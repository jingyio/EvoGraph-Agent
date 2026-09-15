import { AlertCircle, ArrowDownToLine, ArrowRight, Bot, Check, ChevronLeft, ChevronRight, CircleStop, FileBarChart2, FilePlus2, FileSearch, FileText, FolderOpen, LoaderCircle, MessageSquareText, Network, Play, Plus, RefreshCw, ShieldCheck, Sparkles, Table2, Trash2, UploadCloud, X } from 'lucide-react';
import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from 'react';
import { api, upload } from './api';
import './workspace.css';

type Role = 'finance' | 'support' | 'tickets';
type Table = { id: string; sourceId: string; sourceName: string; sheet: string; fields: string[]; types: Record<string, string>; missing: Record<string, number>; rowCount: number };
type Source = { id: string; name: string; format: string; sizeBytes: number; tableIds: string[]; status: string; downloadPath?: string; provenance?: { kind?: string; source?: string } };
type WorkspaceTask = { id: string; title: string; task: string; createdAt: string; split: string; scenario: Role; sourceStatus?: string; followupRunId?: string | null };
type Workspace = { id: string; role: Role; label: string; folderName: string; folderPath: string; sources: Source[]; tables: Table[]; tasks: WorkspaceTask[]; reports: ReportSummary[]; exports: ExportItem[] };
type Preview = { table: Table; records: Record<string, unknown>[] };
type ReportSummary = { id: string; runId: string; taskId: string; title: string; createdAt: string; metrics: Record<string, unknown>; selectedIds: string[]; evidenceCount: number; summary: string };
type ExportItem = { id: string; name: string; rowCount: number; createdAt: string };
type TraceEvent = { seq: number; at?: string; type: string; title: string; detail?: any; elapsedMs?: number; metrics?: Metrics };
type Metrics = { modelRequests?: number; toolCalls?: number; inputTokens?: number; outputTokens?: number; durationMs?: number; toolErrors?: number; reportAttempts?: number; runtimeOverheadMs?: number };
type Run = { id: string; taskId: string; status: string; phase: string; strategy: string; createdAt?: string; events: TraceEvent[]; metrics: Metrics; evaluation?: { status: string; issues?: string[] }; trajectoryMatch?: unknown; submission?: { groups?: { name: string; reason: string; condition: string; count: number; selectedIds: string[]; evidenceIds: string[] }[]; metrics?: Record<string, unknown>; selectedIds?: string[]; evidenceIds?: string[]; summary?: string; assumptions?: string[] }; graph?: { nodes: GraphNode[]; nodeStates: Record<string, string> }; fallback?: string; evolution?: { planningPath?: string; usedVersionId?: string; generation?: number; matchVersion?: number; trajectoryCompilation?: unknown; currentBindings?: unknown; lookupMs?: number; localCompileMs?: number; bindingMs?: number }; error?: string; learningEnabled?: boolean; learningWriteEnabled?: boolean; pollUrl?: string; reportUrl?: string; reportDownloadUrl?: string; selectionDownloadUrl?: string };
type GraphNode = { id: string; tool: string; dependencies: string[]; foreach?: unknown; reuse?: unknown; defer?: boolean };
type RunSummary = { id: string; taskId: string; status: string; phase: string; strategy: string; createdAt: string; metrics: Metrics; evaluation: { status: string }; learningEnabled?: boolean; learningWriteEnabled?: boolean; comparison?: { id?: string; arm?: string; providerProfile?: string }; experience?: { mode?: string; releaseId?: string | null; versionCount?: number; readOnly?: boolean } };

