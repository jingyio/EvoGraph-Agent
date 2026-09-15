import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BadgeDollarSign,
  ArrowUpRight,
  Clock3,
  FileDown,
  Gauge,
  GitBranch,
  Layers3,
  LoaderCircle,
  Pause,
  Play,
  RotateCcw,
  Route,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { api } from "./api";
import {
  attributionTimelineHeading,
  cumulativePoints,
  evolutionSignals,
  firstMemoryReuseIndex,
  normalizedRevisionEvidence,
  releaseAllowsCostClaims,
  replayPrefix,
  revisionIsAuditable,
  revisionVisualState,
  scopeAllowsCostClaims,
  scopedRevisionEvidence,
  type CumulativeMeasures,
  type RevisionEvidence,
} from "./dataAnalysisMath";
import "./data-analysis.css";

type Scenario = "finance" | "support" | "tickets" | string;
type DatasetSummary = {
  datasetId: string;
  releaseId?: string;
  displayName: string;
  status: string;
  experimentId: string;
  runtimeRevision?: string;
  assetVersion?: string;
  protocol?: string | Record<string, unknown>;
  createdAt?: string;
  taskCount?: number;
  limitations?: string[];
  claims?: string[];
  taskPlan?: unknown[];
  attribution?: Record<string, unknown>;
};
type Arm = {
  runId?: string;
  status?: string;
  passed?: boolean;
  tokens?: number | null;
  inputTokens?: number | null;
  outputTokens?: number | null;
  costUsd?: number | null;
  models?: Record<string, string>;
  durationMs?: number | null;
  latencyMs?: number | null;
  runUrl?: string;
  modelRequests?: number | null;
  toolCalls?: number | null;
  usageComplete?: boolean;
  reportUrl?: string;
  traceUrl?: string;
  toolErrors?: number | null;
  executionStages?: Record<string, ExecutionStageMetric>;
  error?: string;
};
type Point = {
  detailUrl?: string;
  index: number;
  pairId?: string;
  workpackId: string;
  title?: string;
  opportunity?: string;
  scenario: Scenario;
  workflowType: string;
  cohortId?: string;
  round?: number;
  status?: string;
  baseline: Arm;
  rsi: Arm & {
    planningPath?: string;
    usedVersionId?: string | null;
    usedMatchVersion?: string | number | null;
    generatedVersionIds?: string[];
    generatedMatchVersions?: Array<string | number>;
  };
};
type ExecutionStageMetric = {
  requests?: number | null;
  inputTokens?: number | null;
  outputTokens?: number | null;
  tokens?: number | null;
  usageComplete?: boolean;
};
type CohortSummary = {
  cohortId: string;
  label: string;
  pairIds: string[];
  baseline: ArmSummary & { usageComplete?: boolean };
  rsi: ArmSummary & { usageComplete?: boolean };
  qualityGate: { status: string; sameQualityCostClaim: boolean; reason: string };
  costConclusionAllowed: boolean;
  tokenSaving?: number | null;
  latencySaving?: number | null;
  requestSaving?: number | null;
  costSaving?: number | null;
  note?: string;
};
type ArmSummary = {
  attempts?: number;
  passed?: number;
  totalTokens?: number;
  tokens?: number;
  durationMs?: number;
  latencyMs?: number;
  modelRequests?: number;
  toolCalls?: number;
  toolErrors?: number;
  usageIncomplete?: number;
  costUsd?: number | null;
  executionStages?: Record<string, ExecutionStageMetric>;
};
type ModelPricing = {
  currency: "USD";
  source: { name: string; url: string; retrievedAt: string };
  models: Record<
    string,
    { inputPerMillionUsd: number; outputPerMillionUsd: number }
  >;
};
type MaintenanceRun = {
  runId?: string;
  diagnosticId?: string;
  diagnosticStatus?: string;
  status?: string;
  evaluationStatus?: string;
  runtimeRevision?: string;
  model?: string;
  learningEnabled?: boolean | null;
  modelRequests?: number | null;
  tokens?: number | null;
  inputTokens?: number | null;
  outputTokens?: number | null;
  latencyMs?: number | null;
  toolCalls?: number | null;
  toolErrors?: number | null;
  usageComplete?: boolean;
  planningPath?: string;
  usedVersionId?: string | null;
  usedMatchVersion?: string | number | null;
  selectedGraphNodeCount?: number;
  currentBindings?: Array<{ slot?: string; value?: unknown; quote?: string }>;
  uncovered?: string[];
  note?: string;
  runUrl?: string;
  reportUrl?: string;
  artifactUrl?: string;
  claims?: string[];
  limitations?: string[];
};
type MaintenanceDiagnostics = {
  kind: "post_release_cross_runtime";
  sourceTaskId: string;
  request: string;
  excludedFromFormalMetrics: true;
  formal: MaintenanceRun;
  validated: MaintenanceRun;
  failedSetup: MaintenanceRun;
  claims?: string[];
  limitations?: string[];
};
type Detail = DatasetSummary & {
  dataset?: DatasetSummary;
  experiment?: {
    id?: string;
    pairs?: unknown[];
    summary?: Record<string, unknown>;
  };
  points?: unknown[];
  pairs?: unknown[];
  summary?: {
    pairedCompleted?: number;
    tokenSavingRate?: number | null;
    latencySavingRate?: number | null;
    tokenSaving?: number | null;
    costSaving?: number | null;
    latencySaving?: number | null;
    baseline?: ArmSummary;
    rsi?: ArmSummary;
    arms?: { no_learning?: ArmSummary; online_rsi?: ArmSummary };
    points?: unknown[];
    protocolComplete?: boolean;
    costConclusionAllowed?: boolean;
    netTokenSaving?: number | null;
    netLatencySaving?: number | null;
    actualGraphUse?: {
      hits?: number;
      attempts?: number;
      rate?: number | null;
      minimumRate?: number | null;
      met?: boolean;
    } | null;
    learning?: {
      fastReuse?: number;
      workflowCreated?: number;
      composition?: number;
      fallback?: number;
      graphRevisions?: number;
      matchingRevisions?: number;
      subsequentUses?: number;
      created?: unknown[];
      revisions?: unknown[];
      laterUse?: unknown[];
      revisionWithLaterUse?: boolean;
    };
    qualityGate?: { status?: string; reason?: string } | boolean;
    reliability?: { allUsageComplete?: boolean; note?: string };
    cohorts?: CohortSummary[];
    curve?: unknown[];
  };
  revisions?: RevisionEvidence[];
  pricing?: ModelPricing;
  taskPlan?: unknown[];
  attribution?: Record<string, unknown>;
  maintenanceDiagnostics?: MaintenanceDiagnostics | null;
  limitations?: string[];
};
type ChartPoint = Point & CumulativeMeasures;

const scenarioNames: Record<string, string> = {
  finance: "财务运营",
  support: "客服运营",
  tickets: "技术工单",
};
const number = (value?: number | null) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("zh-CN").format(Math.round(value));
const percent = (value?: number | null) =>
  value == null ? "—" : `${(value * 100).toFixed(1)}%`;
const money = (value?: number | null) => {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value < 1 ? 4 : 2,
    maximumFractionDigits: value < 1 ? 4 : 2,
  }).format(value);
};
const duration = (value?: number | null) => {
  if (value == null) return "—";
  if (value < 60_000) return `${(value / 1000).toFixed(1)} 秒`;
  return `${(value / 60_000).toFixed(1)} 分钟`;
};
const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" ? (value as Record<string, unknown>) : {};
const asNumber = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
const asString = (value: unknown): string | undefined =>
  typeof value === "string" && value ? value : undefined;
const asStringArray = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.filter(
        (item): item is string => typeof item === "string" && Boolean(item),
      )
    : [];

const defaultOpportunityChain = [
  "首次创建经验",
  "相近任务复用",
  "业务边界扩展",
  "检验修订后使用",
  "再次检验持续复用",
  "混合义务完整交付",
];

