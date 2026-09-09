import type { Tool } from './tools.js';
import type { ChatMessage, Completion, ModelOptions, Provider, ToolCall } from './model-types.js';

/** The only model HTTP boundary, shared by ReAct and the experience planner. */
export function buildModelRequest(options: ModelOptions, messages: ChatMessage[], tools: Tool[]) {
  const openRouter = new URL(options.baseUrl).hostname === 'openrouter.ai';
  return {
    model: options.model,
    messages,
    tools: tools.map(tool => ({ type: 'function', function: { name: tool.name, description: tool.description, parameters: tool.parameters } })),
    tool_choice: 'auto',
    parallel_tool_calls: false,
    enable_thinking: false,
    ...(openRouter ? { reasoning: { enabled: false } } : {}),
  };
}

export class ChatCompletionsProvider implements Provider {
  readonly kind = 'live' as const;
  readonly model: string;
  readonly settings: { enableThinking: false; reasoningEnabled?: false };
  constructor(private options: ModelOptions) {
    if (!options.apiKey || !options.model) throw new Error('请在 .env 配置 LLM_API_KEY 和 LLM_MODEL，然后重启服务。');
    const url = new URL(options.baseUrl);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('LLM_BASE_URL must be an HTTP(S) API base URL without embedded credentials or query');
    this.model = options.model;
    this.settings = { enableThinking: false, ...(url.hostname === 'openrouter.ai' ? { reasoningEnabled: false as const } : {}) };
  }
  async complete(messages: ChatMessage[], tools: Tool[], signal: AbortSignal): Promise<Completion> {
    const response = await fetch(`${this.options.baseUrl.replace(/\/+$/, '')}/chat/completions`, {
      method: 'POST', redirect: 'error', signal: AbortSignal.any([signal, AbortSignal.timeout(this.options.timeoutMs)]),
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${this.options.apiKey}` },
      body: JSON.stringify(buildModelRequest(this.options, messages, tools)),
    });
    if (!response.ok) throw new Error(`模型服务返回 HTTP ${response.status}。请检查模型、地址、额度与鉴权；本次请求未自动重试。`);
    const payload = await response.json() as any;
    const choice = payload.choices?.[0], message = choice?.message;
    if (!message || message.role !== 'assistant') throw new Error('模型服务未返回合法的 assistant message');
    if (message.refusal) throw new Error('模型拒绝了本次任务。');
    const calls = message.tool_calls ?? [];
    if (!Array.isArray(calls) || calls.some((call: any) => call.type !== 'function' || typeof call.id !== 'string' || typeof call.function?.name !== 'string' || typeof call.function?.arguments !== 'string') || new Set(calls.map((call: ToolCall) => call.id)).size !== calls.length) throw new Error('模型返回的工具调用格式不合法');
    const usage = payload.usage;
    const reasoningTokens = usage?.completion_tokens_details?.reasoning_tokens;
    const validUsage = Number.isSafeInteger(usage?.prompt_tokens) && usage.prompt_tokens >= 0 && Number.isSafeInteger(usage?.completion_tokens) && usage.completion_tokens >= 0;
    // reasoning_content is intentionally not requested, logged or displayed.
    return { message: { role: 'assistant', content: typeof message.content === 'string' ? message.content : null, ...(calls.length ? { tool_calls: calls } : {}) }, usage: validUsage ? { input: usage.prompt_tokens, output: usage.completion_tokens, ...(Number.isSafeInteger(reasoningTokens) && reasoningTokens >= 0 ? { reasoning: reasoningTokens } : {}) } : undefined, finishReason: choice.finish_reason || 'unknown' };
  }
}

