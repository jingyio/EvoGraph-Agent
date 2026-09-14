import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Gauge,
  Layers3,
  LoaderCircle,
  Route,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { api } from "./api";
import { cumulativePoints, type CumulativeMeasures } from "./dataAnalysisMath";
import "./data-analysis.css";

type Scenario = "finance" | "support" | "tickets" | string;
type DatasetSummary = {
  datasetId: string;
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
};
type Arm = {
  runId?: string;
  status?: string;
  passed?: boolean;
  tokens?: number | null;
  durationMs?: number | null;
  latencyMs?: number | null;
  runUrl?: string;
  modelRequests?: number | null;
  toolCalls?: number | null;
  usageComplete?: boolean;
  reportUrl?: string;
};
type Point = {
  index: number;
  workpackId: string;
  scenario: Scenario;
  workflowType: string;
  round?: number;
  status?: string;
  baseline: Arm;
  rsi: Arm & { planningPath?: string; usedVersionId?: string | null; generatedVersionIds?: string[] };
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
  usageIncomplete?: number;
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
    latencySaving?: number | null;
    baseline?: ArmSummary;
    rsi?: ArmSummary;
    learning?: {
      fastReuse?: number;
      workflowCreated?: number;
      composition?: number;
      fallback?: number;
    };
    qualityGate?: { status?: string; reason?: string };
    reliability?: { allUsageComplete?: boolean; note?: string };
    curve?: unknown[];
  };
  limitations?: string[];
};
type ChartPoint = Point & CumulativeMeasures;

const scenarioNames: Record<string, string> = {
  finance: "财务运营",
  support: "客服运营",
  tickets: "技术工单",
};
const number = (value?: number | null) =>
  value == null ? "—" : new Intl.NumberFormat("zh-CN").format(Math.round(value));
const percent = (value?: number | null) =>
  value == null ? "—" : `${(value * 100).toFixed(1)}%`;
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

export function datasetItems(payload: unknown): DatasetSummary[] {
  if (Array.isArray(payload)) return payload as DatasetSummary[];
  const root = asRecord(payload);
  return Array.isArray(root.items) ? (root.items as DatasetSummary[]) : [];
}

function normalizeArm(value: unknown, fallback: Record<string, unknown> = {}): Arm {
  const arm = asRecord(value);
  const metrics = asRecord(arm.metrics);
  const evaluation = asRecord(arm.evaluation);
  const input = asNumber(metrics.inputTokens);
  const output = asNumber(metrics.outputTokens);
  const explicitTokens = asNumber(arm.tokens);
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
    tokens:
      explicitTokens ??
      asNumber(fallback.tokens) ??
      derivedTokens,
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
    usageComplete:
      typeof arm.usageComplete === "boolean"
        ? arm.usageComplete
        : typeof metrics.usageComplete === "boolean"
          ? metrics.usageComplete
          : undefined,
    reportUrl: asString(arm.reportUrl),
    runUrl: asString(arm.runUrl),
  };
}

