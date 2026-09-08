export type Scenario = 'finance' | 'support';
export type RunMode = 'fixture' | 'live';
export type DataSource = 'sandbox' | 'erpnext' | 'zammad';
export type RunStatus = 'running' | 'completed' | 'failed' | 'cancelled' | 'limited';
export type Priority = 'low' | 'normal' | 'high' | 'urgent';

export interface Invoice { id: string; customerId: string; customer: string; amountCents: number; currency: 'CNY'; dueDate: string }
export interface Payment { id: string; customerId: string; amountCents: number; currency: 'CNY'; date: string; bankRef: string; invoiceRefs: string[] }
export interface Allocation { paymentId: string; invoiceId: string; amountCents: number }
export interface FinanceCase { id: string; kind: 'duplicate' | 'unmatched' | 'overdue'; entityId: string; summary: string; evidenceIds: string[] }
export interface Ticket { id: string; subject: string; customer: string; category: 'billing' | 'technical' | 'account'; priority: Priority; status: 'open' | 'pending' | 'closed'; ownerId: string | null; dueAt: string; body: string; version: number }
export interface SupportAgent { id: string; name: string; skills: Ticket['category'][]; capacity: number; available: boolean }
export interface KnowledgeArticle { id: string; category: Ticket['category']; title: string; body: string }
export interface ReplyDraft { ticketId: string; body: string; articleIds: string[]; sent: false }
export interface Escalation { ticketId: string; reason: string }
export interface World {
  asOf: string;
  invoices: Invoice[];
  payments: Payment[];
  allocations: Allocation[];
  cases: FinanceCase[];
  tickets: Ticket[];
  agents: SupportAgent[];
  knowledge: KnowledgeArticle[];
  drafts: ReplyDraft[];
  escalations: Escalation[];
}
export interface Metric { label: string; value: string; note?: string }
export interface Report { title: string; summary: string; metrics: Metric[]; columns: string[]; rows: string[][]; findings: string[]; source: DataSource; createdAt: string }
export interface RunEvent { seq: number; at: string; type: 'start' | 'model' | 'action' | 'observation' | 'finish' | 'error'; title: string; detail?: unknown; durationMs?: number }
export interface RunMetrics { modelRequests: number; toolCalls: number; toolErrors: number; inputTokens: number | null; outputTokens: number | null; usageComplete: boolean; durationMs: number }
export interface RunRequest { scenario: Scenario; mode: RunMode; source: DataSource; task: string }
export interface AgentRun {
  id: string; request: RunRequest; status: RunStatus; startedAt: string; finishedAt?: string;
  model: string | null; metrics: RunMetrics; events: RunEvent[]; initial: World; state: World;
  report?: Report; finalText?: string; error?: string;
}
export interface ToolCard { name: string; description: string; effect: 'read' | 'sandbox-write' | 'artifact'; parameters: Record<string, unknown> }
export interface PublicConfig { modelConfigured: boolean; model: string | null; maxSteps: number; connectors: { erpnext: boolean; zammad: boolean }; presets: Record<Scenario, string> }

export const PRESETS: Record<Scenario, string> = {
  finance: '核对当前快照的全部回款与应收。仅在客户、币种和发票引用一致且无重复银行流水时分配回款；处理部分回款，登记疑似重复、无法匹配和逾期异常，输出有记录依据的对账简报。',
  support: '巡检当前快照的全部未关闭工单，识别超时和紧急工单，按技能、可用状态及剩余容量分派；为每个未关闭工单检索知识库并保存回复草稿，升级超时工单，输出服务运营简报。不要发送消息或把工单标成已解决。',
};
