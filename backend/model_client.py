"""The only LLM HTTP boundary. Both ReAct and G-Agent inject this client."""
import asyncio
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Optional, Protocol
from urllib.parse import urlsplit
import httpx


@dataclass(frozen=True)
class ModelOptions:
    base_url: str
    api_key: str
    model: str
    timeout: float = 60.0


class Provider(Protocol):
    kind: str
    model: Optional[str]
    async def complete(self, messages: list, tools: list) -> dict: ...


class ModelTransportError(RuntimeError):
    """A bounded, transport-only failure with auditable retry count."""

    def __init__(self, message: str, *, transport_retries: int = 0):
        super().__init__(message)
        self.transport_retries = transport_retries


def valid_count(value):
    return type(value) is int and 0 <= value <= 9007199254740991


def request_body(options, messages, tools, *, require_tool=False):
    body = {'model': options.model, 'messages': messages, 'tools': [
        {'type': 'function', 'function': {'name': t.name, 'description': t.description, 'parameters': t.parameters}} for t in tools],
        'tool_choice': 'required' if require_tool and tools else 'auto', 'parallel_tool_calls': True, 'enable_thinking': False}
    if urlsplit(options.base_url).hostname == 'openrouter.ai':
        body['reasoning'] = {'enabled': False}
    return body


class ModelClient:
    kind = 'live'

    def __init__(self, options, transport=None):
        parsed = urlsplit(options.base_url)
        if not options.api_key or not options.model:
            raise ValueError('请在 .env 配置 LLM_API_KEY 和 LLM_MODEL 后重启服务。')
        if parsed.scheme not in ['http', 'https'] or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('模型地址必须是无内嵌凭据的 HTTP(S) API 基础地址')
        self.options, self.model, self.transport = options, options.model, transport
        self.settings = {'enableThinking': False, 'parallelToolCalls': True}
        self.supports_required_tool_choice = True
        if parsed.hostname == 'openrouter.ai':
            self.settings['reasoningEnabled'] = False

    async def complete(self, messages, tools, *, require_tool=False):
        retries = 0
        retryable_statuses = {408, 429, 500, 502, 503, 504}
        async with httpx.AsyncClient(timeout=self.options.timeout, follow_redirects=False, trust_env=False, transport=self.transport) as client:
            while True:
                try:
                    response = await client.post(self.options.base_url.rstrip('/') + '/chat/completions',
                                                 headers={'Authorization': 'Bearer ' + self.options.api_key},
                                                 json=request_body(self.options, messages, tools, require_tool=require_tool))
                except httpx.TimeoutException:
                    if retries == 0:
                        retries = 1
                        await asyncio.sleep(0.2)
                        continue
                    raise ModelTransportError('模型服务请求超时；已重试 1 次仍失败。', transport_retries=retries) from None
                except httpx.HTTPError:
                    if retries == 0:
                        retries = 1
                        await asyncio.sleep(0.2)
                        continue
                    raise ModelTransportError('模型服务网络连接失败；已重试 1 次仍失败。', transport_retries=retries) from None
                if response.status_code == 200:
                    break
                if response.status_code in retryable_statuses and retries == 0:
                    retries = 1
                    await asyncio.sleep(0.2)
                    continue
                suffix = '已重试 1 次仍失败。' if retries else '本次请求未自动重试。'
                raise ModelTransportError(f'模型服务返回 HTTP {response.status_code}；{suffix}', transport_retries=retries)
        try:
            payload = response.json()
            choice = payload['choices'][0]
            message = choice['message']
            if not isinstance(message, dict) or message.get('role') != 'assistant':
                raise ValueError()
            if message.get('refusal'):
                raise RuntimeError('模型拒绝了本次任务。')
            calls = message.get('tool_calls') or []
            if not isinstance(calls, list) or any(not isinstance(c, dict) or c.get('type') != 'function' or not isinstance(c.get('id'), str)
                or not isinstance(c.get('function'), dict) or not isinstance(c['function'].get('name'), str) or not isinstance(c['function'].get('arguments'), str) for c in calls):
                raise ValueError()
            if len({c['id'] for c in calls}) != len(calls):
                raise ValueError()
            clean = {'role': 'assistant', 'content': message.get('content') if isinstance(message.get('content'), str) else None}
            if calls:
                clean['tool_calls'] = [{'id': c['id'], 'type': 'function', 'function': {'name': c['function']['name'], 'arguments': c['function']['arguments']}} for c in calls]
            result = {
                'message': clean,
                'finishReason': choice.get('finish_reason', 'unknown'),
                'transportRetries': retries,
                # Failed transport attempts have no reliable provider usage
                # payload, even when the retry later succeeds.
                'usageComplete': retries == 0,
            }
            usage = payload.get('usage') or {}
            if valid_count(usage.get('prompt_tokens')) and valid_count(usage.get('completion_tokens')):
                result['usage'] = {'input': usage['prompt_tokens'], 'output': usage['completion_tokens']}
                reasoning = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
                if valid_count(reasoning):
                    result['usage']['reasoning'] = reasoning
            return result  # Never retain reasoning_content or raw credentials in traces.
        except (ValueError, TypeError, KeyError, IndexError):
            raise RuntimeError('模型服务返回不合法的工具调用响应') from None
