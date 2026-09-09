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


def valid_count(value):
    return type(value) is int and 0 <= value <= 9007199254740991


def request_body(options, messages, tools):
    body = {'model': options.model, 'messages': messages, 'tools': [
        {'type': 'function', 'function': {'name': t.name, 'description': t.description, 'parameters': t.parameters}} for t in tools],
        'tool_choice': 'auto', 'parallel_tool_calls': False, 'enable_thinking': False}
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
        self.settings = {'enableThinking': False}
        if parsed.hostname == 'openrouter.ai':
            self.settings['reasoningEnabled'] = False

    async def complete(self, messages, tools):
        try:
            async with httpx.AsyncClient(timeout=self.options.timeout, follow_redirects=False, trust_env=False, transport=self.transport) as client:
                response = await client.post(self.options.base_url.rstrip('/') + '/chat/completions',
                                             headers={'Authorization': 'Bearer ' + self.options.api_key},
                                             json=request_body(self.options, messages, tools))
        except httpx.TimeoutException:
            raise RuntimeError('模型服务请求超时；未自动重试。') from None
        except httpx.HTTPError:
            raise RuntimeError('模型服务网络连接失败；请检查地址与网络。') from None
        if response.status_code != 200:
            raise RuntimeError(f'模型服务返回 HTTP {response.status_code}；本次请求未自动重试。')
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
            result = {'message': clean, 'finishReason': choice.get('finish_reason', 'unknown')}
            usage = payload.get('usage') or {}
            if valid_count(usage.get('prompt_tokens')) and valid_count(usage.get('completion_tokens')):
                result['usage'] = {'input': usage['prompt_tokens'], 'output': usage['completion_tokens']}
                reasoning = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
                if valid_count(reasoning):
                    result['usage']['reasoning'] = reasoning
            return result  # Never retain reasoning_content or raw credentials in traces.
        except (ValueError, TypeError, KeyError, IndexError):
            raise RuntimeError('模型服务返回不合法的工具调用响应') from None
