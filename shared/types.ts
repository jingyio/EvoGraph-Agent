export type Scenario = 'finance' | 'support';
export type RunMode = 'fixture' | 'live';
export type AgentStrategy = 'react' | 'graph';
export type SnapshotVariant = 'base' | 'changed' | 'exception';
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
export interface RunEvent { seq: number; at: string; type: 'start' | 'model' | 'action' | 'observation' | 'finish' | 'error' | 'graph' | 'evaluation'; title: string; detail?: unknown; durationMs?: number }
export interface RunMetrics { modelRequests: number; toolCalls: number; toolErrors: number; inputTokens: number | null; outputTokens: number | null; reasoningTokens?: number | null; usageComplete: boolean; durationMs: number }
export type EvaluationProfile = 'auto' | 'invariants' | 'finance_full' | 'support_full';
export interface RunRequest { scenario: Scenario; mode: RunMode; source: DataSource; task: string; strategy?: AgentStrategy; snapshot?: SnapshotVariant; evaluationProfile?: EvaluationProfile }
export interface AgentRun {
  id: string; request: RunRequest; status: RunStatus; startedAt: string; finishedAt?: string;
  model: string | null; metrics: RunMetrics; events: RunEvent[]; initial: World; state: World;
  report?: Report; finalText?: string; error?: string;
  graph?: GraphExecution;
  modelSettings?: { enableThinking: boolean; reasoningEnabled?: boolean; parallelToolCalls?: boolean };
  backend?: 'python';
  evaluation?: { status: 'passed' | 'failed' | 'not_evaluated'; scope: string; issues: { code: string; entityId: string; message: string }[]; note: string };
}
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export type GraphBinding = { kind: 'literal'; value: JsonValue } | { kind: 'item'; path: string[] } | { kind: 'result'; nodeId: string; path: string[] };
export interface GraphNode {
  id: string; tool: string; arguments: Record<string, GraphBinding>; dependencies: string[];
  foreach?: { nodeId: string; collectionPath: string[] | null };
  paginate?: { maxPages: number };
  sourceEventSeqs: number[];
}
export interface TaskGraph {
  id: string; version: number; createdAt: string; sourceRunId: string; scenario: Scenario; source: DataSource;
  task: string; taskKey: string; contractHash: string; environmentHash: string; nodes: GraphNode[];
  sourceModelRequests: number; sourceInputTokens: number | null; sourceOutputTokens: number | null;
  validation: { status: 'passed'; toolCalls: number; durationMs: number; compileMs: number; learningModelRequests: 0 };
  scope: 'read-prefix'; compilerVersion: 1;
}
export interface GraphExecution {
  status: 'miss' | 'hit' | 'fallback'; graphId?: string; version?: number; sourceRunId?: string; reason?: string;
  nodeStates: Record<string, 'pending' | 'running' | 'done' | 'failed'>; toolCalls: number; completedNodes: number;
  learnedGraphId?: string; learning?: TaskGraph['validation']; learningError?: string;
  selection?: 'exact' | 'adapted' | 'none'; plannerRequests?: number; selectedNodeIds?: string[];
}
export interface ToolCard { name: string; description: string; effect: 'read' | 'sandbox-write' | 'artifact'; parameters: Record<string, unknown>; origin?: { kind: 'autotool'; spec: string; operationId: string; digest: string } }
export interface PublicConfig { modelConfigured: boolean; model: string | null; maxSteps: number; backend?: string; enableThinking?: boolean; connectors: { erpnext: boolean; zammad: boolean }; presets: Record<Scenario, string> }

export const PRESETS: Record<Scenario, string> = {
  finance: '核对当前快照的全部回款与应收。仅在客户、币种和发票引用一致且无重复银行流水时分配回款；处理部分回款，登记疑似重复、无法匹配和逾期异常，输出有记录依据的对账简报。',
  support: '巡检当前快照的全部未关闭工单，识别超时和紧急工单，按技能、可用状态及剩余容量分派；为每个未关闭工单检索知识库并保存回复草稿，升级超时工单，输出服务运营简报。不要发送消息或把工单标成已解决。',
};
