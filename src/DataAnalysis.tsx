import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BadgeDollarSign,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  FileDown,
  Gauge,
  GitBranch,
  Layers3,
  LoaderCircle,
  Route,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { api } from "./api";
import {
  attributionTimelineHeading,
  cumulativePoints,
  evolutionSignals,
  normalizedRevisionEvidence,
  releaseAllowsCostClaims,
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
const rate = (value?: number | null) =>
  value == null ? "—" : `$${value.toFixed(value < 1 ? 3 : 2)}/M`;
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
        round: asNumber(row.round) ?? asNumber(curveRow.round) ?? undefined,
        status: asString(row.status),
        baseline,
        rsi,
      } satisfies Point;
    })
    .filter((point) => Number.isFinite(point.index))
    .sort((a, b) => a.index - b.index);
}

function protocolLabel(value: Detail["protocol"]): string {
  if (typeof value === "string") return value;
  if (!value) return "未标注";
  return String(
    value.id || value.runtimeProtocol || value.mode || "冻结成对协议",
  );
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

export default function DataAnalysis() {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [scenario, setScenario] = useState("all");
  const [workflow, setWorkflow] = useState("all");
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
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
  const timelineEntries = plan.length
    ? plan.map(
        (task) => points.find((point) => point.index === task.index) || task,
      )
    : points;
  const scenarios = useMemo(
    () => Array.from(new Set(points.map((point) => point.scenario))),
    [points],
  );
  const workflows = useMemo(
    () =>
      Array.from(
        new Set(
          points
            .filter(
              (point) => scenario === "all" || point.scenario === scenario,
            )
            .map((point) => point.workflowType),
        ),
      ),
    [points, scenario],
  );
  const visible = useMemo(
    () =>
      points.filter(
        (point) =>
          (scenario === "all" || point.scenario === scenario) &&
          (workflow === "all" || point.workflowType === workflow),
      ),
    [points, scenario, workflow],
  );
  const curve = useMemo(() => cumulativePoints(visible), [visible]);
  const selected =
    curve.find((point) => point.index === selectedIndex) ||
    curve.at(-1) ||
    null;
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
  const scopeBaselinePassed = visible.filter(
    (point) => point.baseline.passed,
  ).length;
  const scopeRsiPassed = visible.filter((point) => point.rsi.passed).length;
  const sumKnown = (values: Array<number | null | undefined>) =>
    values.some((value) => value == null)
      ? null
      : values.reduce<number>((total, value) => total + (value as number), 0);
  const scopeBaselineRequests =
    scopeLast?.baselineCumulativeRequests ??
    sumKnown(visible.map((point) => point.baseline.modelRequests));
  const scopeRsiRequests =
    scopeLast?.rsiCumulativeRequests ??
    sumKnown(visible.map((point) => point.rsi.modelRequests));
  const scopeRequestSaving = scopeLast?.requestSavingRate ?? null;
  const scopeBaselineTools = sumKnown(visible.map((point) => point.baseline.toolCalls));
  const scopeRsiTools = sumKnown(visible.map((point) => point.rsi.toolCalls));
  const scopeBaselineAccuracy = scopeLast?.baselineCumulativeAccuracy ?? null;
  const scopeRsiAccuracy = scopeLast?.rsiCumulativeAccuracy ?? null;
  const scopeFast = visible.filter(
    (point) => point.rsi.planningPath === "fast",
  ).length;
  const scopeFastRate = visible.length ? scopeFast / visible.length : null;
  const executionStageRows = [
    ["read_selection_and_binding", "读取选择", "选择当前资料、字段或检索范围"],
    ["compute_selection_and_binding", "计算选择", "选择聚合、关联、比较与参数绑定"],
    ["mixed_tool_decision", "混合决策", "同次响应包含多类工具或无法单独归类"],
    ["report_composition", "报告组合", "组织并提交有证据的业务报告"],
  ] as const;
  const aggregateExecutionStages = (arm: "baseline" | "rsi") => {
    const totals: Record<string, ExecutionStageMetric> = {};
    executionStageRows.forEach(([key]) => {
      const rows = visible.map((point) => point[arm].executionStages?.[key]);
      totals[key] = {
        requests: rows.reduce((sum, row) => sum + (row?.requests || 0), 0),
        inputTokens: rows.reduce((sum, row) => sum + (row?.inputTokens || 0), 0),
        outputTokens: rows.reduce((sum, row) => sum + (row?.outputTokens || 0), 0),
        usageComplete: rows.every((row) => row?.usageComplete !== false),
      };
    });
    return totals;
  };
  const baselineExecutionStages = visible.length
    ? aggregateExecutionStages("baseline")
    : baseline.executionStages || {};
  const rsiExecutionStages = visible.length
    ? aggregateExecutionStages("rsi")
    : rsi.executionStages || {};
  const executionRequests = (stages: Record<string, ExecutionStageMetric>) =>
    executionStageRows.reduce(
      (total, [key]) => total + (stages[key]?.requests || 0),
      0,
    );
  const baselineOtherRequests =
    scopeBaselineRequests == null
      ? null
      : Math.max(0, scopeBaselineRequests - executionRequests(baselineExecutionStages));
  const rsiOtherRequests =
    scopeRsiRequests == null
      ? null
      : Math.max(0, scopeRsiRequests - executionRequests(rsiExecutionStages));

  const scopeG0 = visible.reduce(
    (total, point) => total + (point.rsi.generatedVersionIds?.length || 0),
    0,
  );
  const scopeM0 = visible.reduce(
    (total, point) => total + (point.rsi.generatedMatchVersions?.length || 0),
    0,
  );
  const actualGraphUse = detail?.summary?.actualGraphUse;
  const graphRevisions = revisions.filter(
    (revision) => revision.graphChanged === true,
  );
  const matchingRevisions = revisions.filter(
    (revision) => revision.matchingChanged === true,
  );
  const usedRevisions = revisions.filter(
    (revision) => revision.subsequentUses?.length,
  );
  const completedPairs = visible.filter(
    (point) => point.baseline.runId && point.rsi.runId,
  ).length;
  const failedBaseline = visible.filter(
    (point) => point.baseline.runId && !point.baseline.passed,
  ).length;
  const failedRsi = visible.filter(
    (point) => point.rsi.runId && !point.rsi.passed,
  ).length;
  const incompleteUsage = visible.filter(
    (point) =>
      point.baseline.usageComplete === false ||
      point.rsi.usageComplete === false,
  ).length;
  const selectedCohort = workflow === "all"
    ? undefined
    : cohortSummaries.find((cohort) => cohort.label === workflow);
  const scopeCostConclusionAllowed =
    releaseCostConclusionAllowed ||
    (isAttribution && selectedCohort?.costConclusionAllowed === true);
  const qualityGate = detail?.summary?.qualityGate;
  const qualityGateFailed =
    qualityGate === false ||
    (typeof qualityGate === "object" &&
      qualityGate.status != null &&
      qualityGate.status !== "passed");
  const claimRestriction =
    selectedCohort && !selectedCohort.costConclusionAllowed
      ? {
          title: "该冻结子簇质量不等",
          detail: selectedCohort.qualityGate.reason,
        }
      : metadata?.status === "candidate" && qualityGateFailed
      ? {
          title: "候选状态且质量门槛未通过",
          detail: "仅展示绝对成本和诊断差值，不计算或展示正式收益曲线。",
        }
      : metadata?.status === "candidate"
        ? {
            title: "候选状态，仅展示绝对值",
            detail: "当前测试组尚未晋升 formal，不计算或展示正式收益曲线。",
          }
      : incompleteUsage > 0
        ? {
            title: "usage 不完整，不计算收益",
            detail: "至少一个保存运行缺少完整 token usage，保留已知绝对值和失败记录。",
          }
        : qualityGateFailed
          ? {
              title: "质量门槛未通过，不计算收益",
              detail: "两臂质量未满足可比条件，保留绝对成本和全部失败。",
            }
          : {
              title: "当前协议不允许正式收益结论",
              detail: "保留两臂绝对成本和全部失败，不计算或展示净收益曲线。",
            };

  return (
    <main className="analysis-page">
      <header className="analysis-heading">
        <div>
          <p className="eyebrow">SAVED PAIRED RUNS / READ ONLY</p>
          <h1>数据分析</h1>
          <p>
            查看同一冻结测试组中，两臂随任务到达产生的质量、成本、经验创建、修订与后续使用证据。
          </p>
        </div>
        <label className="dataset-picker">
          <span>测试组</span>
          <select
            aria-label="选择测试组"
            value={datasetId}
            disabled={loading || !datasets.length}
            onChange={(event) => setDatasetId(event.target.value)}
          >
            {!datasets.length && <option value="">暂无可用测试组</option>}
            {datasets.map((dataset) => (
              <option key={dataset.datasetId} value={dataset.datasetId}>
                {dataset.displayName} · {dataset.status}
              </option>
            ))}
          </select>
        </label>
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
          <section className="analysis-context">
            <div className="analysis-context-title">
              <div>
                <small>当前测试组</small>
                <h2>{metadata.displayName}</h2>
              </div>
              <span className={`analysis-status ${metadata.status}`}>
                {metadata.status}
              </span>
            </div>
            <dl>
              <div>
                <dt>实验 ID</dt>
                <dd>{metadata.experimentId}</dd>
              </div>
              <div>
                <dt>Runtime</dt>
                <dd>{metadata.runtimeRevision || "未标注"}</dd>
              </div>
              <div>
                <dt>任务资产</dt>
                <dd>{metadata.assetVersion || "未标注"}</dd>
              </div>
              <div>
                <dt>运行协议</dt>
                <dd>{protocolLabel(metadata.protocol)}</dd>
              </div>
            </dl>
            <p>
              页面内所有数字、曲线和报告只来自这个测试组；切换选项会整体替换数据上下文。
            </p>
            {metadata.claims?.[0] && (
              <p className="analysis-claim">{metadata.claims[0]}</p>
            )}
            {detail?.pricing && (
              <details className="analysis-pricing">
                <summary>模型成本估算价格快照</summary>
                <p>
                  以每次保存运行的真实输入、输出 token 和角色模型计算；这是按
                  <a
                    href={detail.pricing.source.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {detail.pricing.source.name}
                  </a>
                  于 {detail.pricing.source.retrievedAt} 取得的{" "}
                  {detail.pricing.currency} 标准价估算，不是账单金额。
                </p>
                <ul>
                  {Object.entries(detail.pricing.models).map(
                    ([model, modelPrice]) => (
                      <li key={model}>
                        <code>{model}</code>：输入{" "}
                        {rate(modelPrice.inputPerMillionUsd)} · 输出{" "}
                        {rate(modelPrice.outputPerMillionUsd)}
                      </li>
                    ),
                  )}
                </ul>
              </details>
            )}
          </section>

          {metadata.status === "candidate" && (
            <section className="analysis-quality pending">
              <Clock3 size={17} />
              <div>
                <small>RELEASE STATUS</small>
                <strong>
                  {points.length
                    ? qualityGateFailed
                      ? "当前候选结果已完成，质量门槛未通过"
                      : "当前候选结果已完成，尚未晋升正式发布"
                    : "当前候选版本尚未完成正式对照"}
                </strong>
                <span>
                  全量十二任务保持质量受限，不主张整体同质量收益。按任务资产预先冻结的子簇可单独查看：只有两臂全部通过且 usage 完整的子簇才展示同质量效率变化。
                </span>
              </div>
            </section>
          )}

          {detail?.summary?.qualityGate != null
            ? (() => {
                const gate = detail.summary!.qualityGate;
                const passed =
                  gate === true ||
                  (typeof gate === "object" && gate.status === "passed");
                const reason =
                  typeof gate === "object" ? gate.reason : undefined;
                return (
                  <section
                    className={`analysis-quality ${passed ? "passed" : "failed"}`}
                  >
                    <CheckCircle2 size={17} />
                    <div>
                      <small>QUALITY GATE</small>
                      <strong>
                        {passed
                          ? "同任务质量门槛通过"
                          : "当前测试组存在质量限制"}
                      </strong>
                      <span>
                        {reason || "完整保留两臂尝试、失败和用量记录。"}
                      </span>
                    </div>
                  </section>
                );
              })()
            : !points.length && (
                <section className="analysis-quality pending">
                  <Clock3 size={17} />
                  <div>
                    <small>EXPERIMENT STATUS</small>
                    <strong>正式对照尚未产生保存结果</strong>
                    <span>
                      当前仅展示冻结协议与任务机会链；token、延迟、成功率和进化结论保持空白。
                    </span>
                  </div>
                </section>
              )}

          {isAttribution && cohortSummaries.length > 0 && (
            <section className="analysis-section analysis-cohorts" aria-label="冻结业务子簇结果">
              <header>
                <div>
                  <p className="eyebrow">FROZEN COHORT BREAKDOWN</p>
                  <h2>全量账本不删点，按冻结业务子簇解释结果</h2>
                </div>
                <p>子簇来自运行前冻结的任务资产。点击后只切换同一实验内的任务和曲线，不重排、不删除失败。</p>
              </header>
              <div className="analysis-cohort-grid">
                {cohortSummaries.map((cohort) => {
                  const comparable = cohort.costConclusionAllowed;
                  return (
                    <button
                      type="button"
                      key={cohort.cohortId}
                      className={workflow === cohort.label ? "selected" : ""}
                      aria-pressed={workflow === cohort.label}
                      onClick={() => {
                        setScenario("finance");
                        setWorkflow(cohort.label);
                        setSelectedIndex(null);
                      }}
                    >
                      <span>{cohort.pairIds.join("–")}</span>
                      <strong>{cohort.label}</strong>
                      <b>{cohort.baseline.passed}/{cohort.baseline.attempts} → {cohort.rsi.passed}/{cohort.rsi.attempts}</b>
                      <dl>
                        <div><dt>Token</dt><dd>{number(cohort.baseline.tokens)} → {number(cohort.rsi.tokens)}</dd></div>
                        <div><dt>模型请求</dt><dd>{number(cohort.baseline.modelRequests)} → {number(cohort.rsi.modelRequests)}</dd></div>
                        <div><dt>串行时间</dt><dd>{duration(cohort.baseline.durationMs)} → {duration(cohort.rsi.durationMs)}</dd></div>
                        <div><dt>工具错误</dt><dd>{number(cohort.baseline.toolErrors)} → {number(cohort.rsi.toolErrors)}</dd></div>
                      </dl>
                      <em>{comparable ? `同质量子簇：token 减少 ${percent(cohort.tokenSaving)}，请求减少 ${percent(cohort.requestSaving)}` : "可靠性子簇：保留失败，成本差只作诊断"}</em>
                      <small>{cohort.qualityGate.reason}</small>
                    </button>
                  );
                })}
              </div>
              <p className="analysis-cohort-note">双方都通过的 11 项仅属于事后敏感性分析，不进入这些主卡片，也不替代全量 12 项质量结论。</p>
            </section>
          )}

          {detail?.maintenanceDiagnostics && (
            <section className="analysis-section analysis-maintenance" aria-label="发布后维护验证">
              <header>
                <div>
                  <p className="eyebrow">POST-RELEASE MAINTENANCE</p>
                  <h2>发布后维护验证 · {detail.maintenanceDiagnostics.sourceTaskId}</h2>
                </div>
                <span>跨 runtime · 独立诊断</span>
              </header>
              <div className="analysis-maintenance-boundary">
                <ShieldCheck size={17} />
                <p>
                  此诊断不进入正式六任务 KPI、累计曲线、成功率或收益。下面只对照同一业务任务在原 formal
                  运行与修复后 runtime 的一次维护观察。
                </p>
              </div>
              <article className="analysis-maintenance-request">
                <small>同一业务请求</small>
                <p>{detail.maintenanceDiagnostics.request}</p>
              </article>
              <div className="analysis-maintenance-grid">
                {([
                  ["原 formal FA06 · 安全回退", detail.maintenanceDiagnostics.formal, "formal"],
                  ["修复后 diagnostic · 读取 G2/M2", detail.maintenanceDiagnostics.validated, "validated"],
                ] as const).map(([title, run, kind]) => (
                  <article key={kind} className={kind}>
                    <small>{title}</small>
                    <strong>{run.evaluationStatus === "passed" ? "结构化评测通过" : run.status || "状态未知"}</strong>
                    <dl>
                      <div><dt>模型请求</dt><dd>{number(run.modelRequests)}</dd></div>
                      <div><dt>Token</dt><dd>{number(run.tokens)}</dd></div>
                      <div><dt>串行 latency</dt><dd>{duration(run.latencyMs)}</dd></div>
                      <div><dt>工具 / 错误</dt><dd>{number(run.toolCalls)} / {number(run.toolErrors)}</dd></div>
                    </dl>
                    <p>
                      {kind === "formal"
                        ? "正式运行未实际复用历史图，安全回退后完成；这些开销已经计入正式六任务结果。"
                        : `实际选择 ${number(run.selectedGraphNodeCount)} 个图节点，使用 G2 / M2，并按当前任务重新绑定参数；未覆盖义务交回模型。`}
                    </p>
                    <code>{run.runtimeRevision}</code>
                    <div className="analysis-run-links">
                      {run.reportUrl && <a href={run.reportUrl} target="_blank" rel="noreferrer"><FileDown size={13} />正式报告</a>}
                      {run.runUrl && <a href={run.runUrl} target="_blank" rel="noreferrer"><GitBranch size={13} />正式轨迹</a>}
                      {run.artifactUrl && <a href={run.artifactUrl} target="_blank" rel="noreferrer"><ArrowUpRight size={13} />诊断收据</a>}
                    </div>
                  </article>
                ))}
              </div>
              <p className="analysis-maintenance-note">
                单次维护诊断观察：13 → 3 次请求，183,752 → 40,158 token，170.8 → 62.9 秒。
                这是跨 runtime 的阻塞修复验证，不能作为正式收益率或普遍性能结论。
              </p>
              <details className="analysis-maintenance-audit">
                <summary>技术审计：首个配置失败诊断与解释边界</summary>
                <p>
                  首次诊断错误关闭跨任务学习，无法读取 probation 经验并退化为冷启动；虽然结构化评测通过，
                  仍记录 {number(detail.maintenanceDiagnostics.failedSetup.modelRequests)} 次请求、
                  {number(detail.maintenanceDiagnostics.failedSetup.tokens)} token、
                  {duration(detail.maintenanceDiagnostics.failedSetup.latencyMs)} 和
                  {number(detail.maintenanceDiagnostics.failedSetup.toolErrors)} 次工具错误。
                </p>
                <ul>{detail.maintenanceDiagnostics.limitations?.map((item) => <li key={item}>{item}</li>)}</ul>
                {detail.maintenanceDiagnostics.failedSetup.artifactUrl && (
                  <a href={detail.maintenanceDiagnostics.failedSetup.artifactUrl} target="_blank" rel="noreferrer">
                    查看配置失败诊断收据 <ArrowUpRight size={13} />
                  </a>
                )}
              </details>
            </section>
          )}

          {points.length > 0 && (
            <section className="analysis-filters" aria-label="分析筛选">
              <label>
                业务场景
                <select
                  aria-label="筛选业务场景"
                  value={scenario}
                  onChange={(event) => {
                    setScenario(event.target.value);
                    setWorkflow("all");
                    setSelectedIndex(null);
                  }}
                >
                  <option value="all">全部场景</option>
                  {scenarios.map((item) => (
                    <option key={item} value={item}>
                      {scenarioNames[item] || item}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                任务类型
                <select
                  aria-label="筛选任务类型"
                  value={workflow}
                  onChange={(event) => {
                    setWorkflow(event.target.value);
                    setSelectedIndex(null);
                  }}
                >
                  <option value="all">全部任务类型</option>
                  {workflows.map((item) => (
                    <option key={item} value={item}>
                      {item.replaceAll("-", " ")}
                    </option>
                  ))}
                </select>
              </label>
              <span>{curve.length} 个成对任务 · 按真实到达顺序累计</span>
            </section>
          )}

          {points.length > 0 && (
            <section className="analysis-kpis" aria-label="当前筛选核心指标">
              <article>
                <ShieldCheck size={18} />
                <small>任务准确率</small>
                <strong>
                  {percent(scopeBaselineAccuracy)} · {percent(scopeRsiAccuracy)}
                </strong>
                <span>
                  结构化通过 {number(scopeBaselinePassed)}/{curve.length} ·{" "}
                  {number(scopeRsiPassed)}/{curve.length}
                </span>
              </article>
              <article>
                <Layers3 size={18} />
                <small>累计 token</small>
                <strong>
                  {number(scopeBaselineTokens)} → {number(scopeRsiTokens)}
                </strong>
                <span>
                  {scopeCostConclusionAllowed
                    ? `节省 ${percent(scopeTokenSaving)}`
                    : claimRestriction.title}
                </span>
              </article>
              <article>
                <BadgeDollarSign size={18} />
                <small>累计模型成本估算</small>
                <strong>
                  {money(scopeBaselineCost)} → {money(scopeRsiCost)}
                </strong>
                <span>
                  {scopeCostConclusionAllowed && scopeCostSaving != null
                    ? `节省 ${percent(scopeCostSaving)}`
                    : claimRestriction.title}
                </span>
              </article>
              <article>
                <Clock3 size={18} />
                <small>累计串行延迟</small>
                <strong>
                  {duration(scopeBaselineLatency)} → {duration(scopeRsiLatency)}
                </strong>
                <span>
                  {scopeCostConclusionAllowed
                    ? `节省 ${percent(scopeLatencySaving)}`
                    : claimRestriction.title}
                </span>
              </article>
              <article>
                <Activity size={18} />
                <small>大模型调用次数</small>
                <strong>
                  {number(scopeBaselineRequests)} → {number(scopeRsiRequests)}
                </strong>
                <span>
                  {scopeCostConclusionAllowed
                    ? `节省 ${percent(scopeRequestSaving)}`
                    : claimRestriction.title}
                </span>
              </article>
              <article>
                <Sparkles size={18} />
                <small>{isAttribution ? "经验证据" : "经验使用"}</small>
                <strong>
                  {isAttribution
                    ? `${number(scopeG0)} G · ${number(scopeM0)} M`
                    : `${number(scopeFast)} Fast · ${percent(scopeFastRate)}`}
                </strong>
                <span>
                  {isAttribution
                    ? `${graphRevisions.length} 次图修订 · ${matchingRevisions.length} 次描述修订`
                    : "当前筛选范围"}
                </span>
              </article>
            </section>
          )}

          {isAttribution && (
            <section className="analysis-section analysis-attribution">
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
                        revisions,
                      )
                    : null;
                  const evidence = signals
                    ? ([
                        signals.createdGraph && "保存 G 版本",
                        signals.createdMatching && "保存 M 版本",
                        signals.graphRevision && "G 覆盖扩展",
                        signals.matchingRevision && "M 描述扩展",
                        signals.usedGraphRevision && "后续实际使用修订 G",
                        signals.usedMatchingRevision && "后续实际使用修订 M",
                        !signals.usedGraphRevision &&
                          signals.usedGraph &&
                          "实际复用 G",
                        !signals.usedMatchingRevision &&
                          signals.usedMatching &&
                          "实际复用 M",
                      ].filter(Boolean) as string[])
                    : [];
                  return (
                    <li
                      key={entry.index}
                      className={point ? "recorded" : "pending"}
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
                        {point
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

          {points.length > 0 && (
            <section className="analysis-section">
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
                  <h3>累计模型成本估算（USD）</h3>
                  <PolylineChart
                    points={curve}
                    metric="cost"
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
            </section>
          )}

          {points.length > 0 && (
            <section className="analysis-section">
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

          {isAttribution && points.length > 0 && (
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
                {executionStageRows.map(([key, label, description]) => (
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
                  ? " 当前仍是候选结果，仅展示绝对值；候选状态下不计算正式节省率。预先冻结且两臂全通过的子簇仅展示同质量分层分析。"
                  : " 该分解用于解释请求发生在哪里，不把某一类别数量直接换算为收益。"}
              </p>
            </section>
          )}

          {points.length > 0 && (
            <section className="analysis-section analysis-saving-layout">
              <article>
                <header>
                  <p className="eyebrow">EFFICIENCY CHANGE</p>
                  <h2>累计效率节省率</h2>
                </header>
                {scopeCostConclusionAllowed ? (
                  <PolylineChart
                    points={curve}
                    metric="saving"
                    labels={labels}
                    onSelect={(point) => setSelectedIndex(point.index)}
                  />
                ) : (
                  <div className="analysis-empty">
                    <ShieldCheck size={20} />
                    <strong>{claimRestriction.title}</strong>
                    <p>{claimRestriction.detail}</p>
                    {qualityGateFailed && (
                      <p>
                        诊断差值（不学习 − 在线 RSI）：{number(
                          scopeBaselineTokens != null && scopeRsiTokens != null
                            ? scopeBaselineTokens - scopeRsiTokens
                            : null,
                        )} token · {number(
                          scopeBaselineRequests != null && scopeRsiRequests != null
                            ? scopeBaselineRequests - scopeRsiRequests
                            : null,
                        )} 次请求 · {number(
                          scopeBaselineTools != null && scopeRsiTools != null
                            ? scopeBaselineTools - scopeRsiTools
                            : null,
                        )} 次工具调用 · {duration(
                          scopeBaselineLatency != null && scopeRsiLatency != null
                            ? scopeBaselineLatency - scopeRsiLatency
                            : null,
                        )}。该差值不等于正式收益。
                      </p>
                    )}
                  </div>
                )}
              </article>
              <article className="analysis-mechanism">
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
                      {number(scopeM0)} 个 M 版本；历史图实际执行 {number(actualGraphUse?.hits)}/{number(actualGraphUse?.attempts)}
                      （{percent(actualGraphUse?.rate)}）；确认 {graphRevisions.length}{" "}
                      次 G 实质修订、{matchingRevisions.length} 次 M
                      实质修订，其中 {usedRevisions.length}{" "}
                      个修订具有后续实际使用记录。只有复用而没有修订时，本页明确只支持经验复用结论。
                    </p>
                    <dl>
                      <div>
                        <dt>G 修订</dt>
                        <dd>{graphRevisions.length}</dd>
                      </div>
                      <div>
                        <dt>M 修订</dt>
                        <dd>{matchingRevisions.length}</dd>
                      </div>
                    </dl>
                  </>
                ) : (
                  <>
                    <p>
                      当前筛选范围记录了 {number(scopeG0)} 次 G0 形成和{" "}
                      {number(scopeFast)} 次 Fast 使用；完整测试组为{" "}
                      {number(learning.workflowCreated)} 次 G0 与{" "}
                      {number(learning.fastReuse)} 次 Fast。它没有
                      G1/G2，也没有真实图结构修订，因此这里不把 Fast
                      命中描述为递归结构进化。
                    </p>
                    <dl>
                      <div>
                        <dt>Composition</dt>
                        <dd>{number(learning.composition)}</dd>
                      </div>
                      <div>
                        <dt>Fallback</dt>
                        <dd>{number(learning.fallback)}</dd>
                      </div>
                    </dl>
                  </>
                )}
              </article>
            </section>
          )}

          {points.length > 0 && (
            <section className="analysis-reliability" aria-label="可靠性与失败">
              <div>
                <ShieldCheck size={18} />
                <span>已完成配对</span>
                <strong>
                  {completedPairs}/{visible.length}
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
                {detail?.summary?.reliability?.note ||
                  "失败、恢复、超时与不完整用量保留在逐任务轨迹中；未知用量不按 0 计算。"}
              </p>
            </section>
          )}

          {selected && (
            <section className="analysis-focus" aria-live="polite">
              <header>
                <div>
                  <p className="eyebrow">SELECTED TASK</p>
                  <h2>
                    第 {selected.index} 项 ·{" "}
                    {selected.title ||
                      selected.workflowType.replaceAll("-", " ")}
                  </h2>
                </div>
                <span>
                  {scenarioNames[selected.scenario] || selected.scenario} ·{" "}
                  {selected.opportunity || `R${selected.round || "—"}`}
                </span>
              </header>
              {taskError && <p role="alert">{taskError}</p>}
              {taskDetail && <div className="analysis-task-business">
                <h3>本次业务问题与附件</h3>
                <p>{taskDetail.task.task}</p>
                <div className="analysis-run-links">{taskDetail.inputs.map((input) =>
                  <a key={input.id} href={input.download}>{input.name} · 下载附件</a>
                )}</div>
                {(["baseline", "rsi"] as const).map((arm) => <article key={arm}>
                  <h3>{labels[arm]} · 保存成果</h3>
                  <p>{taskDetail.runs[arm]?.submission?.summary || "未交付业务报告"}</p>
                  <details>
                    <summary>执行过程回放 · 已保存的真实工具调用</summary>
                    <ol>{taskDetail.runs[arm]?.toolTrace?.map((trace, index) => <li key={index}>
                      {({ workspace_preview_rows: "读取资料", workspace_map_fields: "选择数据字段", workspace_aggregate_keyed: "按业务对象汇总", workspace_align_keyed: "关联当前资料", workspace_derive_values: "计算派生金额", workspace_compare_values: "检查业务条件", workspace_select_missing: "检查资料完整性", workspace_filter_rows: "筛选业务记录", workspace_sort_rows: "排序业务记录", workspace_publish_report: "提交报告" } as Record<string, string>)[trace.tool] || trace.tool}
                      {trace.executor === "graph" ? " · 图执行" : " · 模型决策"} · {trace.ok ? "完成" : "失败，已计入开销"}
                    </li>)}</ol>
                  </details>
                </article>)}
              </div>}
              <div className="analysis-focus-grid">
                {(["baseline", "rsi"] as const).map((arm) => {
                  const run = selected[arm];
                  const url = reportUrl(metadata, arm, run);
                  const trace = traceUrl(metadata, arm, run);
                  return (
                    <article key={arm} className={arm}>
                      <small>{labels[arm]}</small>
                      <strong>
                        {money(run.costUsd)} · {number(run.tokens)} token
                      </strong>
                      <span>
                        {duration(run.durationMs)} · {number(run.modelRequests)}{" "}
                        次 LLM · {number(run.toolCalls)} 次工具 ·{" "}
                        {number(run.toolErrors)} 次工具错误
                      </span>
                      <em>
                        {run.passed ? "结构化校验通过" : run.status || "未通过"}
                      </em>
                      <div className="analysis-run-links">
                        {url && (
                          <a href={url} target="_blank" rel="noreferrer">
                            <FileDown size={13} />
                            业务报告
                          </a>
                        )}
                        {selected.detailUrl && <a href={`${selected.detailUrl}/runs/${arm}/selection`}>结构化清单</a>}
                        {trace && (
                          <a href={trace} target="_blank" rel="noreferrer">
                            <GitBranch size={13} />
                            真实轨迹
                          </a>
                        )}
                      </div>
                    </article>
                  );
                })}
                <article className="path">
                  <small>
                    {isAttribution
                      ? "单任务观测差异与学习证据"
                      : "RSI 执行路径"}
                  </small>
                  <strong>
                    {releaseCostConclusionAllowed
                      ? `token ${percent(selectedTokenSaving)} · 成本 ${percent(selectedCostSaving)} · latency ${percent(selectedLatencySaving)}`
                      : "当前实验不计算收益"}
                  </strong>
                  <span>
                    {selected.rsi.usedVersionId
                      ? `实际使用 G ${selected.rsi.usedVersionId}`
                      : "本任务未记录图版本使用"}
                  </span>
                  <span>
                    {selected.rsi.usedMatchVersion != null
                      ? `实际使用 M ${selected.rsi.usedMatchVersion}`
                      : "本任务未记录匹配版本使用"}
                  </span>
                  <code>{selected.workpackId}</code>
                </article>
              </div>
              {isAttribution &&
                revisions.some(
                  (revision) =>
                    revision.sourcePairId === selected.pairId ||
                    revision.sourceTaskId === selected.workpackId,
                ) && (
                  <details className="analysis-revision-audit">
                    <summary>展开本任务产生的 G / M diff</summary>
                    {revisions
                      .filter(
                        (revision) =>
                          revision.sourcePairId === selected.pairId ||
                          revision.sourceTaskId === selected.workpackId,
                      )
                      .map((revision, index) => (
                        <div key={index}>
                          <strong>
                            {revision.graphChanged
                              ? "G 结构有实质差异"
                              : "G 未变化"}{" "}
                            ·{" "}
                            {revision.matchingChanged
                              ? "M 匹配描述有实质差异"
                              : "M 未变化"}
                          </strong>
                          <span>
                            后续实际使用 {revision.subsequentUses?.length || 0}{" "}
                            次
                          </span>
                          <pre>{JSON.stringify(revision, null, 2)}</pre>
                        </div>
                      ))}
                  </details>
                )}
            </section>
          )}

          {points.length > 0 && (
            <section className="analysis-section analysis-task-ledger">
              <header>
                <div>
                  <p className="eyebrow">TRACEABLE TASK LEDGER</p>
                  <h2>逐任务真实运行与报告</h2>
                </div>
                <p>任务序号沿用测试组的真实到达顺序；空用量不会按 0 计入。</p>
              </header>
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
                        revisions,
                      );
                      const evidence =
                        signals.graphRevision || signals.matchingRevision
                          ? "产生实质修订"
                          : signals.usedGraphRevision ||
                              signals.usedMatchingRevision
                            ? "实际使用修订"
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
                              className={`path-badge ${signals.graphRevision || signals.matchingRevision ? "revision" : point.rsi.planningPath || "unknown"}`}
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
                                  A
                                </a>
                              )}
                              {reportUrl(metadata, "rsi", point.rsi) && (
                                <a
                                  href={reportUrl(metadata, "rsi", point.rsi)}
                                  target="_blank"
                                  rel="noreferrer"
                                  title={`${labels.rsi}报告`}
                                >
                                  B
                                </a>
                              )}
                              {baselineTrace && (
                                <a
                                  href={baselineTrace}
                                  target="_blank"
                                  rel="noreferrer"
                                  title={`${labels.baseline}轨迹`}
                                >
                                  A·T
                                </a>
                              )}
                              {rsiTrace && (
                                <a
                                  href={rsiTrace}
                                  target="_blank"
                                  rel="noreferrer"
                                  title={`${labels.rsi}轨迹`}
                                >
                                  B·T
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
            </section>
          )}

          {metadata.limitations?.length || detail?.limitations?.length ? (
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