const FINANCE_CAPABILITY = { key: 'finance' as const, label: '财务运营', caption: '订单、支付、退款与异常复核' };
const formatCount = (value?: number) => new Intl.NumberFormat('zh-CN').format(value || 0);
const formatMs = (value?: number) => value == null ? '—' : value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${Math.round(value)}ms`;
const totalTokens = (metrics?: Metrics) => (metrics?.inputTokens || 0) + (metrics?.outputTokens || 0);
const statusName: Record<string, string> = { queued: '排队', running: '处理中', completed: '已完成', limited: '受限停止', cancelled: '已取消', failed: '失败', passed: '硬校验通过', user_review_required: '等待复核', failed_evaluation: '未通过校验' };

type LaneKind = 'plan' | 'traditional' | 'rsi';
const laneName = (lane: LaneKind) => lane === 'plan' ? '传统 Plan + ReAct' : lane === 'rsi' ? '图执行 · 在线 RSI' : '图执行 · 不学习';

function eventTitle(event: TraceEvent, lane: LaneKind = 'traditional'): string {
  if (event.type === 'model_start') {
    if (event.title === 'match') return lane === 'rsi' ? '正在匹配金融经验' : '正在检查可复用结构';
    if (event.title === 'plan') return lane === 'plan' ? '正在生成执行计划' : '正在为本次任务重新规划';
    if (event.title === 'execute') return 'LLM 正在选择下一项业务动作';
    return 'LLM 请求进行中';
  }
  if (event.type === 'model') return event.detail?.decisionStage === 'report_composition' ? 'LLM 已组织业务报告' : 'LLM 已返回业务动作';
  if (event.type === 'plan') return lane === 'plan' ? '传统执行计划已生成' : '本次数据计划已生成';
  if (event.type === 'graph_created') return lane === 'rsi' ? '已载入并绑定可复用执行图' : '本次执行图已建立';
  if (event.type === 'graph') return `${lane === 'rsi' ? '经验图' : '执行图'}节点 ${event.title}`;
  if (event.type === 'binding') return lane === 'rsi' ? '经验图已绑定本次资料' : '本次资料参数已绑定';
  if (event.type === 'action') return `调用 ${toolLabel(event.title)}`;
  if (event.type === 'observation') return `获得 ${toolLabel(event.title)}结果`;
  if (event.type === 'fallback') return lane === 'rsi' ? '经验覆盖不足，交回模型补齐' : '当前结构不足，交回模型补齐';
  if (event.type === 'report_recovery') return '业务报告校验恢复';
  if (event.type === 'evaluation') return '业务成果校验';
  if (event.type === 'finished') return '本次工作已结束';
  return event.title;
}

function eventChannel(event: TraceEvent): 'model' | 'rsi' | 'tool' | 'control' {
  if (event.type === 'model' || event.type === 'model_start' || event.detail?.executor === 'model') return 'model';
  if (['graph', 'graph_created', 'binding', 'motif', 'compiler', 'composition'].includes(event.type) || event.detail?.executor === 'graph') return 'rsi';
  if (event.type === 'action' || event.type === 'observation') return 'tool';
  return 'control';
}

function compactValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value.length > 180 ? `${value.slice(0, 177)}…` : value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return `${value.length} 项`;
  if (typeof value === 'object') return `${Object.keys(value as Record<string, unknown>).length} 个字段`;
  return String(value);
}

function eventDetailLines(event: TraceEvent, lane: LaneKind = 'traditional'): string[] {
  const detail = event.detail;
  if (!detail) return [];
  if (event.type === 'model' || event.type === 'model_start') {
    const usage = detail.usage as { input?: number; output?: number } | undefined;
    const calls = Array.isArray(detail.toolCalls) ? detail.toolCalls.map((call: any) => call?.function?.name).filter(Boolean) : [];
    return [
      detail.model ? `模型：${detail.model}` : '',
      usage ? `本次 token：${formatCount(usage.input)} 输入 · ${formatCount(usage.output)} 输出` : '',
      calls.length ? `返回动作：${calls.join('、')}` : (detail.content ? `文本结果：${compactValue(detail.content)}` : ''),
    ].filter(Boolean);
  }
  if (event.type === 'plan') {
    return (detail.steps || []).slice(0, 6).map((step: { id?: string; intent?: string; sourceTable?: string }) =>
      `${step.id || '步骤'}：${step.intent || '读取当前资料'}${step.sourceTable ? ` · ${step.sourceTable}` : ''}`,
    );
  }
  if (event.type === 'graph_created') {
    return (detail.nodes || []).slice(0, 8).map((node: { id?: string; tool?: string; dependencies?: string[] }) =>
      `${node.id || '节点'}：${String(node.tool || '').replace('workspace_', '')}${node.dependencies?.length ? ` ← ${node.dependencies.join('、')}` : ''}`,
    );
  }
  if (event.type === 'action') {
    try {
      const argumentsValue = typeof detail.arguments === 'string' ? JSON.parse(detail.arguments) : detail.arguments;
      return [
        `执行者：${detail.executor === 'graph' ? (lane === 'rsi' ? '在线 RSI 图运行时' : '图执行运行时') : 'LLM 调度'}`,
        ...Object.entries(argumentsValue || {}).slice(0, 6).map(([key, value]) => `${key}：${compactValue(value)}`),
      ];
    } catch {
      return [`执行者：${detail.executor === 'graph' ? (lane === 'rsi' ? '在线 RSI 图运行时' : '图执行运行时') : 'LLM 调度'}`];
    }
  }
  if (event.type === 'observation') {
    const result = detail.result || {};
    const keys = ['matchedCount', 'count', 'rowCount', 'changedCount', 'matchCount', 'page', 'mayHaveMore', 'saved', 'reportId'];
    const rows = Array.isArray(result.records) ? `records：${result.records.length} 条` : '';
    return [detail.ok === false ? `工具错误：${compactValue(detail.error)}` : '工具成功返回', rows,
      ...keys.filter(key => result[key] !== undefined).map(key => `${key}：${compactValue(result[key])}`)].filter(Boolean);
  }
  if (Array.isArray(detail)) return detail.slice(0, 6).map(item => compactValue(item));
  return Object.entries(detail).slice(0, 7).map(([key, value]) => `${key}：${compactValue(value)}`);
}

function Metric({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return <div className="workspace-metric"><small>{label}</small><strong>{value}</strong>{hint && <span>{hint}</span>}</div>;
}

function GraphView({ run }: { run: Run }) {
  if (!run.graph?.nodes?.length) return <div className="workspace-graph-empty"><Network size={18} /><span>{run.fallback ? '当前资料/计划未形成可安全执行图，已交回模型。' : '等待可执行结构。'}</span></div>;
  return <div className="workspace-graph">{run.graph.nodes.map((node, index) => <div key={node.id} className={`workspace-graph-node ${run.graph?.nodeStates[node.id] || 'pending'}`}><div><small>{node.id}</small><strong>{node.tool.replace('workspace_', '')}</strong></div><span>{node.dependencies.length ? `依赖 ${node.dependencies.join(' · ')}` : '起始节点'}</span>{Boolean(node.reuse) && <em>复用观察</em>}{Boolean(node.foreach) && <em>当前行绑定</em>}{node.defer && <em>模型接管</em>}{index < run.graph!.nodes.length - 1 && <ChevronRight size={16} />}</div>)}</div>;
}

type ComparisonArm = {
  arm?: 'plan_react' | 'no_learning' | 'online_rsi' | 'graph_rsi';
  runId: string;
  taskId: string;
  createdAt?: string;
  label: string;
  strategy: 'plan_react' | 'graph_rsi';
  status: string;
  phase?: string;
  timeline?: TraceEvent[];
  metrics?: Metrics;
  evaluation?: Run['evaluation'];
  submission?: Run['submission'];
  pollUrl?: string;
  reportUrl?: string;
  reportDownloadUrl?: string;
  selectionDownloadUrl?: string;
  providerProfile?: 'primary' | 'secondary' | 'primary_serial';
  learningEnabled?: boolean;
  learningWriteEnabled?: boolean;
  experience?: { mode?: string; releaseId?: string | null; versionCount?: number; readOnly?: boolean };
  model?: string;
  runDetail?: Run;
};
type WorkspaceComparison = {
  id: string;
  taskId: string;
  status: string;
  executionPolicy: 'strict_serial' | 'strict_serial_three_arm' | 'parallel_dual_key' | 'parallel_three_arm_two_key';
  design?: 'plan_react_graph_learning_three_arm' | 'same_graph_runtime_learning_ablation' | 'legacy_plan_react_vs_graph_rsi';
  knowledgeBase?: { releaseId?: string; datasetId?: string; versionCount?: number; readOnly?: boolean } | null;
  model?: string;
  limits?: { runs: number; models: number; reads: number };
  arms: ComparisonArm[];
};
type StoredComparisonRef = { comparisonId: string; taskId: string };

const COMPARISON_STORAGE_KEY = 'rsi-workspace-comparisons-v1';
const LAST_WORKSPACE_STORAGE_KEY = 'rsi-last-workspace-v1';
const HISTORY_CUTOFF_STORAGE_KEY = 'rsi-workspace-history-cutoff-v1';
const storedComparisonRefs = (): Record<string, StoredComparisonRef> => {
  if (typeof window === 'undefined') return {};
  try { return JSON.parse(window.localStorage.getItem(COMPARISON_STORAGE_KEY) || '{}') as Record<string, StoredComparisonRef>; }
  catch { return {}; }
};
const rememberComparison = (workspaceId: string, comparison: WorkspaceComparison) => {
  if (!workspaceId || comparison.id.startsWith('history:')) return;
  const current = storedComparisonRefs();
  current[workspaceId] = { comparisonId: comparison.id, taskId: comparison.taskId };
  window.localStorage.setItem(COMPARISON_STORAGE_KEY, JSON.stringify(current));
};
const forgetComparison = (workspaceId: string) => {
  const current = storedComparisonRefs();
  delete current[workspaceId];
  window.localStorage.setItem(COMPARISON_STORAGE_KEY, JSON.stringify(current));
};
const rememberWorkspace = (workspaceId: string) => {
  if (workspaceId) window.localStorage.setItem(LAST_WORKSPACE_STORAGE_KEY, workspaceId);
};
const historyCutoffs = (): Record<string, string> => {
  if (typeof window === 'undefined') return {};
  try { return JSON.parse(window.localStorage.getItem(HISTORY_CUTOFF_STORAGE_KEY) || '{}') as Record<string, string>; }
  catch { return {}; }
};

const comparisonArm = (comparison: WorkspaceComparison | null, armName: 'plan_react' | 'no_learning' | 'online_rsi') =>
  comparison?.arms.find(arm => arm.arm === armName) ||
  comparison?.arms.find(arm => armName === 'plan_react'
    ? arm.strategy === 'plan_react'
    : armName === 'no_learning'
      ? arm.strategy === 'graph_rsi' && arm.learningEnabled === false
      : arm.strategy === 'graph_rsi' && arm.learningEnabled !== false) || null;
const armRun = (arm?: ComparisonArm | null): Run | null => arm ? {
  ...arm.runDetail,
  id: arm.runId,
  taskId: arm.taskId,
  status: arm.status,
  phase: arm.phase || arm.runDetail?.phase || '',
  strategy: arm.strategy,
  createdAt: arm.createdAt || arm.runDetail?.createdAt,
  events: arm.timeline || arm.runDetail?.events || [],
  metrics: arm.metrics || arm.runDetail?.metrics || {},
  evaluation: arm.evaluation || arm.runDetail?.evaluation,
  submission: arm.submission || arm.runDetail?.submission,
  learningEnabled: arm.learningEnabled ?? arm.runDetail?.learningEnabled,
  learningWriteEnabled: arm.learningWriteEnabled ?? arm.runDetail?.learningWriteEnabled,
  pollUrl: arm.pollUrl || arm.runDetail?.pollUrl,
  reportUrl: arm.reportUrl || arm.runDetail?.reportUrl,
  reportDownloadUrl: arm.reportDownloadUrl || arm.runDetail?.reportDownloadUrl,
  selectionDownloadUrl: arm.selectionDownloadUrl || arm.runDetail?.selectionDownloadUrl,
} : null;
const comparisonStatus = (arms: ComparisonArm[]) => {
  const statuses = new Set(arms.map(arm => arm.status));
  if (statuses.has('running')) return 'running';
  if (statuses.has('queued')) return 'queued';
  if (statuses.size === 1 && statuses.has('completed')
      && arms.every(arm => ['passed', 'user_review_required'].includes(arm.evaluation?.status || ''))) return 'completed';
  return 'completed_with_failures';
};

const activeRun = (run?: Run | null) => Boolean(run && ['queued', 'running'].includes(run.status));
const terminalRun = (run?: Run | null) => Boolean(run && !activeRun(run));
const optionalCount = (value?: number) => value == null ? '等待/不可用' : formatCount(value);
const optionalTokens = (metrics?: Metrics) =>
  metrics?.inputTokens == null && metrics?.outputTokens == null
    ? '等待/不可用'
    : formatCount((metrics.inputTokens || 0) + (metrics.outputTokens || 0));
const runExports = (run?: Run | null) => (run?.events || []).flatMap(event =>
  event.detail?.result?.downloadPath
    ? [{ path: event.detail.result.downloadPath as string, rowCount: event.detail.result.rowCount as number | undefined }]
    : [],
);

const TOOL_LABELS: Record<string, string> = {
  workspace_list_sources: '确认当前附件',
  workspace_get_schema: '识别字段结构',
  workspace_profile_table: '统计资料概况',
  workspace_preview_rows: '读取业务记录',
  workspace_reconcile_keyed_sums: '订单级汇总核对',
  workspace_aggregate_rows: '汇总业务指标',
  workspace_aggregate_keyed: '按业务键聚合',
  workspace_compare_values: '检查业务阈值',
  workspace_filter_rows: '筛选关注记录',
  workspace_get_row: '读取证据记录',
  workspace_join_rows: '关联业务资料',
  workspace_map_fields: '提取当前字段',
  workspace_select_missing: '识别资料缺失',
  workspace_align_keyed: '按业务键对齐',
  workspace_distinct_values: '统计不同取值',
  workspace_derive_values: '计算派生指标',
  workspace_publish_report: '生成业务报告',
  workspace_save_draft: '保存业务草稿',
};
const TABLE_LABELS: Record<string, string> = {
  orders: '订单表', payments: '支付表', items: '商品明细表', customers: '客户表',
  complaints: '投诉表', narratives: '投诉叙述', responses_dates: '响应日期表',
  issues: '工单表', activity: '活动记录', labels: '标签表', issue_body: '工单正文',
};
const toolLabel = (name?: string) => name ? TOOL_LABELS[name] || name.replace(/^workspace_/, '').replaceAll('_', ' ') : '当前工具';
const shortVersion = (value: unknown) => typeof value === 'string' && value ? value.slice(0, 8) : '';
const tableLabel = (value: unknown) => {
  if (typeof value !== 'string') return '';
  const matched = Object.keys(TABLE_LABELS).find(name => value === name || value.endsWith(`_${name}`));
  return matched ? TABLE_LABELS[matched] : value.length > 24 ? `${value.slice(0, 10)}…` : value;
};
const parsedEventArguments = (event: TraceEvent): Record<string, any> => {
  try {
    const value = typeof event.detail?.arguments === 'string' ? JSON.parse(event.detail.arguments) : event.detail?.arguments;
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  } catch { return {}; }
};
const thresholdLabel = (name: unknown, operator: unknown, value: unknown) => {
  const key = String(name || '').toLowerCase();
  const businessName = key.includes('installment') ? '分期' : key.includes('diff') || key.includes('amount') || key.includes('cent') ? '金额差异' : String(name || '阈值');
  const operatorName: Record<string, string> = { abs_gt: '>', gt: '>', gte: '≥', lt: '<', lte: '≤', eq: '=' };
  const unit = key.includes('installment') ? '期' : key.includes('diff') || key.includes('amount') || key.includes('cent') ? '分' : '';
  return `${businessName} ${operatorName[String(operator || '')] || String(operator || '')} ${compactValue(value)}${unit}`.replace(/\s+/g, ' ').trim();
};
const firstThreshold = (value: unknown): string => {
  if (Array.isArray(value)) {
    for (const item of value) { const found = firstThreshold(item); if (found) return found; }
    return '';
  }
  if (!value || typeof value !== 'object') return '';
  const record = value as Record<string, unknown>;
  if (Array.isArray(record.comparisons)) {
    const values = record.comparisons.slice(0, 2).map((item: any) => item?.threshold === undefined ? '' : thresholdLabel(item.name || item.leftAlias, item.operator, item.threshold)).filter(Boolean);
    if (values.length) return values.join(' · ');
  }
  if (Array.isArray(record.filters)) {
    const values = record.filters.slice(0, 2).map((item: any) => item?.value === undefined ? '' : thresholdLabel(item.field, item.operator, item.value)).filter(Boolean);
    if (values.length) return values.join(' · ');
  }
  if (record.threshold !== undefined && ['number', 'string'].includes(typeof record.threshold)) return thresholdLabel(record.name || record.field, record.operator, record.threshold);
  for (const nested of Object.values(record)) { const found = firstThreshold(nested); if (found) return found; }
  return '';
};
const centsAsBrl = (value: unknown) => typeof value === 'number' ? `R$ ${(value / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '';
type StageFact = { label: string; value: string };
function eventStageLabel(event: TraceEvent, lane: LaneKind = 'traditional'): string {
  if (event.type === 'model_start') return event.title === 'plan' ? (lane === 'plan' ? '传统规划' : '本次重规划') : event.title === 'match' ? (lane === 'rsi' ? '匹配金融经验' : '检查当前结构') : event.title === 'execute' ? '选择下一动作' : '模型决策';
  if (event.type === 'model') return event.detail?.decisionStage === 'report_composition' ? '组织报告' : '模型决策';
  if (event.type === 'plan') return '形成计划';
  if (event.type === 'graph_created') return '构建执行图';
  if (event.type === 'graph' || event.type === 'binding') return lane === 'rsi' ? '经验图执行' : '本次图执行';
  if (event.type === 'action') return event.detail?.executor === 'graph' ? (lane === 'rsi' ? '经验图自动执行' : '图运行时执行') : '调用业务工具';
  if (event.type === 'observation') return event.detail?.ok === false ? '工具恢复' : '获得当前结果';
  if (event.type === 'evaluation') return '核验成果';
  if (event.type === 'finished') return '保存完成';
  if (event.type === 'report_recovery' || event.type === 'fallback' || event.type === 'read_guard') return '有界恢复';
  return '执行进展';
}
function notificationEventTitle(event: TraceEvent, lane: LaneKind): string {
  if (event.type === 'action') return toolLabel(event.title);
  if (event.type === 'observation') return event.detail?.ok === false ? `${toolLabel(event.title)}需要恢复` : `${toolLabel(event.title)}已完成`;
  if (event.type === 'graph') return `${lane === 'rsi' ? '经验图' : '执行图'}节点已完成 · ${event.title}`;
  return eventTitle(event, lane);
}

function eventStageFacts(event: TraceEvent, run: Run): StageFact[] {
  const facts: StageFact[] = [];
  const add = (label: string, value: unknown) => {
    if (value === undefined || value === null || value === '') return;
    facts.push({ label, value: compactValue(value) });
  };
  const detail = event.detail || {};
  const args = parsedEventArguments(event);
  if (event.type === 'model_start') {
    add('模型', String(detail.model || '').replace('qwen/', ''));
    add('可用动作', Array.isArray(detail.availableTools) ? `${detail.availableTools.length} 项` : '');
  } else if (event.type === 'model') {
    add('输入 token', detail.usage?.input != null ? formatCount(detail.usage.input) : '');
    add('输出 token', detail.usage?.output != null ? formatCount(detail.usage.output) : '');
    const calls = Array.isArray(detail.toolCalls) ? detail.toolCalls.map((call: any) => toolLabel(call?.function?.name)).filter(Boolean) : [];
    add('下一动作', calls.length > 1 ? `${calls[0]}等 ${calls.length} 项` : calls[0]);
  } else if (event.type === 'plan') {
    const steps = Array.isArray(detail.steps) ? detail.steps : [];
    add('计划步骤', `${steps.length} 项`);
    const tables = [...new Set(steps.map((step: any) => TABLE_LABELS[step?.sourceTable] || step?.sourceTable).filter(Boolean))];
    add('当前资料', tables.join(' · '));
  } else if (event.type === 'graph_created') {
    add('图节点', Array.isArray(detail.nodes) ? `${detail.nodes.length} 个` : '');
    add('执行路径', run.evolution?.usedVersionId ? `复用 G ${shortVersion(run.evolution.usedVersionId)}` : '当前计划编译');
    add('本地编译', run.evolution?.localCompileMs != null ? formatMs(run.evolution.localCompileMs) : '');
  } else if (event.type === 'graph') {
    const selections = Array.isArray(detail) ? detail : [];
    add('已选择节点', selections.length ? `${selections.length} 个` : '');
    add('当前工具', selections[0]?.tool ? toolLabel(selections[0].tool) : '');
  } else if (event.type === 'binding') {
    add('节点', detail.nodeId);
    add('当前资料', tableLabel(args.tableId || args.anchorTableId));
    add('当前阈值', firstThreshold(args));
    if (!firstThreshold(args)) add('绑定耗时', detail.bindingMs != null ? formatMs(detail.bindingMs) : '');
  } else if (event.type === 'action') {
    add('业务动作', toolLabel(event.title));
    add('当前资料', tableLabel(args.tableId || args.anchorTableId));
    const threshold = firstThreshold(args);
    add('当前阈值', threshold);
    if (!threshold) add('运算', args.operation || (Array.isArray(args.aggregates) ? `${args.aggregates.length} 项聚合` : ''));
  } else if (event.type === 'observation') {
    const result = detail.result || {};
    add(detail.ok === false ? '错误' : '工具结果', detail.ok === false ? detail.error : '成功');
    add('当前资料', tableLabel(result.tableId));
    const recordCount = Array.isArray(result.records) ? result.records.length : undefined;
    const count = result.matchedCount ?? result.anchorCount ?? result.count ?? result.rowCount ?? recordCount;
    add(result.anchorCount != null ? '复核主体' : '记录数量', count != null ? `${formatCount(count)} 条` : '');
    add('支付合计', centsAsBrl(result.totals?.payment_sum));
    add('商品及运费', centsAsBrl(result.totals?.goods_total ?? result.totals?.item_total));
    add('缺失记录', result.missingAnyCount != null ? `${formatCount(result.missingAnyCount)} 条` : '');
    add('报告', result.reportId ? '已保存' : '');
  } else if (event.type === 'evaluation') {
    add('校验状态', statusName[detail.status] || detail.status);
    add('问题', Array.isArray(detail.issues) ? `${detail.issues.length} 项` : '');
  } else if (event.type === 'finished') {
    add('LLM 请求', `${formatCount(run.metrics.modelRequests)} 次`);
    add('累计 token', formatCount(totalTokens(run.metrics)));
    const generated = detail.evolution?.generatedVersionIds?.[0];
    add(generated ? '新经验版本' : '结果', generated ? `G ${shortVersion(generated)}` : statusName[detail.status] || detail.status);
  } else if (event.type === 'semantic_constraint' && Array.isArray(detail)) {
    add('业务口径', detail[0]);
  } else {
    eventDetailLines(event).slice(0, 2).forEach((value, index) => add(index ? '当前值' : '状态', value));
  }
  return facts.slice(0, 3);
}

function LiveStageNotification({
  id,
  label,
  run,
  active,
}: {
  id: LaneKind;
  label: string;
  run: Run | null;
  active: boolean;
}) {
  const latest = run?.events.at(-1);
  const eventKey = latest && run ? `${run.id}:${latest.seq}` : '';
  const [shown, setShown] = useState<{ key: string; event: TraceEvent; run: Run } | null>(null);
  const [dismissedKey, setDismissedKey] = useState('');
  const activeInThisView = useRef(false);

  useEffect(() => {
    activeInThisView.current = false;
    setShown(null);
    setDismissedKey('');
  }, [run?.id]);

  useEffect(() => {
    if (active) activeInThisView.current = true;
    const mayAnnounce = active || activeInThisView.current;
    if (!mayAnnounce || !latest || !run || !eventKey || eventKey === dismissedKey) return;
    setShown({ key: eventKey, event: latest, run });
    const timer = window.setTimeout(() => {
      setShown(current => current?.key === eventKey ? null : current);
      if (!active) activeInThisView.current = false;
    }, 3100);
    return () => window.clearTimeout(timer);
  }, [active, eventKey, dismissedKey]);

  if (!shown) return null;
  const { event, run: shownRun } = shown;
  const facts = eventStageFacts(event, shownRun);
  const channel = event.detail?.ok === false ? 'error' : eventChannel(event);
  return <article key={shown.key} className={`workspace-live-notification ${id} ${channel}`} data-event-seq={event.seq}>
    <div className="workspace-live-notification-icon" aria-hidden="true">{id === 'rsi' ? <Sparkles size={18} /> : id === 'plan' ? <FileText size={18} /> : <Bot size={18} />}</div>
    <div className="workspace-live-notification-copy">
      <header><span>{label}</span><small>{eventStageLabel(event, id)} · {event.elapsedMs == null ? '刚刚' : formatMs(event.elapsedMs)}</small></header>
      <strong>{notificationEventTitle(event, id)}</strong>
      {facts.length > 0 && <dl>{facts.map((fact, index) => <div key={`${fact.label}-${index}`}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl>}
    </div>
    <button type="button" onClick={() => {
      setDismissedKey(shown.key);
      setShown(null);
      if (!active) activeInThisView.current = false;
    }} aria-label={`关闭${label}阶段通知`}><X size={12} /></button>
    <i className="workspace-live-notification-progress" aria-hidden="true" />
  </article>;
}

function WorkspaceLiveOverlay({
  planRun,
  traditionalRun,
  rsiRun,
  active,
}: {
  planRun: Run | null;
  traditionalRun: Run | null;
  rsiRun: Run | null;
  active: boolean;
}) {
  if (!planRun && !traditionalRun && !rsiRun) return null;
  return <aside className="workspace-live-overlay" role="status" aria-live="polite" aria-label="三臂实时阶段通知">
    <LiveStageNotification id="plan" label="传统 Plan + ReAct" run={planRun} active={active && activeRun(planRun)} />
    <LiveStageNotification id="traditional" label="图执行 · 不学习" run={traditionalRun} active={active && activeRun(traditionalRun)} />
    <LiveStageNotification id="rsi" label="图执行 · 在线 RSI（金融经验）" run={rsiRun} active={active && activeRun(rsiRun)} />
  </aside>;
}

function WorkspaceStageBoard({ lanes }: { lanes: { lane: LaneKind; run: Run | null; waiting: string }[] }) {
  const anyActive = lanes.some(item => activeRun(item.run));
  const [clock, setClock] = useState(Date.now());
  useEffect(() => {
    if (!anyActive) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [anyActive]);
  return <section className="workspace-stage-board" aria-label="三臂真实阶段对照">
    <header><strong>当前执行阶段</strong></header>
    <div>{lanes.map(({ lane, run, waiting }) => {
      const latest = run?.events.at(-1);
      const eventStarted = latest?.at ? Date.parse(latest.at) : NaN;
      const waitingMs = activeRun(run) && Number.isFinite(eventStarted) ? Math.max(0, clock - eventStarted) : null;
      return <article key={lane} className={lane}>
        <small>{laneName(lane)}</small>
        <strong>{latest ? notificationEventTitle(latest, lane) : waiting}</strong>
        <span>{waitingMs != null
          ? `${eventStageLabel(latest!, lane)} · 已持续 ${formatMs(waitingMs)}`
          : run
            ? `${latest ? `${eventStageLabel(latest, lane)} · ` : ''}${statusName[run.status] || run.status}`
            : '尚未启动'}</span>
      </article>;
    })}</div>
  </section>;
}

function WorkspaceRunLane({
  arm,
  run,
  error,
  waiting,
}: {
  arm: LaneKind;
  run: Run | null;
  error?: string;
  waiting: string;
}) {
  const events = useMemo(() => run?.events || [], [run?.events]);
  const [selectedEventSeq, setSelectedEventSeq] = useState<number | null>(null);
  useEffect(() => { setSelectedEventSeq(null); }, [run?.id]);
  const selectedEvent = events.find(event => event.seq === selectedEventSeq) || events.at(-1);
  const report = run?.submission;
  const exports = runExports(run);
  const isRsi = arm === 'rsi';
  const isPlan = arm === 'plan';
  const showMetrics = Boolean(run && run.status !== 'queued');
  const learningState = run
    ? run.learningWriteEnabled === true
      ? '经验可读写'
      : run.learningEnabled === true
        ? '读取冻结经验，不写入'
        : run.learningEnabled === false
          ? '不读取或写入经验'
          : '经验状态未返回'
    : '等待运行创建';

  return <article className={`workspace-agent-lane ${arm}`}>
    <header>
      <h3>{laneName(arm)}</h3>
      <span className={run?.status === 'completed' ? 'done' : activeRun(run) ? 'active' : error ? 'failed' : ''}>
        {run ? statusName[run.status] || run.status : error ? '启动失败' : waiting}
      </span>
    </header>

    {showMetrics && <div className="workspace-agent-metrics">
      <Metric label="LLM 请求" value={optionalCount(run?.metrics.modelRequests)} />
      <Metric label="Token" value={optionalTokens(run?.metrics)} />
      <Metric label="工具调用" value={optionalCount(run?.metrics.toolCalls)} />
      <Metric label="串行耗时" value={run ? formatMs(run.metrics.durationMs) : '等待/不可用'} />
    </div>}

    {error && <p className="workspace-run-error">{error}</p>}

    {events.length > 0 && <details className="workspace-event-history">
      <summary><span>完整执行记录</span><small>{events.length} 个真实事件</small></summary>
      <div className="workspace-lane-events" aria-label={`${laneName(arm)}真实事件`}>
        {events.map(event => <button
          key={event.seq}
          className={`${eventChannel(event)} ${selectedEvent?.seq === event.seq ? 'selected' : ''}`}
          onClick={() => setSelectedEventSeq(event.seq)}
        >
          <i>{eventChannel(event) === 'model' ? 'M' : eventChannel(event) === 'rsi' ? 'R' : eventChannel(event) === 'tool' ? 'T' : 'C'}</i>
          <span><strong>{eventTitle(event, arm)}</strong><small>{event.elapsedMs == null ? '时间未返回' : formatMs(event.elapsedMs)}</small></span>
          {event.type === 'observation' && event.detail?.ok === false && <em>错误</em>}
        </button>)}
        {!events.length && <p>{error ? '该臂没有可回放事件。' : waiting}</p>}
      </div>

      {selectedEvent && <div className={`workspace-event-detail ${eventChannel(selectedEvent)}`}>
        <header>
          <span>{eventChannel(selectedEvent) === 'model' ? 'LLM' : eventChannel(selectedEvent) === 'rsi' ? 'RSI RUNTIME' : eventChannel(selectedEvent) === 'tool' ? 'TOOL' : 'CONTROL'}</span>
          <strong>{eventTitle(selectedEvent, arm)}</strong>
        </header>
        {eventDetailLines(selectedEvent, arm).length > 0
          ? <ul>{eventDetailLines(selectedEvent, arm).map((line, index) => <li key={`${selectedEvent.seq}-${index}`}>{line}</li>)}</ul>
          : <p>该真实事件没有返回额外展示字段。</p>}
      </div>}
    </details>}

    {run && <details className="workspace-agent-audit">
      <summary>技术审计 · 图、参数与完整轨迹</summary>
      {run ? <>
        <p>Run {run.id} · {events.length} 个真实事件{isRsi ? ` · 金融冻结知识库 · ${learningState}` : isPlan ? ' · 不读取图经验' : ' · 不读取或写入跨任务经验'}</p>
        <GraphView run={run} />
        {Boolean(run.trajectoryMatch || run.evolution?.trajectoryCompilation) && <div className="workspace-trajectory">
          <strong>轨迹来源 · G{run.evolution?.generation ?? '—'} / M{run.evolution?.matchVersion ?? '—'}</strong>
          <pre>{JSON.stringify({ match: run.trajectoryMatch, compilation: run.evolution?.trajectoryCompilation }, null, 2)}</pre>
        </div>}
      </> : <p>等待后端返回运行结构。</p>}
    </details>}

    {(report || terminalRun(run)) && <section className="workspace-lane-report">
      <header>
        <div><FileBarChart2 size={17} /><strong>最终业务报告</strong></div>
        <span>{report ? (run?.evaluation?.status === 'passed' ? '结构化校验通过' : run?.evaluation?.status === 'user_review_required' ? '待用户复核' : '已返回，校验未通过') : terminalRun(run) ? '后端未返回报告' : '等待完成'}</span>
      </header>
      {report ? <>
        <p>{report.summary || '报告正文为空；请查看技术审计和下载文件。'}</p>
        <small>{report.evidenceIds?.length || 0} 条当前观察证据 · {report.selectedIds?.length || 0} 项业务清单</small>
        {report.groups?.length ? <details><summary>查看原因结果清单</summary><div className="workspace-lane-groups">{report.groups.map(group => <article key={group.name}><strong>{group.name} · {group.count} 项</strong><p>{group.reason}</p><code>{group.selectedIds.length ? group.selectedIds.join('、') : '本次为空组'}</code></article>)}</div></details> : null}
        <div className="workspace-result-actions">
          {run?.reportUrl ? <a href={run.reportUrl} target="_blank" rel="noreferrer">打开报告 <ArrowRight size={14} /></a> : <span>后端未返回报告地址</span>}
          {run?.reportDownloadUrl ? <a href={run.reportDownloadUrl} download>下载报告 <ArrowDownToLine size={14} /></a> : <span>后端未返回下载地址</span>}
          {run?.selectionDownloadUrl ? <a href={run.selectionDownloadUrl} download>下载结构化清单 <ArrowDownToLine size={14} /></a> : <span>清单地址不可用</span>}
        </div>
        {exports.length > 0 && <div className="workspace-downloads">{exports.map(item => <a key={item.path} href={item.path}><ArrowDownToLine size={14} />下载清单 · {item.rowCount == null ? '行数未返回' : `${item.rowCount} 行`}</a>)}</div>}
      </> : <p>{terminalRun(run) ? '本次真实 run 已结束，但当前 API 没有返回业务报告。' : '运行完成后在这里显示同 run 的报告正文、下载入口和结构化清单。'}</p>}
    </section>}
  </article>;
}

export default function WorkspaceWorkbench() {
  const input = useRef<HTMLInputElement>(null);
  const requestArea = useRef<HTMLTextAreaElement>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  useEffect(() => {
    void api<Workspace[]>('/api/workspaces').then(items => {
      const lastWorkspaceId = window.localStorage.getItem(LAST_WORKSPACE_STORAGE_KEY);
      const lastWorkspace = items.find(item => item.id === lastWorkspaceId && item.role === FINANCE_CAPABILITY.key);
      if (lastWorkspace) void activateWorkspace(lastWorkspace);
    }).catch(() => {});
  }, []);
  const [tableId, setTableId] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [request, setRequest] = useState('');
  const [readyTask, setReadyTask] = useState<WorkspaceTask | null>(null);
  const [clarifications, setClarifications] = useState<{ id: string; question: string }[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [costConfirmed, setCostConfirmed] = useState(false);
  const [comparison, setComparison] = useState<WorkspaceComparison | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [historyCutoff, setHistoryCutoff] = useState('');
  const [busy, setBusy] = useState<'workspace' | 'upload' | 'prepare' | 'run' | ''>('');
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');

  const planArm = comparisonArm(comparison, 'plan_react');
  const traditionalArm = comparisonArm(comparison, 'no_learning');
  const rsiArm = comparisonArm(comparison, 'online_rsi');
  const planRun = armRun(planArm);
  const traditionalRun = armRun(traditionalArm);
  const rsiRun = armRun(rsiArm);
  const active = Boolean(busy === 'run' || comparison && ['queued', 'running'].includes(comparison.status));
  const historyComparison = Boolean(comparison?.id.startsWith('history:'));
  const planWaiting = planArm?.status === 'queued' ? '等待开始' : planArm ? '等待真实事件' : historyComparison ? '历史记录无此方法' : '等待运行创建';
  const traditionalWaiting = traditionalArm?.status === 'queued' ? '等待 A 完成' : traditionalArm ? '等待真实事件' : historyComparison ? '历史记录无此方法' : '等待运行创建';
  const rsiWaiting = rsiArm?.status === 'queued' ? '等待 B 完成' : rsiArm ? '等待真实事件' : historyComparison ? '历史记录无此方法' : '等待运行创建';

  useEffect(() => {
    const area = requestArea.current;
    if (!area) return;
    area.style.height = 'auto';
    area.style.height = `${Math.max(122, area.scrollHeight)}px`;
  }, [request]);

  async function createWorkspace(resetDraft = true): Promise<Workspace | null> {
    setBusy('workspace'); setError('');
    if (resetDraft) {
      setComparison(null); setReadyTask(null); setClarifications([]); setAnswers({}); setCostConfirmed(false); setRequest('');
    }
    try {
      const item = await api<Workspace>('/api/workspaces', { method: 'POST', body: JSON.stringify({ role: FINANCE_CAPABILITY.key, label: `${FINANCE_CAPABILITY.label}工作区` }) });
      setWorkspace(item); setTableId(item.tables[0]?.id || ''); setPreview(null); setRuns([]); rememberWorkspace(item.id);
      return item;
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(''); }
    return null;
  }

  async function refreshWorkspace(id = workspace?.id) {
    if (!id) return;
    const item = await api<Workspace>(`/api/workspaces/${id}`);
    setWorkspace(item);
    if (!tableId && item.tables[0]) setTableId(item.tables[0].id);
    const history = await api<{ runs: RunSummary[] }>(`/api/workspaces/runs?workspaceId=${id}`);
    const cutoff = historyCutoffs()[id] || historyCutoff;
    setRuns(cutoff ? history.runs.filter(run => run.createdAt > cutoff) : history.runs);
  }

  async function restoreComparison(workspaceId: string, workspaceSnapshot?: Workspace) {
    const saved = storedComparisonRefs()[workspaceId];
    if (!saved) { setComparison(null); return; }
    try {
      const restored = await api<WorkspaceComparison>(`/api/workspaces/comparison-runs/${saved.comparisonId}`);
      const task = (workspaceSnapshot || workspace)?.tasks.find(item => item.id === saved.taskId);
      if (!task || task.sourceStatus === 'removed') {
        forgetComparison(workspaceId);
        setComparison(null);
        setReadyTask(null);
        setRequest('');
        return;
      }
      setComparison(restored);
      setReadyTask(task);
      setRequest(task.task);
    } catch {
      forgetComparison(workspaceId);
      setComparison(null);
      setReadyTask(null);
      setRequest('');
    }
  }

  async function activateWorkspace(item: Workspace) {
    if (item.role !== FINANCE_CAPABILITY.key) return;
    setWorkspace(item); setTableId(item.tables[0]?.id || ''); setComparison(null);
    setHistoryCutoff(historyCutoffs()[item.id] || '');
    setReadyTask(null); setRequest(''); setClarifications([]); setCostConfirmed(false); rememberWorkspace(item.id);
    await refreshWorkspace(item.id);
    await restoreComparison(item.id, item);
  }

  useEffect(() => {
    if (!workspace || !tableId) { setPreview(null); return; }
    api<Preview>(`/api/workspaces/${workspace.id}/tables/${encodeURIComponent(tableId)}/preview`).then(setPreview).catch(reason => setError(reason.message));
  }, [workspace?.id, tableId]);

  useEffect(() => {
    if (!comparison || !['queued', 'running'].includes(comparison.status) || comparison.id.startsWith('history:')) return;
    let disposed = false;
    const poll = async () => {
      try {
        const current = await api<WorkspaceComparison>(`/api/workspaces/comparison-runs/${comparison.id}`);
        if (disposed) return;
        setComparison(current);
        if (workspace?.id) rememberComparison(workspace.id, current);
        if (!['queued', 'running'].includes(current.status)) void refreshWorkspace();
      } catch (reason) {
        if (!disposed) setError((reason as Error).message);
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 800);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [comparison?.id, comparison?.status, workspace?.id]);


  async function addFiles(files: FileList | File[]) {
    const pendingFiles = Array.from(files);
    if (!pendingFiles.length || busy) return;
    const target = workspace || await createWorkspace(false);
    if (!target) return;
    setBusy('upload'); setError('');
    try {
      for (const file of pendingFiles) await upload(`/api/workspaces/${target.id}/files`, file);
      await refreshWorkspace(target.id);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(''); }
  }

  async function removeSource(source: Source) {
    if (!workspace) return;
    setError('');
    try { await api(`/api/workspaces/${workspace.id}/files/${source.id}`, { method: 'DELETE', body: '{}' }); await refreshWorkspace(); }
    catch (reason) { setError((reason as Error).message); }
  }

  async function prepareTask() {
    const target = workspace || await createWorkspace(false);
    if (!target) return;
    setBusy('prepare'); setError(''); setClarifications([]);
    try {
      const body = { request, answers };
      const response = await api<{ status: string; task?: WorkspaceTask; clarifications?: { id: string; question: string }[] }>(`/api/workspaces/${target.id}/tasks`, { method: 'POST', body: JSON.stringify(body) });
      if (response.status === 'needs_clarification') { setClarifications(response.clarifications || []); return; }
      const nextTask = response.task || null;
      setReadyTask(nextTask);
      setCostConfirmed(false); await refreshWorkspace(target.id);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(''); }
  }

  async function startWork() {
    if (!readyTask || !costConfirmed) return;
    setBusy('run'); setError('');
    try {
      const result = await api<WorkspaceComparison>(`/api/workspaces/tasks/${readyTask.id}/comparison-runs`, {
        method: 'POST',
        body: JSON.stringify({ confirmCost: true }),
      });
      setComparison(result);
      if (workspace?.id) rememberComparison(workspace.id, result);
    } catch (reason) {
      setError((reason as Error).message);
    } finally { setBusy(''); }
  }

  async function stopWork() {
    if (!comparison) return;
    const activeArms = comparison.arms.filter(arm => ['queued', 'running'].includes(arm.status));
    await Promise.allSettled(activeArms.map(arm => api(`/api/workspaces/runs/${arm.runId}/cancel`, { method: 'POST', body: '{}' })));
    if (!comparison.id.startsWith('history:')) {
      try {
        const current = await api<WorkspaceComparison>(`/api/workspaces/comparison-runs/${comparison.id}`);
        setComparison(current);
        if (workspace?.id) rememberComparison(workspace.id, current);
      }
      catch (reason) { setError((reason as Error).message); }
    }
  }

  function clearHistory() {
    if (!workspace || active) return;
    const cutoff = new Date().toISOString();
    const cutoffs = historyCutoffs();
    cutoffs[workspace.id] = cutoff;
    window.localStorage.setItem(HISTORY_CUTOFF_STORAGE_KEY, JSON.stringify(cutoffs));
    const comparisons = storedComparisonRefs();
    delete comparisons[workspace.id];
    window.localStorage.setItem(COMPARISON_STORAGE_KEY, JSON.stringify(comparisons));
    setHistoryCutoff(cutoff);
    setRuns([]);
    setComparison(null);
    setReadyTask(null);
    setCostConfirmed(false);
  }

  async function openRun(item: RunSummary) {
    try {
      const sameTask = runs.filter(candidate => candidate.taskId === item.taskId);
      const planSummary = sameTask.find(candidate => candidate.comparison?.arm === 'plan_react') ||
        sameTask.find(candidate => candidate.strategy === 'plan_react');
      const traditionalSummary = sameTask.find(candidate => candidate.comparison?.arm === 'no_learning') ||
        sameTask.find(candidate => candidate.strategy === 'graph_rsi' && candidate.learningEnabled === false);
      const rsiSummary = sameTask.find(candidate => candidate.comparison?.arm === 'online_rsi') ||
        sameTask.find(candidate => candidate.strategy === 'graph_rsi' && candidate.learningEnabled === true);
      const [plan, traditional, rsi] = await Promise.all([
        planSummary ? api<Run>(`/api/workspaces/runs/${planSummary.id}`) : Promise.resolve(null),
        traditionalSummary ? api<Run>(`/api/workspaces/runs/${traditionalSummary.id}`) : Promise.resolve(null),
        rsiSummary ? api<Run>(`/api/workspaces/runs/${rsiSummary.id}`) : Promise.resolve(null),
      ]);
      const arms: ComparisonArm[] = [plan, traditional, rsi].filter((run): run is Run => Boolean(run)).map(run => ({
        arm: run.learningEnabled ? 'online_rsi' : run.strategy === 'plan_react' ? 'plan_react' : 'no_learning',
        runId: run.id,
        taskId: run.taskId,
        createdAt: run.createdAt,
        label: run.learningEnabled ? '图执行 · 在线 RSI' : run.strategy === 'plan_react' ? '传统 Plan + ReAct' : '图执行 · 不学习',
        strategy: run.strategy as ComparisonArm['strategy'],
        status: run.status,
        phase: run.phase,
        timeline: run.events,
        metrics: run.metrics,
        evaluation: run.evaluation,
        submission: run.submission,
        learningEnabled: run.learningEnabled,
        learningWriteEnabled: (run as Run & { learningWriteEnabled?: boolean }).learningWriteEnabled,
        experience: (run as Run & { experience?: ComparisonArm['experience'] }).experience,
        reportUrl: `/api/workspaces/runs/${run.id}/report`,
        reportDownloadUrl: `/api/workspaces/runs/${run.id}/report/download`,
        selectionDownloadUrl: `/api/workspaces/runs/${run.id}/selection/download`,
        runDetail: run,
      }));
      setComparison({ id: `history:${item.taskId}`, taskId: item.taskId, status: comparisonStatus(arms), executionPolicy: 'strict_serial', arms });
    } catch (reason) { setError((reason as Error).message); }
  }

  function filesChanged(event: ChangeEvent<HTMLInputElement>) { if (event.target.files) void addFiles(event.target.files); event.target.value = ''; }
  function dropped(event: DragEvent<HTMLDivElement>) { event.preventDefault(); setDragging(false); if (event.dataTransfer.files) void addFiles(event.dataTransfer.files); }

  const visibleWorkspace: Workspace = workspace || {
    id: '', role: FINANCE_CAPABILITY.key, label: `${FINANCE_CAPABILITY.label}工作区`,
    folderName: '首次输入后创建', folderPath: '上传首份资料或提交工作要求后创建本地目录',
    sources: [], tables: [], tasks: [], reports: [], exports: [],
  };
  const columns = preview?.table.fields || [];
  const visibleError = error.includes('任务引用的资料已被移除') ? '' : error;

  return <main className="workspace-shell">
    <header className="workspace-topbar"><div className="workspace-brand"><Bot size={19} /><span>上传资料，比较传统规划、图执行与在线 RSI</span></div><div className="workspace-topbar-status"><span><i />本次资料独立保存</span><span title={visibleWorkspace.folderPath}><FolderOpen size={12} />{visibleWorkspace.folderName}</span></div></header>
    <section className="workspace-header"><div><p>财务复核 · 输入问题与附件</p><h1>{FINANCE_CAPABILITY.label}</h1><span>{FINANCE_CAPABILITY.caption}</span></div><div className="workspace-capability" aria-label="当前业务能力"><small>FINANCE</small><strong>财务复核</strong><span>当前演示固定能力</span></div></section>

    {visibleError && <div className="workspace-error"><AlertCircle size={16} /><span>{visibleError}</span><button onClick={() => setError('')} title="关闭错误"><X size={15} /></button></div>}
    <section className="workspace-layout">
      <aside className="workspace-sources"><header><div><small>资料</small><strong>{visibleWorkspace.sources.length} 个文件</strong></div><button onClick={() => input.current?.click()} title="添加资料" disabled={active || busy === 'upload'}><Plus size={16} /></button></header>
        <div className={`workspace-drop ${dragging ? 'dragging' : ''}`} onDragEnter={event => { event.preventDefault(); setDragging(true); }} onDragOver={event => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={dropped} onClick={() => input.current?.click()}>
          <UploadCloud size={21} /><strong>{busy === 'upload' ? '正在解析资料' : '拖入资料'}</strong><span>CSV · XLSX · JSON · TXT</span><input ref={input} type="file" accept=".csv,.xlsx,.json,.txt" multiple onChange={filesChanged} />
        </div>
        <div className="workspace-source-list">{visibleWorkspace.sources.map(source => <div key={source.id}><FileText size={15} /><span><strong>{source.name}</strong><small>{source.format.toUpperCase()} · {(source.sizeBytes / 1024).toFixed(1)} KB</small>{source.provenance?.source && <small className="workspace-provenance">{source.provenance.source}</small>}</span><span className="workspace-source-actions">{source.downloadPath && <a href={source.downloadPath} title="下载资料"><ArrowDownToLine size={13} /></a>}<button onClick={() => void removeSource(source)} title="移除资料" disabled={active}><Trash2 size={14} /></button></span></div>)}</div>
        <header className="workspace-table-header"><div><small>数据表</small><strong>{visibleWorkspace.tables.length} 张</strong></div></header>
        <div className="workspace-table-list">{visibleWorkspace.tables.map(table => <button key={table.id} className={table.id === tableId ? 'selected' : ''} onClick={() => setTableId(table.id)}><Table2 size={14} /><span>{table.sheet}<small>{formatCount(table.rowCount)} 行 · {table.fields.length} 列</small></span></button>)}</div>
      </aside>

      <section className="workspace-center">
        <div className="workspace-request"><header><div><small>工作要求</small><strong>{readyTask ? '对比任务已准备' : '输入业务需求'}</strong></div><span>{active ? '执行中' : readyTask ? '可启动' : '未运行'}</span></header>
          <textarea ref={requestArea} value={request} onChange={event => { setRequest(event.target.value); setReadyTask(null); setClarifications([]); }} disabled={active} placeholder="例如：核对订单、支付和退款，列出需要人工复核的金额差异及依据。" />
          <footer>{!readyTask && <button className="workspace-primary" onClick={() => void prepareTask()} disabled={!request.trim() || active || busy === 'prepare'}>{busy === 'prepare' ? <LoaderCircle size={15} /> : <Sparkles size={15} />}解析请求</button>}{readyTask && <><label className="workspace-cost"><input type="checkbox" checked={costConfirmed} onChange={event => setCostConfirmed(event.target.checked)} disabled={active} /><span>确认 3 次真实运行及模型费用</span></label><button className="workspace-primary" onClick={() => void startWork()} disabled={!costConfirmed || active || busy === 'run'}>{busy === 'run' ? <LoaderCircle size={15} /> : <Play size={15} />}按顺序运行三臂</button></>}{active && <button className="workspace-stop" onClick={() => void stopWork()}><CircleStop size={15} />取消运行</button>}</footer>
        </div>

        {clarifications.length > 0 && <section className="workspace-clarify"><header><MessageSquareText size={17} /><div><small>需要确认</small><strong>补齐影响结论的资料范围</strong></div></header>{clarifications.map(item => <label key={item.id}><span>{item.question}</span><input value={answers[item.id] || ''} onChange={event => setAnswers(current => ({ ...current, [item.id]: event.target.value }))} placeholder="填写说明或上传相应资料" /></label>)}<button className="workspace-secondary" onClick={() => void prepareTask()} disabled={busy === 'prepare'}><RefreshCw size={14} />提交确认</button></section>}

        <details className="workspace-data workspace-data-collapsible"><summary><div><small>资料预览</small><strong>{preview?.table.sheet || '尚未选择数据表'}</strong></div>{preview && <span>{formatCount(preview.table.rowCount)} 行 · {preview.table.fields.length} 列</span>}</summary><div className="workspace-data-body">{preview ? <><details className="employee-audit"><summary>字段类型与缺失值</summary><div className="workspace-fields">{preview.table.fields.map(field => <span key={field}><b>{field}</b><small>{preview.table.types[field]} · 缺失 {preview.table.missing[field] || 0}</small></span>)}</div></details><div className="workspace-table-scroll"><table><thead><tr>{columns.slice(0, 6).map(field => <th key={field}>{field}</th>)}</tr></thead><tbody>{preview.records.map((row, index) => <tr key={String(row.rowId || index)}>{columns.slice(0, 6).map(field => <td key={field}>{String(row[field] ?? '—')}</td>)}</tr>)}</tbody></table></div></> : <div className="workspace-empty"><FolderOpen size={20} /><span>上传资料后显示解析预览</span></div>}</div></details>

      </section>

      <aside className="workspace-history"><header><div><small>工作记录</small><strong>{runs.length} 次 run</strong></div><button className="workspace-clear-history" onClick={clearHistory} disabled={!runs.length || active} title="清空当前页面的历史记录"><Trash2 size={13} />清空历史记录</button></header><div className="workspace-history-list">{runs.map(item => { const task = visibleWorkspace.tasks.find(row => row.id === item.taskId); const selected = item.taskId === comparison?.taskId; return <button key={item.id} className={selected ? 'selected' : ''} onClick={() => void openRun(item)}><span className={item.status}><i />{item.learningEnabled ? 'RSI · ' : item.strategy === 'graph_rsi' ? '不学习 · ' : '传统 · '}{statusName[item.status] || item.status}</span><strong>{task?.title || item.taskId.slice(0, 8)}</strong><small>{optionalTokens(item.metrics)} token · {formatMs(item.metrics.durationMs)}</small></button>; })}{!runs.length && <div className="workspace-history-empty"><FileSearch size={18} /><span>开始三臂工作后，三条真实轨迹会保存在这里。</span></div>}</div></aside>
    </section>

    {(comparison || readyTask) && <section className="workspace-comparison workspace-comparison-wide"><header><div><small>同题 · 同附件 · 同模型</small><h2>三种 Agent 实测对比</h2></div></header>
      <div className="workspace-method-contrast" aria-label="传统规划、图执行不学习与在线 RSI 方法差异">
        <article className="plan"><div><span>A</span><strong>传统 Plan + ReAct</strong></div><p>模型逐步规划并执行。</p></article>
        <article className="traditional"><div><span>B</span><strong>图执行 · 不学习</strong></div><p>每次重新规划，不读取经验。</p></article>
        <article className="rsi"><div><span>C</span><strong>图执行 · 在线 RSI</strong></div><p>复用冻结经验，按当前资料重算。</p></article>
      </div>
      <div className="workspace-attribution-guide"><span><b>运行顺序</b>A → B → C 严格串行</span><span><b>A → B</b> 图运行时与编译方式的差异</span><span><b>B → C</b> 跨任务学习的净贡献</span></div>
      <details className="workspace-experiment-notes">
        <summary>实验说明</summary>
        <div>
          <p>三臂读取同一题目和附件，使用 qwen/qwen3.5-27b、同一工具和预算。A 用于检验传统 Agent 基线；B 与 C 使用相同图运行时，B 不读写跨任务经验，C 只读金融 12 任务冻结知识库。</p>
          <dl>
            <div><dt>执行方式</dt><dd>A 完成后运行 B，B 完成后运行 C；三臂统一使用主 Key</dd></div>
            <div><dt>知识库</dt><dd>{comparison?.knowledgeBase ? `${comparison.knowledgeBase.versionCount || 0} 个版本 · ${comparison.knowledgeBase.releaseId || 'ID 未返回'} · 只读` : '启动后由后端返回版本和 Release ID'}</dd></div>
            <div><dt>阶段计时</dt><dd>只按后端真实事件更新，持续时间从当前事件时间戳计算</dd></div>
          </dl>
        </div>
      </details>
      <div className="workspace-comparison-task" aria-label="本次完整问题"><small>本次完整问题</small><p>{readyTask?.task || request || '当前历史任务未返回完整题面。'}</p></div>
      {comparison && <>
        <WorkspaceStageBoard lanes={[
          { lane: 'plan', run: planRun, waiting: planWaiting },
          { lane: 'traditional', run: traditionalRun, waiting: traditionalWaiting },
          { lane: 'rsi', run: rsiRun, waiting: rsiWaiting },
        ]} />
        <div className="workspace-agent-grid">
          <WorkspaceRunLane arm="plan" run={planRun} waiting={planWaiting} />
          <WorkspaceRunLane arm="traditional" run={traditionalRun} waiting={traditionalWaiting} />
          <WorkspaceRunLane arm="rsi" run={rsiRun} waiting={rsiWaiting} />
        </div>
      </>}
    </section>}
    <WorkspaceLiveOverlay planRun={planRun} traditionalRun={traditionalRun} rsiRun={rsiRun} active={active} />
  </main>;
}