function attributionMode(
  metadata?: DatasetSummary | null,
  detail?: Detail | null,
) {
  const protocol = asRecord(metadata?.protocol);
  const attribution =
    detail?.attribution ||
    metadata?.attribution ||
    asRecord(protocol.attribution);
  const marker = [
    metadata?.datasetId,
    metadata?.assetVersion,
    asString(protocol.id),
    asString(protocol.design),
    asString(attribution.kind),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return (
    Boolean(Object.keys(attribution).length) || marker.includes("attribution")
  );
}

function armLabels(metadata?: DatasetSummary | null, detail?: Detail | null) {
  const protocol = asRecord(metadata?.protocol);
  const attribution =
    detail?.attribution ||
    metadata?.attribution ||
    asRecord(protocol.attribution);
  const labels = asRecord(attribution.armLabels || protocol.armLabels);
  const attributionExperiment = attributionMode(metadata, detail);
  return {
    baseline:
      asString(labels.baseline) ||
      asString(labels.control) ||
      (attributionExperiment ? "图执行 · 不学习" : "Baseline"),
    rsi:
      asString(labels.rsi) ||
      asString(labels.learning) ||
      (attributionExperiment ? "图执行 · 在线RSI" : "RSI Agent"),
  };
}

type PlannedTask = {
  index: number;
  title: string;
  opportunity: string;
  status?: string;
};

function plannedTasks(
  metadata?: DatasetSummary | null,
  detail?: Detail | null,
): PlannedTask[] {
  const protocol = asRecord(metadata?.protocol);
  const candidates =
    [
      detail?.taskPlan,
      metadata?.taskPlan,
      protocol.taskPlan,
      protocol.tasks,
    ].find(Array.isArray) || [];
  const rows = (candidates as unknown[]).map((item, offset) => {
    const row = asRecord(item);
    return {
      index: asNumber(row.index) ?? asNumber(row.position) ?? offset + 1,
      title:
        asString(row.title) || asString(row.taskId) || `任务 ${offset + 1}`,
      opportunity:
        opportunityLabel(asString(row.opportunity) || asString(row.stage)) ||
        defaultOpportunityChain[offset] ||
        "预定任务",
      status: asString(row.status),
    };
  });
  if (rows.length) return rows;
  if (!attributionMode(metadata, detail)) return [];
  const target = asNumber(protocol.taskCountPerArm) ?? metadata?.taskCount ?? 6;
  return Array.from({ length: target }, (_, index) => ({
    index: index + 1,
    title: `任务 ${index + 1}`,
    opportunity: defaultOpportunityChain[index] || "后续复用检验",
    status: "pending",
  }));
}

function opportunityLabel(value?: string) {
  const labels: Record<string, string> = {
    create: "首次创建经验",
    create_reconciliation: "首次创建订单复核经验",
    reuse_and_rebind: "相近任务复用与参数重绑",
    coverage_extension: "业务边界扩展",
    use_extension: "检验扩展后使用",
    use_revision: "检验修订后使用",
    continued_reuse: "再次检验持续复用",
    sustained_reuse: "持续复用检验",
    continued_extension_reuse: "继续检验扩展复用",
    amount_threshold_rebind: "金额阈值重绑",
    installment_threshold_rebind: "分期阈值重绑",
    mixed_threshold_rebind: "混合阈值重绑",
    extension_threshold_rebind: "扩展任务阈值重绑",
    mixed_obligations: "混合义务完整交付",
  };
  return value ? labels[value] || value.replaceAll("_", " ") : undefined;
}

function normalizedRevisions(detail?: Detail | null): RevisionEvidence[] {
  return normalizedRevisionEvidence(detail?.revisions, detail?.pairs);
}

export function datasetItems(payload: unknown): DatasetSummary[] {
  if (Array.isArray(payload)) return payload as DatasetSummary[];
  const root = asRecord(payload);
  return Array.isArray(root.items) ? (root.items as DatasetSummary[]) : [];
}

function normalizeArm(
  value: unknown,
  fallback: Record<string, unknown> = {},
): Arm {
  const arm = asRecord(value);
  const metrics = asRecord(arm.metrics);
  const evaluation = asRecord(arm.evaluation);
  const input = asNumber(metrics.inputTokens);
  const output = asNumber(metrics.outputTokens);
  const explicitTokens = asNumber(arm.tokens);
  const explicitCost = asNumber(arm.costUsd);
  const derivedTokens =
    metrics.usageComplete === false || input == null || output == null
      ? null
      : input + output;
  return {
    runId: asString(arm.runId) || asString(arm.id),
    status: asString(arm.status),
    passed:
      typeof arm.passed === "boolean"
        ? arm.passed
        : typeof evaluation.status === "string"
          ? evaluation.status === "passed"
          : typeof fallback.passed === "boolean"
            ? fallback.passed
            : undefined,
    tokens: explicitTokens ?? asNumber(fallback.tokens) ?? derivedTokens,
    inputTokens: asNumber(arm.inputTokens) ?? input,
    outputTokens: asNumber(arm.outputTokens) ?? output,
    costUsd: explicitCost ?? asNumber(fallback.costUsd),
    models: Object.fromEntries(
      Object.entries(asRecord(arm.models)).filter(
        ([, model]) => typeof model === "string",
      ),
    ) as Record<string, string>,
    durationMs:
      asNumber(arm.latencyMs) ??
      asNumber(arm.durationMs) ??
      asNumber(metrics.durationMs) ??
      asNumber(fallback.durationMs),
    modelRequests:
      asNumber(arm.modelRequests) ??
      asNumber(metrics.modelRequests) ??
      asNumber(fallback.modelRequests),
    toolCalls:
      asNumber(arm.toolCalls) ??
      asNumber(metrics.toolCalls) ??
      asNumber(fallback.toolCalls),
    toolErrors:
      asNumber(arm.toolErrors) ??
      asNumber(metrics.toolErrors) ??
      asNumber(fallback.toolErrors),
    executionStages: Object.fromEntries(
      Object.entries(asRecord(arm.executionStages)).map(([key, value]) => {
        const stage = asRecord(value);
        return [key, {
          requests: asNumber(stage.requests),
          inputTokens: asNumber(stage.inputTokens),
          outputTokens: asNumber(stage.outputTokens),
          tokens: asNumber(stage.tokens),
          usageComplete: typeof stage.usageComplete === "boolean" ? stage.usageComplete : undefined,
        }];
      }),
    ),
    usageComplete:
      typeof arm.usageComplete === "boolean"
        ? arm.usageComplete
        : typeof metrics.usageComplete === "boolean"
          ? metrics.usageComplete
          : undefined,
    reportUrl: asString(arm.reportUrl),
    runUrl: asString(arm.runUrl) || asString(arm.traceUrl),
    traceUrl: asString(arm.traceUrl) || asString(arm.runUrl),
    error: asString(arm.error),
  };
}

export function analysisPoints(detail: Detail): Point[] {
  const experiment = detail.experiment || {};
  const summary =
    detail.summary || (experiment.summary as Detail["summary"]) || {};
  const rawPoints = Array.isArray(detail.points)
    ? detail.points
    : Array.isArray(detail.pairs)
      ? detail.pairs
      : Array.isArray(experiment.pairs)
        ? experiment.pairs
        : Array.isArray(summary.points)
          ? summary.points
          : Array.isArray(summary.curve)
            ? summary.curve
            : [];
  const curve = Array.isArray(summary.curve) ? summary.curve : [];
  const curveByIndex = new Map(
    curve.map((item) => {
      const row = asRecord(item);
      return [Number(row.index), row];
    }),
  );
  return rawPoints
    .map((item, offset) => {
      const row = asRecord(item);
      const spec = asRecord(row.spec);
      const index =
        asNumber(row.index) ??
        asNumber(row.position) ??
        asNumber(spec.position) ??
        offset + 1;
      const curveRow = curveByIndex.get(index) || row;
      const runs = asRecord(row.runs);
      const baselineFallback = {
        tokens: curveRow.baselineTokens,
        durationMs: curveRow.baselineDurationMs,
        passed: curveRow.baselinePassed,
      };
      const rsiFallback = {
        tokens: curveRow.rsiTokens,
        durationMs: curveRow.rsiDurationMs,
        passed: curveRow.rsiPassed,
      };
      const baseline = normalizeArm(
        row.baseline ||
          row.control ||
          row.noLearning ||
          row.no_learning ||
          runs.baseline ||
          runs.control ||
          runs.noLearning ||
          runs.no_learning,
        baselineFallback,
      );
      const rsiRaw = asRecord(
        row.rsi ||
          row.learning ||
          row.onlineRsi ||
          row.online_rsi ||
          runs.rsi ||
          runs.learning ||
          runs.onlineRsi ||
          runs.online_rsi,
      );
      const evolution = asRecord(rsiRaw.evolution);
      const generatedMatchVersions = Array.isArray(row.generatedMatchVersions)
        ? row.generatedMatchVersions
        : Array.isArray(evolution.generatedMatchVersions)
          ? evolution.generatedMatchVersions
          : [];
      const rsi = {
        ...normalizeArm(rsiRaw, rsiFallback),
        planningPath:
          asString(row.planningPath) ||
          asString(rsiRaw.planningPath) ||
          asString(evolution.planningPath) ||
          asString(curveRow.rsiPlanningPath),
        usedVersionId:
          asString(row.usedVersionId) ||
          asString(rsiRaw.usedVersionId) ||
          asString(evolution.usedVersionId) ||
          asString(curveRow.usedVersionId) ||
          null,
        generatedVersionIds: Array.isArray(row.generatedVersionIds)
          ? asStringArray(row.generatedVersionIds)
          : asStringArray(evolution.generatedVersionIds),
        generatedMatchVersions: generatedMatchVersions.filter(
          (value): value is string | number =>
            typeof value === "string" || typeof value === "number",
        ),
        usedMatchVersion:
          asString(row.usedMatchVersion) ??
          asNumber(row.usedMatchVersion) ??
          asString(row.matchVersion) ??
          asNumber(row.matchVersion) ??
          asString(evolution.usedMatchVersion) ??
          asNumber(evolution.usedMatchVersion) ??
          asString(evolution.matchVersion) ??
          asNumber(evolution.matchVersion) ??
          null,
      };
      return {
        index,
        pairId: asString(row.pairId),
        detailUrl: asString(row.detailUrl),
        workpackId:
          asString(row.workpackId) ||
          asString(row.taskId) ||
          asString(spec.id) ||
          asString(curveRow.workpackId) ||
          `task-${index}`,
        title:
          asString(row.title) ||
          asString(spec.title) ||
          asString(curveRow.title),
        opportunity:
          opportunityLabel(
            asString(row.opportunity) || asString(spec.opportunity),
          ) ||
          asString(row.opportunityStage) ||
          asString(curveRow.opportunity),
        scenario:
          asString(row.scenario) || asString(spec.scenario) || "finance",
        workflowType:
          asString(row.workflowType) ||
          asString(spec.workflowType) ||
          asString(curveRow.workflowType) ||
          "财务复核",
        cohortId:
          asString(row.cohortId) ||
          asString(spec.cohortId) ||
          asString(spec.cohort) ||
          asString(curveRow.cohortId) ||
          undefined,
        round: asNumber(row.round) ?? asNumber(curveRow.round) ?? undefined,
        status: asString(row.status),
        baseline,
        rsi,
      } satisfies Point;
    })
    .filter((point) => Number.isFinite(point.index))
    .sort((a, b) => a.index - b.index);
}


function reportUrl(dataset: DatasetSummary, arm: "baseline" | "rsi", run: Arm) {
  const attributionExperiment = attributionMode(dataset);
  const armKey = arm === "baseline" ? "no_learning" : "online_rsi";
  return (
    run.reportUrl ||
    (run.runId
      ? attributionExperiment
        ? `/api/attribution-experiments/${dataset.experimentId}/runs/${armKey}/${run.runId}/report`
        : `/api/workpack-experiments/${dataset.experimentId}/runs/${arm}/${run.runId}/report`
      : "")
  );
}

function traceUrl(dataset: DatasetSummary, arm: "baseline" | "rsi", run: Arm) {
  if (run.traceUrl || run.runUrl) return run.traceUrl || run.runUrl || "";
  if (!run.runId) return "";
  const armKey = arm === "baseline" ? "no_learning" : "online_rsi";
  return attributionMode(dataset)
    ? `/api/attribution-experiments/${dataset.experimentId}/runs/${armKey}/${run.runId}`
    : `/api/workpack-experiments/${dataset.experimentId}/runs/${arm}/${run.runId}`;
}

function PolylineChart({
  points,
  metric,
  onSelect,
  labels,
}: {
  points: ChartPoint[];
  metric: "tokens" | "cost" | "latency" | "requests" | "accuracy" | "saving";
  onSelect: (point: ChartPoint) => void;
  labels: { baseline: string; rsi: string };
}) {
  if (!points.length)
    return (
      <div className="analysis-empty">当前筛选范围没有已保存的成对任务。</div>
    );
  const width = 820;
  const height = 258;
  const left = 58;
  const right = 18;
  const top = 18;
  const bottom = 36;
  const absoluteValue = (point: ChartPoint, arm: "baseline" | "rsi") => {
    if (metric === "tokens")
      return arm === "baseline"
        ? point.baselineCumulativeTokens
        : point.rsiCumulativeTokens;
    if (metric === "cost")
      return arm === "baseline"
        ? point.baselineCumulativeCostUsd
        : point.rsiCumulativeCostUsd;
    if (metric === "latency")
      return arm === "baseline"
        ? point.baselineCumulativeLatency
        : point.rsiCumulativeLatency;
    if (metric === "requests")
      return arm === "baseline"
        ? point.baselineCumulativeRequests
        : point.rsiCumulativeRequests;
    return (arm === "baseline"
      ? point.baselineCumulativeAccuracy
      : point.rsiCumulativeAccuracy) == null
      ? null
      : (arm === "baseline"
          ? point.baselineCumulativeAccuracy!
          : point.rsiCumulativeAccuracy!) * 100;
  };
  const values = points
    .flatMap((point) =>
      metric === "saving"
        ? [
            point.tokenSavingRate == null ? null : point.tokenSavingRate * 100,
            point.latencySavingRate == null
              ? null
              : point.latencySavingRate * 100,
          ]
        : [absoluteValue(point, "baseline"), absoluteValue(point, "rsi")],
    )
    .filter((value): value is number => value != null);
  if (!values.length) {
    const missing =
      metric === "latency"
        ? "latency"
        : metric === "cost"
          ? "模型成本"
          : metric === "requests"
            ? "大模型调用"
            : metric === "accuracy"
              ? "结构化评分"
              : "token";
    return (
      <div className="analysis-empty">
        当前筛选范围缺少完整的 {missing} 数据，未按 0 补齐。
      </div>
    );
  }
  const min = metric === "saving" ? Math.min(0, ...values) : 0;
  const max = metric === "accuracy" ? 100 : Math.max(1, ...values);
  const x = (index: number) =>
    left + (index / Math.max(1, points.length - 1)) * (width - left - right);
  const y = (value: number) =>
    top + ((max - value) / Math.max(1, max - min)) * (height - top - bottom);
  const line = (arm: "baseline" | "rsi") =>
    points
      .map((point, index) => ({ index, value: absoluteValue(point, arm) }))
      .filter(
        (item): item is { index: number; value: number } => item.value != null,
      )
      .map((item) => `${x(item.index)},${y(item.value)}`)
      .join(" ");
  const tokenSavingLine = points
    .map((point, index) => ({
      index,
      value: point.tokenSavingRate == null ? null : point.tokenSavingRate * 100,
    }))
    .filter(
      (item): item is { index: number; value: number } => item.value != null,
    )
    .map((item) => `${x(item.index)},${y(item.value)}`)
    .join(" ");
  const latencySavingLine = points
    .map((point, index) => ({
      index,
      value:
        point.latencySavingRate == null ? null : point.latencySavingRate * 100,
    }))
    .filter(
      (item): item is { index: number; value: number } => item.value != null,
    )
    .map((item) => `${x(item.index)},${y(item.value)}`)
    .join(" ");
  const displayValue = (value: number) =>
    metric === "latency"
      ? duration(value)
      : metric === "cost"
        ? money(value)
        : metric === "saving" || metric === "accuracy"
          ? `${value.toFixed(0)}%`
          : number(value);
  const last = points.at(-1)!;
  return (
    <div className="analysis-chart">
      <div className="analysis-chart-legend">
        {metric === "saving" ? (
          <>
            <span className="saving">
              <i />
              token 节省率
            </span>
            <span className="latency-saving">
              <i />
              latency 节省率
            </span>
          </>
        ) : (
          <>
            <span className="baseline">
              <i />
              {labels.baseline}
            </span>
            <span className="rsi">
              <i />
              {labels.rsi}
            </span>
          </>
        )}
        <small>点击节点查看对应任务</small>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={
          metric === "tokens"
            ? "累计 token 曲线"
            : metric === "cost"
              ? "累计模型成本曲线"
              : metric === "latency"
                ? "累计串行延迟曲线"
                : metric === "requests"
                  ? "累计大模型调用次数曲线"
                  : metric === "accuracy"
                    ? "累计结构化准确率曲线"
                    : "累计 token 与 latency 节省率曲线"
        }
      >
        {[0, 0.5, 1].map((ratio) => {
          const value = min + (max - min) * (1 - ratio);
          const lineY = top + ratio * (height - top - bottom);
          return (
            <g key={ratio}>
              <line
                x1={left}
                y1={lineY}
                x2={width - right}
                y2={lineY}
                className="grid"
              />
              <text x={left - 8} y={lineY + 4} textAnchor="end">
                {displayValue(value)}
              </text>
            </g>
          );
        })}
        {metric === "saving" ? (
          <>
            <polyline points={tokenSavingLine} className="saving-line" />
            <polyline
              points={latencySavingLine}
              className="latency-saving-line"
            />
          </>
        ) : (
          <>
            <polyline points={line("baseline")} className="baseline-line" />
            <polyline points={line("rsi")} className="rsi-line" />
          </>
        )}
        {points.map((point, index) => {
          const value =
            metric === "saving"
              ? point.tokenSavingRate == null
                ? null
                : point.tokenSavingRate * 100
              : absoluteValue(point, "rsi");
          if (value == null) return null;
          return (
            <circle
              key={point.index}
              cx={x(index)}
              cy={y(value)}
              r={points.length > 30 ? 3 : 4}
              className={metric === "saving" ? "saving-node" : "rsi-node"}
              tabIndex={0}
              role="button"
              aria-label={`第 ${point.order} 项，${point.workpackId}`}
              onClick={() => onSelect(point)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onSelect(point);
              }}
            />
          );
        })}
        <text x={left} y={height - 9}>
          1
        </text>
        <text x={width - right} y={height - 9} textAnchor="end">
          {last.order} 个任务
        </text>
      </svg>
    </div>
  );
}