export function analysisPoints(detail: Detail): Point[] {
  const experiment = detail.experiment || {};
  const summary = detail.summary || (experiment.summary as Detail["summary"]) || {};
  const rawPoints = Array.isArray(detail.points)
    ? detail.points
    : Array.isArray(detail.pairs)
      ? detail.pairs
      : Array.isArray(experiment.pairs)
        ? experiment.pairs
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
    .map((item) => {
      const row = asRecord(item);
      const index = Number(row.index);
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
      const baseline = normalizeArm(row.baseline || runs.baseline, baselineFallback);
      const rsiRaw = asRecord(row.rsi || runs.rsi);
      const evolution = asRecord(rsiRaw.evolution);
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
          ? row.generatedVersionIds.filter((value): value is string => typeof value === "string")
          : Array.isArray(evolution.generatedVersionIds)
            ? evolution.generatedVersionIds.filter((value): value is string => typeof value === "string")
            : [],
      };
      return {
        index,
        workpackId:
          asString(row.workpackId) || asString(curveRow.workpackId) || `task-${index}`,
        scenario: asString(row.scenario) || "unknown",
        workflowType:
          asString(row.workflowType) || asString(curveRow.workflowType) || "未标注任务族",
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
  return String(value.id || value.runtimeProtocol || value.mode || "冻结成对协议");
}

function reportUrl(dataset: DatasetSummary, arm: "baseline" | "rsi", run: Arm) {
  return (
    run.reportUrl ||
    (run.runId
      ? `/api/workpack-experiments/${dataset.experimentId}/runs/${arm}/${run.runId}/report`
      : "")
  );
}

function PolylineChart({
  points,
  metric,
  onSelect,
}: {
  points: ChartPoint[];
  metric: "tokens" | "latency" | "requests" | "accuracy" | "saving";
  onSelect: (point: ChartPoint) => void;
}) {
  if (!points.length)
    return <div className="analysis-empty">当前筛选范围没有已保存的成对任务。</div>;
  const width = 820;
  const height = 258;
  const left = 58;
  const right = 18;
  const top = 18;
  const bottom = 36;
  const absoluteValue = (point: ChartPoint, arm: "baseline" | "rsi") => {
    if (metric === "tokens")
      return arm === "baseline" ? point.baselineCumulativeTokens : point.rsiCumulativeTokens;
    if (metric === "latency")
      return arm === "baseline" ? point.baselineCumulativeLatency : point.rsiCumulativeLatency;
    if (metric === "requests")
      return arm === "baseline" ? point.baselineCumulativeRequests : point.rsiCumulativeRequests;
    return (arm === "baseline" ? point.baselineCumulativeAccuracy : point.rsiCumulativeAccuracy) == null
      ? null
      : (arm === "baseline" ? point.baselineCumulativeAccuracy! : point.rsiCumulativeAccuracy!) * 100;
  };
  const values = points.flatMap((point) =>
    metric === "saving"
      ? [point.tokenSavingRate == null ? null : point.tokenSavingRate * 100, point.latencySavingRate == null ? null : point.latencySavingRate * 100]
      : [absoluteValue(point, "baseline"), absoluteValue(point, "rsi")],
  ).filter((value): value is number => value != null);
  if (!values.length) {
    const missing = metric === "latency" ? "latency" : metric === "requests" ? "大模型调用" : metric === "accuracy" ? "结构化评分" : "token";
    return <div className="analysis-empty">当前筛选范围缺少完整的 {missing} 数据，未按 0 补齐。</div>;
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
      .filter((item): item is { index: number; value: number } => item.value != null)
      .map((item) => `${x(item.index)},${y(item.value)}`)
      .join(" ");
  const tokenSavingLine = points
    .map((point, index) => ({ index, value: point.tokenSavingRate == null ? null : point.tokenSavingRate * 100 }))
    .filter((item): item is { index: number; value: number } => item.value != null)
    .map((item) => `${x(item.index)},${y(item.value)}`)
    .join(" ");
  const latencySavingLine = points
    .map((point, index) => ({ index, value: point.latencySavingRate == null ? null : point.latencySavingRate * 100 }))
    .filter((item): item is { index: number; value: number } => item.value != null)
    .map((item) => `${x(item.index)},${y(item.value)}`)
    .join(" ");
  const displayValue = (value: number) =>
    metric === "latency"
      ? duration(value)
      : metric === "saving" || metric === "accuracy"
        ? `${value.toFixed(0)}%`
        : number(value);
  const last = points.at(-1)!;
  return (
    <div className="analysis-chart">
      <div className="analysis-chart-legend">
        {metric === "saving" ? (
          <><span className="saving"><i />token 节省率</span><span className="latency-saving"><i />latency 节省率</span></>
        ) : (
          <>
            <span className="baseline"><i />Baseline</span>
            <span className="rsi"><i />RSI Agent</span>
          </>
        )}
        <small>点击节点查看对应任务</small>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={metric === "tokens" ? "累计 token 曲线" : metric === "latency" ? "累计串行延迟曲线" : metric === "requests" ? "累计大模型调用次数曲线" : metric === "accuracy" ? "累计结构化准确率曲线" : "累计 token 与 latency 节省率曲线"}>
        {[0, 0.5, 1].map((ratio) => {
          const value = min + (max - min) * (1 - ratio);
          const lineY = top + ratio * (height - top - bottom);
          return (
            <g key={ratio}>
              <line x1={left} y1={lineY} x2={width - right} y2={lineY} className="grid" />
              <text x={left - 8} y={lineY + 4} textAnchor="end">{displayValue(value)}</text>
            </g>
          );
        })}
        {metric === "saving" ? (
          <><polyline points={tokenSavingLine} className="saving-line" /><polyline points={latencySavingLine} className="latency-saving-line" /></>
        ) : (
          <>
            <polyline points={line("baseline")} className="baseline-line" />
            <polyline points={line("rsi")} className="rsi-line" />
          </>
        )}
        {points.map((point, index) => {
          const value = metric === "saving"
            ? point.tokenSavingRate == null ? null : point.tokenSavingRate * 100
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
        <text x={left} y={height - 9}>1</text>
        <text x={width - right} y={height - 9} textAnchor="end">{last.order} 个任务</text>
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
        setDatasetId((current) => current || defaultDatasetId || items[0]?.datasetId || "");
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

  const metadata = detail?.dataset || detail || datasets.find((item) => item.datasetId === datasetId);
  const points = useMemo(() => (detail ? analysisPoints(detail) : []), [detail]);
  const scenarios = useMemo(
    () => Array.from(new Set(points.map((point) => point.scenario))),
    [points],
  );
  const workflows = useMemo(
    () =>
      Array.from(
        new Set(
          points
            .filter((point) => scenario === "all" || point.scenario === scenario)
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
    curve.find((point) => point.index === selectedIndex) || curve.at(-1) || null;
  const baseline = detail?.summary?.baseline || {};
  const rsi = detail?.summary?.rsi || {};
  const baselineTokens = baseline.tokens ?? baseline.totalTokens;
  const rsiTokens = rsi.tokens ?? rsi.totalTokens;
  const baselineLatency = baseline.latencyMs ?? baseline.durationMs;
  const rsiLatency = rsi.latencyMs ?? rsi.durationMs;
  const learning = detail?.summary?.learning || {};
  const scopeLast = curve.at(-1);
  const scopeBaselineTokens = scopeLast?.baselineCumulativeTokens ?? (curve.length ? null : baselineTokens);
  const scopeRsiTokens = scopeLast?.rsiCumulativeTokens ?? (curve.length ? null : rsiTokens);
  const scopeBaselineLatency = scopeLast?.baselineCumulativeLatency ?? (curve.length ? null : baselineLatency);
  const scopeRsiLatency = scopeLast?.rsiCumulativeLatency ?? (curve.length ? null : rsiLatency);
  const scopeTokenSaving = scopeLast?.tokenSavingRate ?? (curve.length ? null : detail?.summary?.tokenSaving);
  const scopeLatencySaving = scopeLast?.latencySavingRate ?? (curve.length ? null : detail?.summary?.latencySaving);
  const scopeBaselinePassed = visible.filter((point) => point.baseline.passed).length;
  const scopeRsiPassed = visible.filter((point) => point.rsi.passed).length;
  const scopeBaselineRequests = scopeLast?.baselineCumulativeRequests ?? null;
  const scopeRsiRequests = scopeLast?.rsiCumulativeRequests ?? null;
  const scopeRequestSaving = scopeLast?.requestSavingRate ?? null;
  const scopeBaselineAccuracy = scopeLast?.baselineCumulativeAccuracy ?? null;
  const scopeRsiAccuracy = scopeLast?.rsiCumulativeAccuracy ?? null;
  const scopeFast = visible.filter((point) => point.rsi.planningPath === "fast").length;
  const scopeFastRate = visible.length ? scopeFast / visible.length : null;
  const scopeG0 = visible.reduce((total, point) => total + (point.rsi.generatedVersionIds?.length || 0), 0);


  return (
    <main className="analysis-page">
      <header className="analysis-heading">
        <div>
          <p className="eyebrow">SAVED PAIRED RUNS / READ ONLY</p>
          <h1>数据分析</h1>
          <p>查看同一测试组中，Baseline 与 RSI Agent 随任务数量增加产生的 token、串行延迟和复用变化。</p>
        </div>
        <label className="dataset-picker">
          <span>测试组</span>
          <select aria-label="选择测试组" value={datasetId} disabled={loading || !datasets.length} onChange={(event) => setDatasetId(event.target.value)}>
            {!datasets.length && <option value="">暂无可用测试组</option>}
            {datasets.map((dataset) => (
              <option key={dataset.datasetId} value={dataset.datasetId}>
                {dataset.displayName} · {dataset.status}
              </option>
            ))}
          </select>
        </label>
      </header>

      {error && <p className="analysis-error" role="alert">{error}</p>}
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
              <span className={`analysis-status ${metadata.status}`}>{metadata.status}</span>
            </div>
            <dl>
              <div><dt>实验 ID</dt><dd>{metadata.experimentId}</dd></div>
              <div><dt>Runtime</dt><dd>{metadata.runtimeRevision || "未标注"}</dd></div>
              <div><dt>任务资产</dt><dd>{metadata.assetVersion || "未标注"}</dd></div>
              <div><dt>运行协议</dt><dd>{protocolLabel(metadata.protocol)}</dd></div>
            </dl>
            <p>页面内所有数字、曲线和报告只来自这个测试组；切换选项会整体替换数据上下文。</p>
            {metadata.claims?.[0] && <p className="analysis-claim">{metadata.claims[0]}</p>}
          </section>

          {detail?.summary?.qualityGate && <section className={`analysis-quality ${detail.summary.qualityGate.status || "unknown"}`}><CheckCircle2 size={17} /><div><small>QUALITY GATE</small><strong>{detail.summary.qualityGate.status === "passed" ? "同任务质量门槛通过" : "当前测试组存在质量限制"}</strong><span>{detail.summary.qualityGate.reason || "完整保留两臂尝试、失败和用量记录。"}</span></div></section>}

          <section className="analysis-filters" aria-label="分析筛选">
            <label>业务场景<select aria-label="筛选业务场景" value={scenario} onChange={(event) => { setScenario(event.target.value); setWorkflow("all"); setSelectedIndex(null); }}><option value="all">全部场景</option>{scenarios.map((item) => <option key={item} value={item}>{scenarioNames[item] || item}</option>)}</select></label>
            <label>任务类型<select aria-label="筛选任务类型" value={workflow} onChange={(event) => { setWorkflow(event.target.value); setSelectedIndex(null); }}><option value="all">全部任务类型</option>{workflows.map((item) => <option key={item} value={item}>{item.replaceAll("-", " ")}</option>)}</select></label>
            <span>{curve.length} 个成对任务 · 按真实到达顺序累计</span>
          </section>

          <section className="analysis-kpis" aria-label="当前筛选核心指标">
            <article><ShieldCheck size={18} /><small>任务准确率</small><strong>{percent(scopeBaselineAccuracy)} · {percent(scopeRsiAccuracy)}</strong><span>结构化通过 {number(scopeBaselinePassed)}/{curve.length} · {number(scopeRsiPassed)}/{curve.length}</span></article>
            <article><Layers3 size={18} /><small>累计 token</small><strong>{number(scopeBaselineTokens)} → {number(scopeRsiTokens)}</strong><span>节省 {percent(scopeTokenSaving)}</span></article>
            <article><Clock3 size={18} /><small>累计串行延迟</small><strong>{duration(scopeBaselineLatency)} → {duration(scopeRsiLatency)}</strong><span>节省 {percent(scopeLatencySaving)}</span></article>
            <article><Activity size={18} /><small>大模型调用次数</small><strong>{number(scopeBaselineRequests)} → {number(scopeRsiRequests)}</strong><span>节省 {percent(scopeRequestSaving)} · 保存的真实请求数</span></article>
            <article><Sparkles size={18} /><small>经验使用</small><strong>{number(scopeFast)} Fast · {percent(scopeFastRate)}</strong><span>当前筛选范围</span></article>
          </section>

          <section className="analysis-section">
            <header><div><p className="eyebrow">TASK GROWTH / ABSOLUTE COST</p><h2>任务增加时的累计开销</h2></div><p>两条线始终使用相同任务范围。串行延迟保留真实等待、失败与恢复耗时。</p></header>
            <div className="analysis-chart-grid">
              <article><h3>累计 token</h3><PolylineChart points={curve} metric="tokens" onSelect={(point) => setSelectedIndex(point.index)} /></article>
              <article><h3>累计串行 latency</h3><PolylineChart points={curve} metric="latency" onSelect={(point) => setSelectedIndex(point.index)} /></article>
            </div>
          </section>

          <section className="analysis-section">
            <header><div><p className="eyebrow">MODEL CALLS / TASK ACCURACY</p><h2>大模型调用与任务准确率</h2></div><p>准确率按当前范围内结构化校验通过数除以已评测任务数计算，失败保留在分母；它不是 Judge 分数或模型置信度。</p></header>
            <div className="analysis-chart-grid">
              <article><h3>累计大模型调用次数</h3><PolylineChart points={curve} metric="requests" onSelect={(point) => setSelectedIndex(point.index)} /></article>
              <article><h3>累计任务准确率</h3><PolylineChart points={curve} metric="accuracy" onSelect={(point) => setSelectedIndex(point.index)} /></article>
            </div>
          </section>

          <section className="analysis-section analysis-saving-layout">
            <article>
              <header><p className="eyebrow">EFFICIENCY CHANGE</p><h2>累计效率节省率</h2></header>
              <PolylineChart points={curve} metric="saving" onSelect={(point) => setSelectedIndex(point.index)} />
            </article>
            <article className="analysis-mechanism">
              <Route size={20} />
              <p className="eyebrow">MECHANISM BOUNDARY</p>
              <h2>{metadata.displayName}展示 G0 形成与 Fast 复用</h2>
              <p>当前筛选范围记录了 {number(scopeG0)} 次 G0 形成和 {number(scopeFast)} 次 Fast 使用；完整测试组为 {number(learning.workflowCreated)} 次 G0 与 {number(learning.fastReuse)} 次 Fast。它没有 G1/G2，也没有真实图结构修订，因此这里不把 Fast 命中描述为递归结构进化。</p>
              <dl><div><dt>Composition</dt><dd>{number(learning.composition)}</dd></div><div><dt>Fallback</dt><dd>{number(learning.fallback)}</dd></div></dl>
            </article>
          </section>

          {selected && (
            <section className="analysis-focus" aria-live="polite">
              <header><div><p className="eyebrow">SELECTED TASK</p><h2>第 {selected.index} 项 · {selected.workflowType.replaceAll("-", " ")}</h2></div><span>{scenarioNames[selected.scenario] || selected.scenario} · R{selected.round || "—"}</span></header>
              <div className="analysis-focus-grid">
                {(["baseline", "rsi"] as const).map((arm) => {
                  const run = selected[arm];
                  const url = reportUrl(metadata, arm, run);
                  return <article key={arm} className={arm}><small>{arm === "baseline" ? "BASELINE" : "RSI AGENT"}</small><strong>{number(run.tokens)} token</strong><span>{duration(run.durationMs)} · {number(run.modelRequests)} 次 LLM · {number(run.toolCalls)} 次工具</span><em>{run.passed ? "结构化校验通过" : run.status || "未通过"}</em>{url && <a href={url} target="_blank" rel="noreferrer">查看实际报告 <ArrowUpRight size={13} /></a>}</article>;
                })}
                <article className="path"><small>RSI 执行路径</small><strong>{selected.rsi.planningPath || "未标注"}</strong><span>{selected.rsi.usedVersionId ? `实际使用版本 ${selected.rsi.usedVersionId}` : "本任务未记录后续结构版本使用"}</span><code>{selected.workpackId}</code></article>
              </div>
            </section>
          )}

          <section className="analysis-section analysis-task-ledger">
            <header><div><p className="eyebrow">TRACEABLE TASK LEDGER</p><h2>逐任务真实运行与报告</h2></div><p>任务序号沿用测试组的真实到达顺序；空用量不会按 0 计入。</p></header>
            <div className="analysis-table-scroll">
              <table>
                <thead><tr><th>序号 / 任务</th><th>场景</th><th>Baseline</th><th>RSI Agent</th><th>执行路径</th><th>报告</th></tr></thead>
                <tbody>{curve.map((point) => <tr key={point.index} className={selectedIndex === point.index ? "selected" : ""} onClick={() => setSelectedIndex(point.index)}><td><strong>#{point.index}</strong><small>{point.workpackId}</small></td><td>{scenarioNames[point.scenario] || point.scenario}<small>{point.workflowType.replaceAll("-", " ")}</small></td><td>{number(point.baseline.tokens)}<small>{duration(point.baseline.durationMs)}</small></td><td>{number(point.rsi.tokens)}<small>{duration(point.rsi.durationMs)}</small></td><td><span className={`path-badge ${point.rsi.planningPath || "unknown"}`}>{point.rsi.planningPath || "—"}</span></td><td>{reportUrl(metadata, "baseline", point.baseline) && <a href={reportUrl(metadata, "baseline", point.baseline)} target="_blank" rel="noreferrer">B</a>}{reportUrl(metadata, "rsi", point.rsi) && <a href={reportUrl(metadata, "rsi", point.rsi)} target="_blank" rel="noreferrer">R</a>}</td></tr>)}</tbody>
              </table>
            </div>
          </section>

          {(metadata.limitations?.length || detail?.limitations?.length) ? <details className="analysis-limitations"><summary>数据限制与解释边界</summary><ul>{(metadata.limitations || detail?.limitations || []).map((item) => <li key={item}>{item}</li>)}</ul></details> : null}
        </>
      )}

      {!loading && !detailLoading && !metadata && !error && (
        <section className="analysis-empty"><Gauge size={22} /><h2>暂无可分析的保存测试组</h2><p>后续结果写入分析清单后，会自动出现在测试组选项中。</p></section>
      )}
    </main>
  );
}
