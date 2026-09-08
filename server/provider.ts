import { randomUUID } from 'node:crypto';
import type { AgentRun, Invoice, Payment, SupportAgent, Ticket } from '../shared/types.js';
import type { Tool } from './tools.js';

export interface ToolCall { id: string; type: 'function'; function: { name: string; arguments: string } }
export interface ChatMessage { role: 'system' | 'user' | 'assistant' | 'tool'; content: string | null; tool_calls?: ToolCall[]; tool_call_id?: string }
export interface Completion { message: ChatMessage; usage?: { input: number; output: number }; finishReason: string }
export interface Provider { kind: 'fixture' | 'live'; model: string | null; complete(messages: ChatMessage[], tools: Tool[], signal: AbortSignal): Promise<Completion> }
export interface ModelOptions { baseUrl: string; apiKey: string; model: string; timeoutMs: number }

export class ChatCompletionsProvider implements Provider {
  readonly kind = 'live' as const;
  readonly model: string;
  constructor(private options: ModelOptions) {
    if (!options.apiKey || !options.model) throw new Error('请在 .env 配置 LLM_API_KEY 和 LLM_MODEL，然后重启服务。');
    const url = new URL(options.baseUrl);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('LLM_BASE_URL must be an HTTP(S) API base URL without embedded credentials or query');
    this.model = options.model;
  }
  async complete(messages: ChatMessage[], tools: Tool[], signal: AbortSignal): Promise<Completion> {
    const response = await fetch(`${this.options.baseUrl.replace(/\/+$/, '')}/chat/completions`, {
      method: 'POST', redirect: 'error', signal: AbortSignal.any([signal, AbortSignal.timeout(this.options.timeoutMs)]),
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${this.options.apiKey}` },
      body: JSON.stringify({ model: this.model, messages, tools: tools.map(tool => ({ type: 'function', function: { name: tool.name, description: tool.description, parameters: tool.parameters } })), tool_choice: 'auto', parallel_tool_calls: false }),
    });
    if (!response.ok) throw new Error(`模型服务返回 HTTP ${response.status}。请检查模型、地址、额度与鉴权；本次请求未自动重试。`);
    const payload = await response.json() as any;
    const choice = payload.choices?.[0], message = choice?.message;
    if (!message || message.role !== 'assistant') throw new Error('模型服务未返回合法的 assistant message');
    if (message.refusal) throw new Error('模型拒绝了本次任务。');
    const calls = message.tool_calls ?? [];
    if (!Array.isArray(calls) || calls.some((call: any) => call.type !== 'function' || typeof call.id !== 'string' || typeof call.function?.name !== 'string' || typeof call.function?.arguments !== 'string') || new Set(calls.map((call: ToolCall) => call.id)).size !== calls.length) throw new Error('模型返回的工具调用格式不合法');
    const usage = payload.usage;
    const validUsage = Number.isSafeInteger(usage?.prompt_tokens) && usage.prompt_tokens >= 0 && Number.isSafeInteger(usage?.completion_tokens) && usage.completion_tokens >= 0;
    // reasoning_content is intentionally not requested, logged or displayed.
    return { message: { role: 'assistant', content: typeof message.content === 'string' ? message.content : null, ...(calls.length ? { tool_calls: calls } : {}) }, usage: validUsage ? { input: usage.prompt_tokens, output: usage.completion_tokens } : undefined, finishReason: choice.finish_reason || 'unknown' };
  }
}

type Action = { name: string; args: Record<string, unknown> };
type Instruction = { title: string; actions: Action[] };
const action = (name: string, args: Record<string, unknown> = {}): Action => ({ name, args });
const step = (title: string, ...actions: Action[]): Instruction => ({ title, actions });
type Plan = Generator<Instruction, string, any[]>;

function* financeFixture(): Plan {
  const [, , payments] = yield step('读取业务时间、应收发票与回款记录', action('get_business_clock'), action('list_invoices'), action('list_payments'));
  const duplicateGroups = new Set<string>();
  for (const payment of payments as Payment[]) {
    const [preview] = yield step(`核查 ${payment.id} 的匹配依据`, action('preview_payment_match', { paymentId: payment.id }));
    if (preview.eligible) {
      yield step(`保存 ${payment.id} 的沙箱匹配关系`, action('allocate_payment', { paymentId: payment.id, allocations: preview.allocations }));
    } else if (preview.reason === 'duplicate_bank_reference') {
      if (duplicateGroups.has(payment.bankRef)) continue;
      duplicateGroups.add(payment.bankRef);
      yield step('登记疑似重复流水，保留原始记录', action('create_finance_case', { kind: 'duplicate', entityId: payment.id, evidenceIds: preview.evidenceIds, summary: `${payment.bankRef} 出现重复记录，核实前不分配该组回款。` }));
    } else if (preview.reason !== 'no_remaining_balance') {
      yield step('登记缺少匹配依据的回款', action('create_finance_case', { kind: 'unmatched', entityId: payment.id, evidenceIds: preview.evidenceIds, summary: `${payment.id} 缺少可核验的发票引用，需要补充客户与付款用途。` }));
    }
  }
  const [overdue] = yield step('核对分配后的逾期应收', action('list_overdue_invoices'));
  if (overdue.length) yield step('为仍未结清的逾期发票登记核查事项', ...(overdue as Invoice[]).map(invoice => action('create_finance_case', { kind: 'overdue', entityId: invoice.id, evidenceIds: [invoice.id], summary: `${invoice.id}（${invoice.customer}）已超过 ${invoice.dueDate}，仍有应收余额待跟进。` })));
  yield step('根据实际账目状态生成简报', action('publish_report', { summary: '已完成有明确依据的回款分配；重复流水与无法识别用途的回款保留待核查，并登记剩余逾期应收。金额由沙箱账目计算。' }));
  return '离线固定流程示例已完成。已保存匹配关系、异常事项与运营简报。本次没有调用 LLM，不能作为 ReAct 性能结果。';
}

function* supportFixture(): Plan {
  const [tickets, agents] = yield step('读取未关闭工单与坐席容量', action('list_tickets', { scope: 'active' }), action('list_agents'), action('get_business_clock'));
  const [risks] = yield step('识别 SLA 风险与紧急事项', action('get_sla_risks'));
  const priority: Record<string, number> = { urgent: 0, high: 1, normal: 2, low: 3 };
  const active = (tickets as Ticket[]).sort((a, b) => priority[a.priority] - priority[b.priority] || a.dueAt.localeCompare(b.dueAt));
  const available = agents as (SupportAgent & { activeCount: number })[];
  for (const ticket of active) {
    if (!ticket.ownerId) {
      const candidate = available.filter(agent => agent.available && agent.skills.includes(ticket.category) && agent.activeCount < agent.capacity).sort((a, b) => a.activeCount - b.activeCount || a.id.localeCompare(b.id))[0];
      if (candidate) { yield step(`按技能与余量分派 ${ticket.id}`, action('assign_ticket', { ticketId: ticket.id, agentId: candidate.id, expectedVersion: ticket.version })); candidate.activeCount++; }
      else yield step(`记录 ${ticket.id} 的容量不足`, action('escalate_ticket', { ticketId: ticket.id, reason: '没有符合技能且具有剩余容量的可用坐席，需要主管协调。' }));
    }
    const [articles] = yield step(`为 ${ticket.id} 检索处理依据`, action('search_knowledge', { category: ticket.category, query: ticket.subject }));
    if (articles.length) yield step(`保存 ${ticket.id} 的内部回复草稿`, action('save_reply_draft', { ticketId: ticket.id, body: `您好，关于“${ticket.subject}”，我们已记录并准备进一步核查。${articles[0].body} 目前尚未确认问题解决。`, articleIds: [articles[0].id] }));
  }
  const overdue = risks.filter((risk: any) => risk.overdue);
  if (overdue.length) yield step('登记超时工单的升级事项', ...overdue.map((risk: any) => action('escalate_ticket', { ticketId: risk.ticketId, reason: '已超过业务快照时刻的 SLA 截止时间，需要负责人优先跟进。' })));
  yield step('生成服务运营简报', action('publish_report', { summary: '已按技能与容量分派待处理工单，为未关闭工单保存带知识来源的回复草稿，并登记超时升级事项。没有发送消息或关闭工单。' }));
  return '离线固定流程示例已完成。工单分派、回复草稿和超时升级均已保存在独立沙箱中。本次没有调用 LLM。';
}

/** Explicit scripted fixture for offline UI + integration testing, never a fake LLM. */
export class FixtureProvider implements Provider {
  readonly kind = 'fixture' as const;
  readonly model = null;
  private plan: Plan;
  private started = false;
  constructor(scenario: AgentRun['request']['scenario']) { this.plan = scenario === 'finance' ? financeFixture() : supportFixture(); }
  async complete(messages: ChatMessage[], _tools: Tool[], signal: AbortSignal): Promise<Completion> {
    signal.throwIfAborted();
    const observations: any[] = [];
    if (this.started) {
      for (let i = messages.length - 1; i >= 0 && messages[i].role === 'tool'; i--) {
        const observation = JSON.parse(messages[i].content || '{}');
        if (!observation.ok) throw new Error(`离线流程工具失败：${observation.error}`);
        observations.unshift(observation.result);
      }
    }
    this.started = true;
    const next = this.plan.next(observations);
    if (next.done) return { message: { role: 'assistant', content: next.value }, finishReason: 'stop' };
    return { message: { role: 'assistant', content: next.value.title, tool_calls: next.value.actions.map(item => ({ id: `call_${randomUUID()}`, type: 'function', function: { name: item.name, arguments: JSON.stringify(item.args) } })) }, finishReason: 'tool_calls' };
  }
}