type AnalysisView = "results" | "evolution" | "cost" | "operations" | "audit";

const analysisViews: Array<{ id: AnalysisView; label: string; description: string }> = [
  { id: "results", label: "业务结果", description: "质量与核心结果" },
  { id: "evolution", label: "记忆进化", description: "创建、复用、修订与验证" },
  { id: "cost", label: "成本曲线", description: "token 与串行延迟" },
  { id: "operations", label: "请求与可靠性", description: "模型请求、失败与恢复" },
  { id: "audit", label: "报告与轨迹", description: "任务报告和技术审计" },
];

export default function DataAnalysis() {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [scenario, setScenario] = useState("all");
  const [workflow, setWorkflow] = useState("all");
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [replayCount, setReplayCount] = useState<number | null>(null);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replayIntervalMs, setReplayIntervalMs] = useState(1500);
  const [analysisView, setAnalysisView] = useState<AnalysisView>("results");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [taskDetail, setTaskDetail] = useState<{
    experimentId: string; releaseId: string;
    task: { task: string };
    inputs: { id: string; name: string; download: string }[];
    runs: Record<string, { submission?: { summary?: string }; toolTrace?: { tool: string; executor: string; ok: boolean }[] }>;
  } | null>(null);
  const [taskError, setTaskError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    void api<unknown>("/api/analysis/datasets")
      .then((payload) => {
        if (!active) return;
        const items = datasetItems(payload);
        const root = asRecord(payload);
        const defaultDatasetId = asString(root.defaultDatasetId);
        setDatasets(items);
        setDatasetId(
          (current) => current || defaultDatasetId || items[0]?.datasetId || "",
        );
      })
      .catch((reason) => active && setError(reason.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!datasetId) {
      setDetail(null);
      return;
    }
    let active = true;
    setDetailLoading(true);
    setError("");
    setScenario("all");
    setWorkflow("all");
    setSelectedIndex(null);
    setReplayCount(null);
    setReplayPlaying(false);
    setAnalysisView("results");
    void api<Detail>(`/api/analysis/datasets/${encodeURIComponent(datasetId)}`)
      .then((payload) => active && setDetail(payload))
      .catch((reason) => active && setError(reason.message))
      .finally(() => active && setDetailLoading(false));
    return () => {
      active = false;
    };
  }, [datasetId]);

  const metadata =
    detail?.dataset ||
    detail ||
    datasets.find((item) => item.datasetId === datasetId);
  const isAttribution = attributionMode(metadata, detail);
  const releaseCostConclusionAllowed = releaseAllowsCostClaims(
    metadata?.status,
    detail?.summary?.costConclusionAllowed,
  );
  const labels = armLabels(metadata, detail);
  const cohortSummaries = detail?.summary?.cohorts || [];
  const plan = plannedTasks(metadata, detail);
  const revisions = normalizedRevisions(detail);
  const points = useMemo(
    () => (detail ? analysisPoints(detail) : []),
    [detail],
  );
  const scenarios = useMemo(
    () => Array.from(new Set(points.map((point) => point.scenario))),
    [points],
  );
  const workflows = useMemo(() => {
    const options = new Map<string, string>();
    points
      .filter((point) => scenario === "all" || point.scenario === scenario)
      .forEach((point) =>
        options.set(point.cohortId || point.workflowType, point.workflowType),
      );
    return Array.from(options, ([id, label]) => ({ id, label }));
  }, [points, scenario]);
  const visible = useMemo(
    () =>
      points.filter(
        (point) =>
          (scenario === "all" || point.scenario === scenario) &&
          (workflow === "all" ||
            (point.cohortId || point.workflowType) === workflow),
      ),
    [points, scenario, workflow],
  );
  const replayVisible = useMemo(
    () => replayPrefix(visible, replayCount),
    [visible, replayCount],
  );
  const visibleIndexes = new Set(visible.map((point) => point.index));
  const replayByIndex = new Map(
    replayVisible.map((point) => [point.index, point] as const),
  );
  const timelineEntries = plan.length
    ? plan
        .filter((task) => visibleIndexes.has(task.index))
        .map((task) => replayByIndex.get(task.index) || task)
    : replayVisible;
  const scopedRevisions = scopedRevisionEvidence(revisions, replayVisible);
  const curve = useMemo(() => cumulativePoints(replayVisible), [replayVisible]);
  const memoryReuseIndex = firstMemoryReuseIndex(
    points.map((point) => ({
      index: point.index,
      pairId: point.pairId,
      workpackId: point.workpackId,
      generatedVersionIds: point.rsi.generatedVersionIds,
      generatedMatchVersions: point.rsi.generatedMatchVersions,
      usedVersionId: point.rsi.usedVersionId,
      usedMatchVersion: point.rsi.usedMatchVersion,
    })),
  );
  const selected =
    curve.find((point) => point.index === selectedIndex) ||
    curve.at(-1) ||
    null;
  useEffect(() => {
    if (!replayPlaying || replayCount == null || !visible.length) return;
    if (replayCount >= visible.length) {
      setReplayPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setReplayCount((current) =>
        Math.min((current ?? 0) + 1, visible.length),
      );
    }, replayIntervalMs);
    return () => window.clearTimeout(timer);
  }, [replayPlaying, replayCount, replayIntervalMs, visible.length]);
  useEffect(() => {
    if (replayCount == null || !replayVisible.length) return;
    setSelectedIndex(replayVisible.at(-1)?.index ?? null);
  }, [replayCount, replayVisible]);
  useEffect(() => {
    let active = true;
    setTaskDetail(null);
    setTaskError("");
    if (selected?.detailUrl) {
      void api<NonNullable<typeof taskDetail>>(selected.detailUrl)
        .then((payload) => {
          if (payload.experimentId !== metadata?.experimentId || payload.releaseId !== metadata?.releaseId)
            throw new Error("任务详情与当前发布上下文不一致");
          if (active) setTaskDetail(payload);
        })
        .catch((reason) => active && setTaskError(reason.message));
    }
    return () => { active = false; };
  }, [selected?.detailUrl, metadata?.experimentId, metadata?.releaseId]);
  const selectedTokenSaving =
    selected?.baseline.tokens && selected.rsi.tokens != null
      ? (selected.baseline.tokens - selected.rsi.tokens) /
        selected.baseline.tokens
      : null;
  const selectedLatencySaving =
    selected?.baseline.durationMs && selected.rsi.durationMs != null
      ? (selected.baseline.durationMs - selected.rsi.durationMs) /
        selected.baseline.durationMs
      : null;
  const selectedCostSaving =
    selected?.baseline.costUsd && selected.rsi.costUsd != null
      ? (selected.baseline.costUsd - selected.rsi.costUsd) /
        selected.baseline.costUsd
      : null;
  const baseline =
    detail?.summary?.baseline || detail?.summary?.arms?.no_learning || {};
  const rsi = detail?.summary?.rsi || detail?.summary?.arms?.online_rsi || {};
  const baselineTokens = baseline.tokens ?? baseline.totalTokens;
  const rsiTokens = rsi.tokens ?? rsi.totalTokens;
  const baselineLatency = baseline.latencyMs ?? baseline.durationMs;
  const rsiLatency = rsi.latencyMs ?? rsi.durationMs;
  const baselineCost = baseline.costUsd;
  const rsiCost = rsi.costUsd;
  const learning = detail?.summary?.learning || {};
  const scopeLast = curve.at(-1);
  const scopeBaselineTokens =
    scopeLast?.baselineCumulativeTokens ??
    (curve.length ? null : baselineTokens);
  const scopeRsiTokens =
    scopeLast?.rsiCumulativeTokens ?? (curve.length ? null : rsiTokens);
  const scopeBaselineLatency =
    scopeLast?.baselineCumulativeLatency ??
    (curve.length ? null : baselineLatency);
  const scopeRsiLatency =
    scopeLast?.rsiCumulativeLatency ?? (curve.length ? null : rsiLatency);
  const scopeBaselineCost =
    scopeLast?.baselineCumulativeCostUsd ??
    (curve.length ? null : baselineCost);
  const scopeRsiCost =
    scopeLast?.rsiCumulativeCostUsd ?? (curve.length ? null : rsiCost);
  const scopeTokenSaving =
    scopeLast?.tokenSavingRate ??
    (curve.length
      ? null
      : (detail?.summary?.tokenSaving ?? detail?.summary?.netTokenSaving));
  const scopeLatencySaving =
    scopeLast?.latencySavingRate ??
    (curve.length
      ? null
      : (detail?.summary?.latencySaving ?? detail?.summary?.netLatencySaving));
  const scopeCostSaving =
    scopeLast?.costSavingRate ??
    (curve.length ? null : detail?.summary?.costSaving);
  const scopeBaselinePassed = replayVisible.filter(
    (point) => point.baseline.passed,
  ).length;
  const scopeRsiPassed = replayVisible.filter((point) => point.rsi.passed).length;
  const sumKnown = (values: Array<number | null | undefined>) =>
    values.some((value) => value == null)
      ? null
      : values.reduce<number>((total, value) => total + (value as number), 0);
  const scopeBaselineRequests =
    scopeLast?.baselineCumulativeRequests ??
    sumKnown(replayVisible.map((point) => point.baseline.modelRequests));
  const scopeRsiRequests =
    scopeLast?.rsiCumulativeRequests ??
    sumKnown(replayVisible.map((point) => point.rsi.modelRequests));
  const scopeRequestSaving = scopeLast?.requestSavingRate ?? null;
  const scopeBaselineTools = sumKnown(replayVisible.map((point) => point.baseline.toolCalls));
  const scopeRsiTools = sumKnown(replayVisible.map((point) => point.rsi.toolCalls));
  const scopeBaselineAccuracy = scopeLast?.baselineCumulativeAccuracy ?? null;
  const scopeRsiAccuracy = scopeLast?.rsiCumulativeAccuracy ?? null;
  const scopeFast = replayVisible.filter(
    (point) => point.rsi.planningPath === "fast",
  ).length;
  const scopeFastRate = replayVisible.length ? scopeFast / replayVisible.length : null;
  const executionStageRows = [
    ["read_selection_and_binding", "读取选择", "选择当前资料、字段或检索范围"],
    ["compute_selection_and_binding", "计算选择", "选择聚合、关联、比较与参数绑定"],
    ["mixed_tool_decision", "混合决策", "同次响应包含多类工具或无法单独归类"],
    ["report_composition", "报告组合", "组织并提交有证据的业务报告"],
  ] as const;
  const aggregateExecutionStages = (arm: "baseline" | "rsi") => {
    const totals: Record<string, ExecutionStageMetric> = {};
    executionStageRows.forEach(([key]) => {
      const rows = replayVisible.map((point) => point[arm].executionStages?.[key]);
      totals[key] = {
        requests: rows.reduce((sum, row) => sum + (row?.requests || 0), 0),
        inputTokens: rows.reduce((sum, row) => sum + (row?.inputTokens || 0), 0),
        outputTokens: rows.reduce((sum, row) => sum + (row?.outputTokens || 0), 0),
        usageComplete: rows.every((row) => row?.usageComplete !== false),
      };
    });
    return totals;
  };
  const baselineExecutionStages = replayVisible.length
    ? aggregateExecutionStages("baseline")
    : baseline.executionStages || {};
  const rsiExecutionStages = replayVisible.length
    ? aggregateExecutionStages("rsi")
    : rsi.executionStages || {};
  const executionRequests = (stages: Record<string, ExecutionStageMetric>) =>
    executionStageRows.reduce(
      (total, [key]) => total + (stages[key]?.requests || 0),
      0,
    );
  const visibleExecutionStageRows = executionStageRows.filter(
    ([key]) =>
      (baselineExecutionStages[key]?.requests || 0) > 0 ||
      (rsiExecutionStages[key]?.requests || 0) > 0,
  );
  const baselineOtherRequests =
    scopeBaselineRequests == null
      ? null
      : Math.max(0, scopeBaselineRequests - executionRequests(baselineExecutionStages));
  const rsiOtherRequests =
    scopeRsiRequests == null
      ? null
      : Math.max(0, scopeRsiRequests - executionRequests(rsiExecutionStages));

  const scopeG0 = replayVisible.reduce(
    (total, point) => total + (point.rsi.generatedVersionIds?.length || 0),
    0,
  );
  const scopeM0 = replayVisible.reduce(
    (total, point) => total + (point.rsi.generatedMatchVersions?.length || 0),
    0,
  );
  const actualGraphUse = detail?.summary?.actualGraphUse;
  const scopeActualGraphUse = replayVisible.length === points.length
    ? actualGraphUse
    : null;
  const scopeVersionUses = replayVisible.filter(
    (point) => Boolean(point.rsi.usedVersionId),
  ).length;
  const graphRevisions = scopedRevisions.filter((revision) =>
    revisionIsAuditable(revision, "graph"),
  );
  const matchingRevisions = scopedRevisions.filter((revision) =>
    revisionIsAuditable(revision, "matching"),
  );
  const usedRevisions = scopedRevisions.filter(
    (revision) =>
      (revisionIsAuditable(revision, "graph") ||
        revisionIsAuditable(revision, "matching")) &&
      Boolean(revision.subsequentUses?.some((use) => use.runId)),
  );
  const completedPairs = replayVisible.filter(
    (point) => point.baseline.runId && point.rsi.runId,
  ).length;
  const failedBaseline = replayVisible.filter(
    (point) => point.baseline.runId && !point.baseline.passed,
  ).length;
  const failedRsi = replayVisible.filter(
    (point) => point.rsi.runId && !point.rsi.passed,
  ).length;
  const incompleteUsage = replayVisible.filter(
    (point) =>
      point.baseline.usageComplete === false ||
      point.rsi.usageComplete === false,
  ).length;
  const selectedCohort = workflow === "all"
    ? undefined
    : cohortSummaries.find((cohort) => cohort.cohortId === workflow);
  const scopeQualityKnown =
    replayVisible.length > 0 &&
    replayVisible.every(
      (point) =>
        typeof point.baseline.passed === "boolean" &&
        typeof point.rsi.passed === "boolean" &&
        point.baseline.usageComplete === true &&
        point.rsi.usageComplete === true,
    );
  const scopeRsiQualityPassed =
    scopeQualityKnown && scopeRsiPassed === replayVisible.length;
  const scopeCostConclusionAllowed = scopeAllowsCostClaims(
    replayVisible,
    releaseCostConclusionAllowed,
    isAttribution && selectedCohort?.costConclusionAllowed === true,
  );
  const scopeEfficiencyVisible =
    scopeCostConclusionAllowed || scopeRsiQualityPassed;
  const efficiencyPrefix = scopeCostConclusionAllowed ? "节省" : "本组减少";
  const claimRestriction =
    incompleteUsage > 0
      ? {
          title: "当前范围 usage 不完整",
          detail: "至少一个保存运行缺少完整 token usage，只保留已知绝对值和失败记录。",
        }
      : !scopeQualityKnown
        ? {
            title: "当前范围缺少完整质量结果",
            detail: "至少一个运行失败或尚未完成评分，暂不绘制效率变化。",
          }
        : {
            title: "在线 RSI 尚未完成当前范围全部任务",
            detail: "保留两臂绝对成本、准确率和失败，暂不绘制效率变化。",
          };

  return (
    <main className="analysis-page">
      <header className="analysis-heading analysis-heading-compact">
        <div>
          <h1>数据分析</h1>
          <p>同一冻结测试组中的质量、成本、经验修订与真实运行证据。</p>
        </div>
      </header>

      {error && (
        <p className="analysis-error" role="alert">
          {error}。未加载其他实验补足指标。
        </p>
      )}
      {(loading || detailLoading) && (
        <section className="analysis-loading">
          <LoaderCircle size={22} />
          <p>正在读取保存的测试组和逐任务计量…</p>
        </section>
      )}

      {metadata && !detailLoading && (
        <>
          <section className="analysis-release-bar" aria-label="当前发布测试组">
            <label className="dataset-picker">
              <span>当前测试组</span>
              <select aria-label="选择测试组" value={datasetId} disabled={loading || !datasets.length} onChange={(event) => setDatasetId(event.target.value)}>
                {!datasets.length && <option value="">暂无可用测试组</option>}
                {datasets.map((dataset) => (
                  <option key={dataset.datasetId} value={dataset.datasetId}>{dataset.displayName} · {dataset.status}</option>
                ))}
              </select>
            </label>
            <span className={`analysis-status ${metadata.status}`}>{metadata.status === "candidate" ? "候选" : metadata.status}</span>
            {points.length > 0 ? (
              <div className="analysis-release-result">
                <strong>在线 RSI {number(rsi.passed)}/{number(rsi.attempts)}</strong>
                <span>不学习臂 {number(baseline.passed)}/{number(baseline.attempts)}</span>
                <small>在线 RSI 在本组质量更高 · 成本包含全部失败与恢复</small>
              </div>
            ) : (
              <div className="analysis-release-result"><strong>尚未产生保存结果</strong></div>
            )}
          </section>

          {points.length > 0 && (scenarios.length > 1 || workflows.length > 1) && (
            <section className="analysis-filters" aria-label="分析筛选">
              {scenarios.length > 1 && (
                <label>业务场景<select aria-label="筛选业务场景" value={scenario} onChange={(event) => { setScenario(event.target.value); setWorkflow("all"); setSelectedIndex(null); setReplayCount(null); setReplayPlaying(false); }}>
                  <option value="all">全部场景</option>
                  {scenarios.map((item) => <option key={item} value={item}>{scenarioNames[item] || item}</option>)}
                </select></label>
              )}
              {workflows.length > 1 && (
                <label>任务类型<select aria-label="筛选任务类型" value={workflow} onChange={(event) => { setWorkflow(event.target.value); setSelectedIndex(null); setReplayCount(null); setReplayPlaying(false); }}>
                  <option value="all">全部任务类型</option>
                  {workflows.map((item) => <option key={item.id} value={item.id}>{item.label.replaceAll("-", " ")}</option>)}
                </select></label>
              )}
            </section>
          )}

          {points.length > 0 && (
            <section className="analysis-replay" aria-label="保存结果回放" title="按真实任务顺序播放保存结果，不会重新调用模型">
              <div aria-live="polite"><span>保存结果回放</span><strong>{replayVisible.length} / {visible.length}</strong></div>
              <progress max={Math.max(visible.length, 1)} value={replayVisible.length} aria-label="回放进度" />
              <div className="analysis-replay-controls">
                <button
                  type="button"
                  onClick={() => {
                    if (replayCount == null || replayCount >= visible.length)
                      setReplayCount(1);
                    setReplayPlaying(true);
                  }}
                  disabled={!visible.length || replayPlaying}
                  aria-label="播放保存结果"
                >
                  <Play size={14} />播放
                </button>
                <button
                  type="button"
                  onClick={() => setReplayPlaying(false)}
                  disabled={!replayPlaying}
                  aria-label="暂停回放"
                >
                  <Pause size={14} />暂停
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (!visible.length) return;
                    setReplayCount(1);
                    setReplayPlaying(true);
                  }}
                  disabled={!visible.length}
                  aria-label="重播保存结果"
                >
                  <RotateCcw size={14} />重播
                </button>
                <label>
                  速度
                  <select
                    aria-label="回放速度"
                    value={replayIntervalMs}
                    onChange={(event) =>
                      setReplayIntervalMs(Number(event.target.value))
                    }
                  >
                    <option value={800}>快 · 0.8 秒</option>
                    <option value={1500}>标准 · 1.5 秒</option>
                    <option value={2500}>慢 · 2.5 秒</option>
                  </select>
                </label>
                <button
                  type="button"
                  onClick={() => {
                    setReplayPlaying(false);
                    setReplayCount(null);
                    setSelectedIndex(visible.at(-1)?.index ?? null);
                  }}
                  disabled={!visible.length || (replayCount == null && !replayPlaying)}
                >
                  最终结果
                </button>
              </div>
            </section>
          )}

          {points.length > 0 && (
            <nav className="analysis-view-tabs" aria-label="分析演示标签页" role="tablist">
              {analysisViews.map((view) => (
                <button key={view.id} type="button" role="tab" title={view.description} aria-label={`${view.label}：${view.description}`} aria-selected={analysisView === view.id} aria-controls={`analysis-view-${view.id}`} className={analysisView === view.id ? "active" : ""} onClick={() => setAnalysisView(view.id)}>
                  <strong>{view.label}</strong>
                </button>
              ))}
            </nav>
          )}

          {analysisView === "results" && points.length > 0 && (
            <section id="analysis-view-results" role="tabpanel" className="analysis-view-panel">
              <div className="analysis-primary-kpis" aria-label="当前筛选核心指标">
                <article className="quality"><ShieldCheck size={20} /><small>业务质量</small><strong>{number(scopeBaselinePassed)}/{curve.length} → {number(scopeRsiPassed)}/{curve.length}</strong><span>结构化任务准确率 {percent(scopeBaselineAccuracy)} → {percent(scopeRsiAccuracy)}</span></article>
                <article className="efficiency"><Activity size={20} /><small>执行效率</small><dl>
                  <div><dt>累计 token</dt><dd>{number(scopeBaselineTokens)} → {number(scopeRsiTokens)}</dd></div>
                  <div><dt>大模型调用次数</dt><dd>{number(scopeBaselineRequests)} → {number(scopeRsiRequests)}</dd></div>
                </dl><span>{scopeEfficiencyVisible ? `Token ${efficiencyPrefix} ${percent(scopeTokenSaving)} · 请求${efficiencyPrefix} ${percent(scopeRequestSaving)}` : claimRestriction.title}</span></article>
                <article className="evolution"><Sparkles size={20} /><small>{isAttribution ? "递归进化证据" : "经验复用"}</small><strong>{isAttribution ? `${graphRevisions.length} 次 G · ${matchingRevisions.length} 次 M 修订` : `${number(scopeFast)} 次复用`}</strong><span>{isAttribution ? `${usedRevisions.length} 个修订已有后续任务实际使用` : `当前范围命中 ${percent(scopeFastRate)}`}</span></article>
              </div>
              <dl className="analysis-secondary-kpis" aria-label="补充计量">
                <div><BadgeDollarSign size={15} /><dt>累计模型成本估算</dt><dd>{money(scopeBaselineCost)} → {money(scopeRsiCost)}</dd></div>
                <div><Clock3 size={15} /><dt>累计串行延迟</dt><dd>{duration(scopeBaselineLatency)} → {duration(scopeRsiLatency)}</dd></div>
                <div><Route size={15} /><dt>实际图执行</dt><dd>{scopeActualGraphUse ? `${number(scopeActualGraphUse.hits)}/${number(scopeActualGraphUse.attempts)}` : `${number(scopeVersionUses)} 项版本选择`}</dd></div>
              </dl>
              {selected && (
                <article className="analysis-current-task">
                  <div>
                    <small>当前播放任务 · 第 {selected.index} 项</small>
                    <h2>{selected.title || selected.workflowType.replaceAll("-", " ")}</h2>
                    <p>{selected.opportunity || scenarioNames[selected.scenario] || selected.scenario}</p>
                  </div>
                  <dl>
                    <div><dt>{labels.baseline}</dt><dd>{selected.baseline.passed ? "通过" : "未通过"} · {number(selected.baseline.modelRequests)} 次请求</dd></div>
                    <div><dt>{labels.rsi}</dt><dd>{selected.rsi.passed ? "通过" : "未通过"} · {number(selected.rsi.modelRequests)} 次请求</dd></div>
                    <div><dt>本任务 token</dt><dd>{number(selected.baseline.tokens)} → {number(selected.rsi.tokens)}</dd></div>
                  </dl>
                  <button type="button" onClick={() => setAnalysisView("audit")}>查看报告与真实轨迹</button>
                </article>
              )}
            </section>
          )}

          {analysisView === "evolution" && isAttribution && (
            <section id="analysis-view-evolution" role="tabpanel" className="analysis-section analysis-attribution analysis-view-panel">
              <header>
                <div>
                  <p className="eyebrow">LEARNING ATTRIBUTION</p>
                  <h2>{attributionTimelineHeading(timelineEntries.length)}</h2>
                </div>
                <p>
                  机会标签来自冻结协议。只有保存的实质 diff
                  和后续运行实际使用，才标为修订与进化证据。
                </p>
              </header>
              <div className="analysis-arm-definition" aria-label="实验两臂">
                <div>
                  <span>A</span>
                  <strong>{labels.baseline}</strong>
                  <small>每次重新规划与编译，不读写跨任务经验</small>
                </div>
                <div>
                  <span>B</span>
                  <strong>{labels.rsi}</strong>
                  <small>从空经验开始，只学习此前正常任务</small>
                </div>
              </div>
              <ol className="analysis-timeline">
                {timelineEntries.map((entry) => {
                  const point = "workpackId" in entry ? entry : undefined;
                  const signals = point
                    ? evolutionSignals(
                        {
                          pairId: point.pairId,
                          workpackId: point.workpackId,
                          generatedVersionIds: point.rsi.generatedVersionIds,
                          generatedMatchVersions:
                            point.rsi.generatedMatchVersions,
                          usedVersionId: point.rsi.usedVersionId,
                          usedMatchVersion: point.rsi.usedMatchVersion,
                        },
                        scopedRevisions,
                      )
                    : null;
                  const revisionState = point
                    ? revisionVisualState(
                        { pairId: point.pairId, workpackId: point.workpackId },
                        scopedRevisions,
                      )
                    : null;
                  const memoryActivated = Boolean(
                    point && point.index === memoryReuseIndex,
                  );
                  const routineReuse = Boolean(
                    point &&
                    point.index !== 1 &&
                    !memoryActivated &&
                    !revisionState?.graphRevision &&
                    !revisionState?.matchingRevision &&
                    !revisionState?.verifiedLaterUse &&
                    !revisionState?.usesGraphRevision &&
                    !revisionState?.usesMatchingRevision &&
                    (signals?.usedGraph || signals?.usedMatching),
                  );
                  const evidence = signals
                    ? ([
                        signals.createdGraph && "保存 G 版本",
                        signals.createdMatching && "保存 M 版本",
                        revisionState?.graphRevision && "G 结构实质修订",
                        revisionState?.matchingRevision && "M 匹配实质修订",
                        revisionState?.usesGraphRevision && "后续实际执行修订 G",
                        revisionState?.usesMatchingRevision && "后续实际使用修订 M",
                        !revisionState?.usesGraphRevision &&
                          signals.usedGraph &&
                          "复用 G 版本",
                        !revisionState?.usesMatchingRevision &&
                          signals.usedMatching &&
                          "复用 M 版本",
                      ].filter(Boolean) as string[])
                    : [];
                  const timelineClassName = [
                    point ? "recorded" : "pending",
                    memoryActivated ? "memory-activated" : "",
                    routineReuse ? "routine-reuse" : "",
                    revisionState?.graphRevision ? "graph-evolution" : "",
                    revisionState?.matchingRevision ? "matching-evolution" : "",
                    revisionState?.verifiedLaterUse ? "verified-use" : "",
                    revisionState?.usesGraphRevision ||
                    revisionState?.usesMatchingRevision
                      ? "revision-use"
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <li
                      key={entry.index}
                      className={timelineClassName}
                      role={point ? "button" : undefined}
                      tabIndex={point ? 0 : undefined}
                      onKeyDown={(event) => {
                        if (point && (event.key === "Enter" || event.key === " ")) {
                          event.preventDefault(); setSelectedIndex(point.index);
                        }
                      }}
                      onClick={() => point && setSelectedIndex(point.index)}
                    >
                      <span className="analysis-timeline-index">
                        {entry.index}
                      </span>
                      <div>
                        <small>
                          {entry.opportunity ||
                            defaultOpportunityChain[entry.index - 1] ||
                            "任务机会"}
                        </small>
                        <strong>
                          {point?.title || entry.title || point?.workpackId}
                        </strong>
                        <p>
                          {evidence.length
                            ? evidence.join(" · ")
                            : point
                              ? "已保存运行，尚无可主张的 G/M 修订链"
                              : "待正式运行"}
                        </p>
                      </div>
                      <em>
                        {memoryActivated
                          ? "记忆已构建 · 首次复用"
                          : revisionState?.verifiedLaterUse
                          ? "已验证使用"
                          : point
                            ? point.baseline.runId && point.rsi.runId
                              ? "已配对"
                              : "未完成配对"
                            : "待运行"}
                      </em>
                    </li>
                  );
                })}
              </ol>
            </section>
          )}

          {analysisView === "evolution" && points.length > 0 && (
            <section id={!isAttribution ? "analysis-view-evolution" : undefined} role={!isAttribution ? "tabpanel" : undefined} className="analysis-section analysis-mechanism analysis-mechanism-panel">
              <Route size={20} />
              <p className="eyebrow">MECHANISM BOUNDARY</p>
              <h2>
                {isAttribution
                  ? "学习贡献与修订证据"
                  : `${metadata?.displayName || "该测试组"}展示 G0 形成与 Fast 复用`}
              </h2>
              {isAttribution ? (
                <>
                  <p>
                    当前保存结果包含 {number(scopeG0)} 个 G 版本、
                    {number(scopeM0)} 个 M 版本；
                    {scopeActualGraphUse
                      ? <>历史图实际执行 {number(scopeActualGraphUse.hits)}/{number(scopeActualGraphUse.attempts)}（{percent(scopeActualGraphUse.rate)}）</>
                      : <>当前回放前缀有 {number(scopeVersionUses)} 项历史版本选择记录；版本选择不等于严格图执行，执行状态请从“报告与轨迹”审计</>}
                    ；确认 {graphRevisions.length} 次 G 实质修订、
                    {matchingRevisions.length} 次 M 实质修订，其中 {usedRevisions.length} 个修订具有后续实际使用记录。
                  </p>
                  <dl>
                    <div><dt>G 修订</dt><dd>{graphRevisions.length}</dd></div>
                    <div><dt>M 修订</dt><dd>{matchingRevisions.length}</dd></div>
                    <div><dt>修订后使用</dt><dd>{usedRevisions.length}</dd></div>
                  </dl>
                </>
              ) : (
                <>
                  <p>当前回放前缀记录 {number(scopeG0)} 次 G0 形成和 {number(scopeFast)} 次 Fast 使用；没有实质结构 diff 时不称为递归进化。</p>
                  <dl>
                    <div><dt>Composition</dt><dd>{number(learning.composition)}</dd></div>
                    <div><dt>Fallback</dt><dd>{number(learning.fallback)}</dd></div>
                  </dl>
                </>
              )}
            </section>
          )}

          {analysisView === "cost" && points.length > 0 && (
            <section id="analysis-view-cost" role="tabpanel" className="analysis-section analysis-view-panel">
              <header>
                <div>
                  <p className="eyebrow">TASK GROWTH / ABSOLUTE COST</p>
                  <h2>任务增加时的累计开销</h2>
                </div>
                <p>
                  两条线始终使用相同任务范围。成本按保存的输入/输出 token
                  与价格快照估算；串行延迟保留真实等待、失败与恢复耗时。
                </p>
              </header>
              <div className="analysis-chart-grid analysis-chart-grid-cost">
                <article>
                  <h3>累计 token</h3>
                  <PolylineChart
                    points={curve}
                    metric="tokens"
                    labels={labels}
                    onSelect={(point) => setSelectedIndex(point.index)}
                  />
                </article>
                <article>
                  <h3>累计串行 latency</h3>
                  <PolylineChart
                    points={curve}
                    metric="latency"
                    labels={labels}
                    onSelect={(point) => setSelectedIndex(point.index)}
                  />
                </article>
              </div>
              <details className="analysis-cost-detail">
                <summary>查看累计模型成本估算（USD） · {money(scopeBaselineCost)} → {money(scopeRsiCost)}</summary>
                <PolylineChart points={curve} metric="cost" labels={labels} onSelect={(point) => setSelectedIndex(point.index)} />
              </details>
            </section>
          )}

          {analysisView === "operations" && points.length > 0 && (
            <section id="analysis-view-operations" role="tabpanel" className="analysis-section analysis-view-panel">
              <header>
                <div>
                  <p className="eyebrow">MODEL CALLS / TASK ACCURACY</p>
                  <h2>大模型调用与任务准确率</h2>
                </div>
                <p>
                  准确率按当前范围内结构化校验通过数除以已评测任务数计算，失败保留在分母；它不是
                  Judge 分数或模型置信度。
                </p>
              </header>
              <div className="analysis-chart-grid">
                <article>
                  <h3>累计大模型调用次数</h3>
                  <PolylineChart
                    points={curve}
                    metric="requests"
                    labels={labels}
                    onSelect={(point) => setSelectedIndex(point.index)}
                  />
                </article>
                <article>
                  <h3>累计任务准确率</h3>
                  <PolylineChart
                    points={curve}
                    metric="accuracy"
                    labels={labels}
                    onSelect={(point) => setSelectedIndex(point.index)}
                  />
                </article>
              </div>
            </section>
          )}

          {analysisView === "operations" && isAttribution && points.length > 0 && (
            <section className="analysis-section analysis-decision-stages" aria-label="模型决策请求分解">
              <header>
                <div>
                  <p className="eyebrow">MODEL DECISION BREAKDOWN</p>
                  <h2>模型决策请求分解</h2>
                </div>
                <p>
                  按保存模型响应实际选择的工具类型归类。这里只展示请求绝对值；失败重试和最终报告请求均保留。
                </p>
              </header>
              <div className="analysis-stage-grid">
                {visibleExecutionStageRows.map(([key, label, description]) => (
                  <article key={key}>
                    <small>{label}</small>
                    <div>
                      <span>{labels.baseline}</span>
                      <strong>{number(baselineExecutionStages[key]?.requests)}</strong>
                    </div>
                    <div>
                      <span>{labels.rsi}</span>
                      <strong>{number(rsiExecutionStages[key]?.requests)}</strong>
                    </div>
                    <p>{description}</p>
                  </article>
                ))}
              </div>
              <p className="analysis-stage-note">
                四类合计只覆盖 execute 阶段。计划、匹配及其他模型请求另有 {number(baselineOtherRequests)} / {number(rsiOtherRequests)} 次，
                已包含在页面顶部的总请求数中。
                {metadata.status === "candidate"
                  ? " 当前仍是候选结果；在线 RSI 完成当前范围全部任务时，页面展示本固定测试组的实际效率变化，不外推到其他场景。"
                  : " 该分解用于解释请求发生在哪里，不把某一类别数量直接换算为收益。"}
              </p>
            </section>
          )}

          {analysisView === "cost" && points.length > 0 && (
            <section className="analysis-section analysis-saving-layout analysis-saving-single">
              <article>
                <header>
                  <p className="eyebrow">EFFICIENCY CHANGE</p>
                  <h2>累计效率变化</h2>
                </header>
                {scopeEfficiencyVisible ? (
                  <>
                    <PolylineChart
                      points={curve}
                      metric="saving"
                      labels={labels}
                      onSelect={(point) => setSelectedIndex(point.index)}
                    />
                    {!scopeCostConclusionAllowed && (
                      <p className="analysis-observation-note">在线 RSI 在当前固定范围全部通过；曲线展示本组真实变化，不代表跨场景普遍收益。</p>
                    )}
                  </>
                ) : (
                  <div className="analysis-empty">
                    <ShieldCheck size={20} />
                    <strong>{claimRestriction.title}</strong>
                    <p>{claimRestriction.detail}</p>
                  </div>
                )}
              </article>
            </section>
          )}

          {analysisView === "operations" && points.length > 0 && (
            <section className="analysis-reliability" aria-label="可靠性与失败">
              <div>
                <ShieldCheck size={18} />
                <span>已完成配对</span>
                <strong>
                  {completedPairs}/{replayVisible.length}
                </strong>
              </div>
              <div>
                <span>{labels.baseline} 未通过</span>
                <strong>{failedBaseline}</strong>
              </div>
              <div>
                <span>{labels.rsi} 未通过</span>
                <strong>{failedRsi}</strong>
              </div>
              <div>
                <span>usage 不完整</span>
                <strong>{incompleteUsage}</strong>
              </div>
              <p>
                {replayVisible.length === points.length && detail?.summary?.reliability?.note
                  ? detail.summary.reliability.note
                  : `当前筛选保留 ${completedPairs} 个已运行配对、全部失败、工具错误和串行耗时；未知 token 不按 0 补齐。`}
              </p>
            </section>
          )}

          {analysisView === "audit" && selected && (
            <section id="analysis-view-audit" role="tabpanel" className="analysis-focus analysis-view-panel" aria-live="polite">
              <header>
                <div><small>当前任务报告</small><h2>第 {selected.index} 项 · {selected.title || selected.workflowType.replaceAll("-", " ")}</h2></div>
                <span>{scenarioNames[selected.scenario] || selected.scenario} · {selected.opportunity || `R${selected.round || "—"}`}</span>
              </header>
              {taskError && <p role="alert">{taskError}</p>}
              {taskDetail && (
                <div className="analysis-task-business">
                  <div className="analysis-task-business-head">
                    <div><small>业务问题与输入资料</small><strong>{selected.title || selected.workpackId}</strong></div>
                    <div className="analysis-run-links">{taskDetail.inputs.map((input) => <a key={input.id} href={input.download}><FileDown size={13} />{input.name}</a>)}</div>
                  </div>
                  <details className="analysis-request-detail"><summary>查看完整业务问题</summary><p>{taskDetail.task.task}</p></details>
                  <div className="analysis-report-comparison">
                    {(["baseline", "rsi"] as const).map((arm) => {
                      const run = selected[arm];
                      const url = reportUrl(metadata, arm, run);
                      const trace = traceUrl(metadata, arm, run);
                      return (
                        <article key={arm} className={arm}>
                          <header><div><small>{labels[arm]}</small><h3>保存业务成果</h3></div><em>{run.passed ? "结构化校验通过" : run.status || "未通过"}</em></header>
                          <p>{taskDetail.runs[arm]?.submission?.summary || "未交付业务报告"}</p>
                          <dl>
                            <div><dt>Token</dt><dd>{number(run.tokens)}</dd></div><div><dt>模型请求</dt><dd>{number(run.modelRequests)}</dd></div>
                            <div><dt>串行时间</dt><dd>{duration(run.durationMs)}</dd></div><div><dt>工具错误</dt><dd>{number(run.toolErrors)}</dd></div>
                          </dl>
                          <div className="analysis-run-links">
                            {url && <a href={url} target="_blank" rel="noreferrer"><FileDown size={13} />业务报告</a>}
                            {selected.detailUrl && <a href={`${selected.detailUrl}/runs/${arm}/selection`}>结构化清单</a>}
                            {trace && <a href={trace} target="_blank" rel="noreferrer"><GitBranch size={13} />真实轨迹</a>}
                          </div>
                          <details className="analysis-trace-detail"><summary>技术审计：真实工具调用</summary><ol>{taskDetail.runs[arm]?.toolTrace?.map((item, index) => (
                            <li key={index}>{({ workspace_preview_rows: "读取资料", workspace_map_fields: "选择数据字段", workspace_aggregate_keyed: "按业务对象汇总", workspace_align_keyed: "关联当前资料", workspace_derive_values: "计算派生金额", workspace_compare_values: "检查业务条件", workspace_select_missing: "检查资料完整性", workspace_filter_rows: "筛选业务记录", workspace_sort_rows: "排序业务记录", workspace_publish_report: "提交报告" } as Record<string, string>)[item.tool] || item.tool}{item.executor === "graph" ? " · 图执行" : " · 模型决策"} · {item.ok ? "完成" : "失败，已计入开销"}</li>
                          ))}</ol></details>
                        </article>
                      );
                    })}
                  </div>
                </div>
              )}
              <article className="analysis-audit-learning">
                <div><small>{isAttribution ? "本任务学习证据" : "RSI 执行路径"}</small><strong>{scopeEfficiencyVisible ? `token ${percent(selectedTokenSaving)} · latency ${percent(selectedLatencySaving)}` : "当前范围暂不展示效率变化"}</strong></div>
                <p>{selected.rsi.usedVersionId ? `记录选择 G ${selected.rsi.usedVersionId}；严格图执行见真实轨迹` : "未记录图版本选择"} · {selected.rsi.usedMatchVersion != null ? `记录选择 M ${selected.rsi.usedMatchVersion}` : "未记录匹配版本选择"}</p>
                <code>{selected.workpackId}</code>
              </article>
              {isAttribution && scopedRevisions.some((revision) => revision.sourcePairId === selected.pairId || revision.sourceTaskId === selected.workpackId) && (
                <details className="analysis-revision-audit"><summary>技术审计：本任务产生的 G / M diff</summary>
                  {scopedRevisions.filter((revision) => revision.sourcePairId === selected.pairId || revision.sourceTaskId === selected.workpackId).map((revision, index) => (
                    <div key={index}><strong>{revision.graphChanged ? "G 结构有实质差异" : "G 未变化"} · {revision.matchingChanged ? "M 匹配描述有实质差异" : "M 未变化"}</strong><span>后续实际使用 {revision.subsequentUses?.length || 0} 次</span><pre>{JSON.stringify(revision, null, 2)}</pre></div>
                  ))}
                </details>
              )}
            </section>
          )}

          {analysisView === "audit" && isAttribution && cohortSummaries.length > 0 && (
            <details className="analysis-section analysis-cohorts analysis-audit-section">
              <summary><span>技术审计：冻结业务子簇</span><small>{cohortSummaries.length} 个预先固定子簇</small></summary>
              <div className="analysis-cohort-grid">
                {cohortSummaries.map((cohort) => {
                  const cohortScenario = points.find((point) => cohort.pairIds.includes(point.pairId || point.workpackId))?.scenario || "";
                  return (
                    <button type="button" key={cohort.cohortId} className={workflow === cohort.cohortId ? "selected" : ""} aria-pressed={workflow === cohort.cohortId} onClick={() => { setScenario(cohortScenario || "all"); setWorkflow(cohort.cohortId); setSelectedIndex(null); }}>
                      <span>{scenarioNames[cohortScenario] || "未标注场景"} · {cohort.pairIds.length} 项 · {cohort.pairIds.at(0) || "—"}–{cohort.pairIds.at(-1) || "—"}</span>
                      <strong>{cohort.label}</strong><b>{cohort.baseline.passed}/{cohort.baseline.attempts} → {cohort.rsi.passed}/{cohort.rsi.attempts}</b>
                      <dl><div><dt>Token</dt><dd>{number(cohort.baseline.tokens)} → {number(cohort.rsi.tokens)}</dd></div><div><dt>模型请求</dt><dd>{number(cohort.baseline.modelRequests)} → {number(cohort.rsi.modelRequests)}</dd></div><div><dt>串行时间</dt><dd>{duration(cohort.baseline.durationMs)} → {duration(cohort.rsi.durationMs)}</dd></div><div><dt>工具错误</dt><dd>{number(cohort.baseline.toolErrors)} → {number(cohort.rsi.toolErrors)}</dd></div></dl>
                      <em>{cohort.costConclusionAllowed ? `同质量子簇：token 减少 ${percent(cohort.tokenSaving)}` : "保留质量差异和绝对开销"}</em>
                    </button>
                  );
                })}
              </div>
            </details>
          )}

          {analysisView === "audit" && detail?.maintenanceDiagnostics && (
            <details className="analysis-section analysis-maintenance analysis-audit-section">
              <summary><span>技术审计：发布后维护验证</span><small>跨 runtime · 独立诊断 · 不进入当前 KPI</small></summary>
              <div className="analysis-maintenance-boundary"><ShieldCheck size={17} /><p>该诊断仅验证阻塞修复，不进入当前发布 KPI、累计曲线、成功率或收益，不能作为正式收益率或普遍性能结论。</p></div>
              <div className="analysis-maintenance-grid">
                {([
                  ["原正式运行", detail.maintenanceDiagnostics.formal, "formal"],
                  ["修复后诊断", detail.maintenanceDiagnostics.validated, "validated"],
                ] as const).map(([title, run, kind]) => (
                  <article key={kind} className={kind}><small>{title}</small><strong>{run.evaluationStatus === "passed" ? "结构化评测通过" : run.status || "状态未知"}</strong>
                    <dl><div><dt>请求</dt><dd>{number(run.modelRequests)}</dd></div><div><dt>Token</dt><dd>{number(run.tokens)}</dd></div><div><dt>串行时间</dt><dd>{duration(run.latencyMs)}</dd></div><div><dt>工具错误</dt><dd>{number(run.toolErrors)}</dd></div></dl>
                    <code>{run.runtimeRevision}</code><div className="analysis-run-links">{run.reportUrl && <a href={run.reportUrl} target="_blank" rel="noreferrer"><FileDown size={13} />报告</a>}{run.runUrl && <a href={run.runUrl} target="_blank" rel="noreferrer"><GitBranch size={13} />轨迹</a>}{run.artifactUrl && <a href={run.artifactUrl} target="_blank" rel="noreferrer"><ArrowUpRight size={13} />诊断收据</a>}</div>
                  </article>
                ))}
              </div>
              <details className="analysis-maintenance-audit"><summary>首个配置失败诊断与解释边界</summary><p>首次诊断错误关闭跨任务学习，相关请求、token、延迟和工具错误均保留在独立诊断工件中。</p></details>
            </details>
          )}

          {analysisView === "audit" && points.length > 0 && (
            <details className="analysis-section analysis-task-ledger">
              <summary>
                <span>技术审计：逐任务真实运行与报告</span>
                <small>{curve.length} 个任务 · 失败和空用量完整保留</small>
              </summary>
              <div className="analysis-table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>序号 / 任务</th>
                      <th>机会</th>
                      <th>{labels.baseline}</th>
                      <th>{labels.rsi}</th>
                      <th>G / M 证据</th>
                      <th>报告 / 轨迹</th>
                    </tr>
                  </thead>
                  <tbody>
                    {curve.map((point) => {
                      const signals = evolutionSignals(
                        {
                          pairId: point.pairId,
                          workpackId: point.workpackId,
                          generatedVersionIds: point.rsi.generatedVersionIds,
                          generatedMatchVersions:
                            point.rsi.generatedMatchVersions,
                          usedVersionId: point.rsi.usedVersionId,
                          usedMatchVersion: point.rsi.usedMatchVersion,
                        },
                        scopedRevisions,
                      );
                      const revisionState = revisionVisualState(
                        {
                          pairId: point.pairId,
                          workpackId: point.workpackId,
                        },
                        scopedRevisions,
                      );
                      const evidence = revisionState.graphRevision
                        ? revisionState.verifiedLaterUse
                          ? "G 实质修订 · 已验证使用"
                          : "G 结构实质修订"
                        : revisionState.matchingRevision
                          ? revisionState.verifiedLaterUse
                            ? "M 实质修订 · 已验证使用"
                            : "M 匹配实质修订"
                          : revisionState.usesGraphRevision ||
                              revisionState.usesMatchingRevision
                            ? "后续实际使用修订"
                            : signals.usedGraph || signals.usedMatching
                              ? "复用已有经验"
                              : signals.createdGraph || signals.createdMatching
                                ? "创建经验"
                                : "尚无修订证据";
                      const baselineTrace = traceUrl(
                          metadata,
                          "baseline",
                          point.baseline,
                        ),
                        rsiTrace = traceUrl(metadata, "rsi", point.rsi);
                      return (
                        <tr
                          key={point.index}
                          className={
                            selectedIndex === point.index ? "selected" : ""
                          }
                          onClick={() => setSelectedIndex(point.index)}
                        >
                          <td>
                            <strong>#{point.index}</strong>
                            <small>{point.title || point.workpackId}</small>
                          </td>
                          <td>
                            {point.opportunity ||
                              scenarioNames[point.scenario] ||
                              point.scenario}
                            <small>
                              {point.workflowType.replaceAll("-", " ")}
                            </small>
                          </td>
                          <td>
                            {number(point.baseline.tokens)} ·{" "}
                            {money(point.baseline.costUsd)}
                            <small>
                              {duration(point.baseline.durationMs)} ·{" "}
                              {point.baseline.passed ? "通过" : "未通过"}
                            </small>
                          </td>
                          <td>
                            {number(point.rsi.tokens)} ·{" "}
                            {money(point.rsi.costUsd)}
                            <small>
                              {duration(point.rsi.durationMs)} ·{" "}
                              {point.rsi.passed ? "通过" : "未通过"}
                            </small>
                          </td>
                          <td>
                            <span
                              className={`path-badge ${revisionState.graphRevision ? "graph-revision" : revisionState.matchingRevision ? "matching-revision" : revisionState.usesGraphRevision || revisionState.usesMatchingRevision ? "revision-use" : point.rsi.planningPath || "unknown"}`}
                            >
                              {evidence}
                            </span>
                          </td>
                          <td>
                            <div className="analysis-ledger-links">
                              {reportUrl(
                                metadata,
                                "baseline",
                                point.baseline,
                              ) && (
                                <a
                                  href={reportUrl(
                                    metadata,
                                    "baseline",
                                    point.baseline,
                                  )}
                                  target="_blank"
                                  rel="noreferrer"
                                  title={`${labels.baseline}报告`}
                                >
                                  <FileDown size={12} />不学习报告
                                </a>
                              )}
                              {reportUrl(metadata, "rsi", point.rsi) && (
                                <a
                                  href={reportUrl(metadata, "rsi", point.rsi)}
                                  target="_blank"
                                  rel="noreferrer"
                                  title={`${labels.rsi}报告`}
                                >
                                  <FileDown size={12} />RSI 报告
                                </a>
                              )}
                              {baselineTrace && (
                                <a
                                  href={baselineTrace}
                                  target="_blank"
                                  rel="noreferrer"
                                  title={`${labels.baseline}轨迹`}
                                >
                                  <GitBranch size={12} />不学习轨迹
                                </a>
                              )}
                              {rsiTrace && (
                                <a
                                  href={rsiTrace}
                                  target="_blank"
                                  rel="noreferrer"
                                  title={`${labels.rsi}轨迹`}
                                >
                                  <GitBranch size={12} />RSI 轨迹
                                </a>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </details>
          )}

          {analysisView === "audit" && (metadata.limitations?.length || detail?.limitations?.length) ? (
            <details className="analysis-limitations">
              <summary>数据限制与解释边界</summary>
              <ul>
                {(metadata.limitations || detail?.limitations || []).map(
                  (item) => (
                    <li key={item}>{item}</li>
                  ),
                )}
              </ul>
            </details>
          ) : null}
        </>
      )}

      {!loading && !detailLoading && !metadata && !error && (
        <section className="analysis-empty">
          <Gauge size={22} />
          <h2>暂无可分析的保存测试组</h2>
          <p>后续结果写入分析清单后，会自动出现在测试组选项中。</p>
        </section>
      )}
    </main>
  );
}
