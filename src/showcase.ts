export const SHOWCASE_EXPERIMENT = 'online-rsi-serial-final-v4';

export type Metrics = Record<string, number | boolean | undefined>;
export type Audit = {
  schemaExact: boolean; metricExact: boolean; selectionExact: boolean; evidenceExact: boolean; evidenceObserved: boolean;
  summaryReferencesValid: boolean; summaryNumbersGrounded: boolean; currencyNotationClear: boolean;
  strictStructuredPass: boolean; strictReportAuditPass: boolean; issues: string[];
};
export type CompactRun = {
  id: string; strategy: string; status: string; evaluation: { status: string; issues?: string[] };
  metrics: Metrics; phaseMetrics: Record<string, { requests?: number; inputTokens?: number; outputTokens?: number }>;
  evolution?: { usedVersionId?: string | null; generation?: number | null; planningPath?: string; generatedVersionIds?: string[]; note?: string; [key: string]: unknown } | null;
  audit: Audit;
};
export type ShowcasePair = {
  index: number; round: number; taskId: string; scenario: string; family: string; familyLabel: string; recordCount: number;
  launchOrder: string[]; runs: { baseline: CompactRun; rsi: CompactRun }; links: Record<string, { trace: string; report: string }>;
};
export type Showcase = {
  id: string; status: string; createdAt: string;
  protocol: Record<string, string | number | boolean | null>;
  overview: {
    baseline: Record<string, any>; rsi: Record<string, any>; tokenSavingRate: number; modelRequestSavingRate: number;
    observedLatencySavingRate: number; toolCallDelta: number; qualityRegressions: number; judge: Record<string, any>;
  };
  audit: { arms: Record<string, Record<string, any>>; scope: string };
  coverage: { experimentTaskCount: number; taskbankTaskCount: number; experimentDescription: string; taskbankDescription: string };
  sources: Source[];
  allTasks: TaskGroup;
  categories: ScenarioGroup[];
  families: { id: string; scenario: string; family: string; label: string; pairs: string[]; points: FamilyPoint[]; finalSavingRate: number }[];
  pairs: ShowcasePair[];
  limitations: Record<string, string>;
};
export type GroupMetrics = { attempts: number; passed: number; inputTokens: number; outputTokens: number; totalTokens: number; modelRequests: number; toolCalls: number; durationMs: number };
export type TaskGroup = { id: string; label: string; taskCount: number; pairs: string[]; points: FamilyPoint[]; finalSavingRate: number; metrics: { baseline: GroupMetrics; rsi: GroupMetrics } };
export type ScenarioGroup = TaskGroup & { scenario: string; familyCount: number; featuredTaskId: string; families: string[] };
export type Source = { scenario: string; label: string; source: string; sourceScale: string; taskShape: string; toolBoundary: string; featuredTaskId: string };
export type FamilyPoint = { taskId: string; position: number; baselineCumulativeTokens: number; rsiCumulativeTokens: number; savingRate: number };
export type GraphNode = { id: string; tool: string; dependencies: string[]; filter?: { field: string; operator: string; value: string }; reuse?: string[]; defer: boolean; boundArguments: Array<Record<string, unknown> | string> };
export type Step = { kind: string; title: string; detail: string | string[] | Record<string, unknown>; executor?: string; nodeId?: string | null };
export type PairDetail = ShowcasePair & {
  task: { id: string; title: string; task: string; scenario: string; family: string; recordCount: number; recordIds: string[]; sourceUrl?: string };
  runs: { baseline: CompactRun & { graphNodes: GraphNode[]; steps: Step[]; timeline: TimelineEvent[]; report: Record<string, unknown> }; rsi: CompactRun & { graphNodes: GraphNode[]; steps: Step[]; timeline: TimelineEvent[]; report: Record<string, unknown> } };
};
export type TimelineEvent = { position: number; kind: string; title: string; elapsedMs: number; metrics: Metrics };

export const total = (metrics?: Metrics) => Number(metrics?.inputTokens || 0) + Number(metrics?.outputTokens || 0);
export const number = (value?: number) => new Intl.NumberFormat('zh-CN').format(Math.round(value || 0));
export const percent = (value?: number | null) => value == null ? '—' : `${(value * 100).toFixed(1)}%`;
export const duration = (ms?: number) => `${((ms || 0) / 1000).toFixed(1)}s`;
export const shorterTool = (tool?: string) => (tool || '').replace(/^(finance|support|tickets)_/, '').replaceAll('_', ' ');
export const taskFromHash = () => new URLSearchParams(window.location.hash.split('?')[1] || '').get('task') || '';
