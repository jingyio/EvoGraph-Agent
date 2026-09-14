export type Release = {
  releaseId: string;
  displayName: string;
  status: "candidate" | "formal" | "historical";
  experimentId: string;
  runtimeRevision: string;
  assetVersion: string;
  protocol: Record<string, unknown>;
  claims: string[];
  limitations: string[];
  createdAt: string;
  source: string;
};
export type Metrics = {
  tokens?: number;
  attempts?: number;
  passed?: number;
  inputTokens: number;
  outputTokens: number;
  modelRequests: number;
  toolCalls: number;
  toolErrors: number;
  durationMs: number;
  usageComplete: boolean;
  failedReportAttempts?: number;
  recoveryToolCalls?: number;
  modelTransportRetries?: number;
  modelProviderAttempts?: number;
};
export type Group = {
  name: string;
  reason: string;
  condition: string;
  count: number;
  selectedIds: string[];
  evidenceIds: string[];
};
export type Run = {
  id: string;
  status: string;
  metrics: Metrics;
  evaluation: { status: string; issues?: string[] };
  submission?: {
    summary: string;
    metrics: Record<string, unknown>;
    groups?: Group[];
    selectedIds: string[];
  };
  events?: {
    seq: number;
    type: string;
    title: string;
    elapsedMs: number;
    detail?: unknown;
  }[];
  graph?: unknown;
  evolution?: unknown;
  trajectoryMatch?: unknown;
  error?: string;
};
export type Pair = {
  pairId: string;
  title: string;
  scenario: string;
  position: number;
  status: string;
  features: unknown;
  detail: string;
  runs: Partial<Record<"baseline" | "rsi", Run>>;
};
export type PairDetail = {
  releaseId: string;
  experimentId: string;
  pairId: string;
  task: { task: string; title: string };
  inputs: { id: string; name: string; sizeBytes: number; download: string }[];
  tables: { sheet: string; rowCount: number }[];
  runs: Partial<Record<"baseline" | "rsi", Run>>;
};
export type Revision = {
  graphId: string;
  sourcePairId: string;
  sourceRunId: string;
  graphChanged: boolean;
  matchingChanged: boolean;
  subsequentUses: { pairId: string; runId: string; matchVersion: number }[];
  graphDiff: unknown;
  matchingDiff: unknown;
};
export type Evidence = {
  release: Release;
  experimentStatus: string;
  plannedPairs: number;
  pairs: Pair[];
  revisions: Revision[];
  evolutionEvidence: { graph: boolean; matching: boolean };
  summary: {
    qualityGate: boolean;
    arms: Record<"baseline" | "rsi", Metrics>;
    netTokenSaving: number;
    curves: unknown[];
  };
};
export const arms = ["baseline", "rsi"] as const;
export const armLabel = { baseline: "基线 · 模型调度", rsi: "RSI · 经验辅助" };
export const n = (value: number | undefined) =>
  value == null ? "—" : value.toLocaleString("zh-CN");
export const tokens = (m: Metrics) =>
  m.tokens ?? m.inputTokens + m.outputTokens;
export const rate = (v: number | null | undefined) =>
  v == null ? "—" : (v * 100).toFixed(1) + "%";
export const statusLabel = (run: Run | undefined) =>
  !run
    ? "未运行"
    : run.status === "running"
      ? "执行中"
      : run.status === "completed" && run.evaluation.status === "passed"
        ? "校验通过"
        : run.evaluation.status === "user_review_required"
          ? "待人工复核"
          : "未通过";
export function verifyRelease(expected: Release, actual: Release) {
  if (
    expected.releaseId !== actual.releaseId ||
    expected.experimentId !== actual.experimentId ||
    expected.runtimeRevision !== actual.runtimeRevision ||
    expected.assetVersion !== actual.assetVersion ||
    expected.status !== actual.status ||
    JSON.stringify(expected.protocol) !== JSON.stringify(actual.protocol)
  )
    throw new Error("发布上下文发生变化，请重新打开当前证据。");
}
export type Measure = "tokens" | "modelRequests" | "durationMs" | "success";
export function measure(run: Run | undefined, key: Measure): number | null {
  if (!run) return null;
  if (key === "tokens")
    return run.metrics.usageComplete ? tokens(run.metrics) : null;
  if (key === "success")
    return run.status === "completed" && run.evaluation.status === "passed"
      ? 1
      : 0;
  return run.metrics[key];
}
