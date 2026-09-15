import { AlertCircle, ArrowDownToLine, ArrowRight, Bot, Check, ChevronLeft, ChevronRight, CircleStop, FileBarChart2, FilePlus2, FileSearch, FileText, FolderOpen, LoaderCircle, MessageSquareText, Network, PanelRightOpen, Play, Plus, RefreshCw, ShieldCheck, Sparkles, Table2, Trash2, UploadCloud, X } from 'lucide-react';
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
type TraceEvent = { seq: number; type: string; title: string; detail?: any; elapsedMs?: number; metrics?: Metrics };
type Metrics = { modelRequests?: number; toolCalls?: number; inputTokens?: number; outputTokens?: number; durationMs?: number; toolErrors?: number; reportAttempts?: number; runtimeOverheadMs?: number };
type Run = { id: string; taskId: string; status: string; phase: string; strategy: string; events: TraceEvent[]; metrics: Metrics; evaluation?: { status: string; issues?: string[] }; trajectoryMatch?: unknown; submission?: { groups?: { name: string; reason: string; condition: string; count: number; selectedIds: string[]; evidenceIds: string[] }[]; metrics?: Record<string, unknown>; selectedIds?: string[]; evidenceIds?: string[]; summary?: string; assumptions?: string[] }; graph?: { nodes: GraphNode[]; nodeStates: Record<string, string> }; fallback?: string; evolution?: { planningPath?: string; usedVersionId?: string; generation?: number; matchVersion?: number; trajectoryCompilation?: unknown; currentBindings?: unknown; lookupMs?: number; localCompileMs?: number; bindingMs?: number }; error?: string; learningEnabled?: boolean; pollUrl?: string; reportUrl?: string; reportDownloadUrl?: string; selectionDownloadUrl?: string };
type GraphNode = { id: string; tool: string; dependencies: string[]; foreach?: unknown; reuse?: unknown; defer?: boolean };
type RunSummary = { id: string; taskId: string; status: string; phase: string; strategy: string; createdAt: string; metrics: Metrics; evaluation: { status: string } };

const ROLES: { key: Role; label: string; caption: string }[] = [
  { key: 'finance', label: '财务运营', caption: '订单、支付、退款与异常复核' },
  { key: 'support', label: '客服运营', caption: '投诉、响应、渠道与跟进队列' },
  { key: 'tickets', label: '技术工单', caption: '分诊、阻塞、活动与变更比较' },
];
const formatCount = (value?: number) => new Intl.NumberFormat('zh-CN').format(value || 0);
const formatMs = (value?: number) => value == null ? '—' : value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${Math.round(value)}ms`;
const totalTokens = (metrics?: Metrics) => (metrics?.inputTokens || 0) + (metrics?.outputTokens || 0);
const statusName: Record<string, string> = { queued: '排队', running: '处理中', completed: '已完成', limited: '受限停止', cancelled: '已取消', failed: '失败', passed: '硬校验通过', user_review_required: '等待复核', failed_evaluation: '未通过校验' };

function eventTitle(event: TraceEvent): string {
  if (event.type === 'model_start') return 'LLM 正在判断下一步';
  if (event.type === 'model') return 'LLM 已返回业务动作';
  if (event.type === 'plan') return '生成当前数据计划';
  if (event.type === 'graph_created') return 'RSI 结构化图已建立';
  if (event.type === 'graph') return `RSI 节点 ${event.title}`;
  if (event.type === 'binding') return '绑定当前资料参数';
  if (event.type === 'action') return `调用 ${event.title}`;
  if (event.type === 'observation') return `获得 ${event.title} 结果`;
  if (event.type === 'fallback') return '结构不适用，交回模型';
  if (event.type === 'report_recovery') return '报告校验恢复';
  if (event.type === 'evaluation') return '结构化成果校验';
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

function eventDetailLines(event: TraceEvent): string[] {
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
        `执行者：${detail.executor === 'graph' ? 'RSI 结构化运行时' : 'LLM 调度'}`,
        ...Object.entries(argumentsValue || {}).slice(0, 6).map(([key, value]) => `${key}：${compactValue(value)}`),
      ];
    } catch {
      return [`执行者：${detail.executor === 'graph' ? 'RSI 结构化运行时' : 'LLM 调度'}`];
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
  runId: string;
  taskId: string;
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
  runDetail?: Run;
};
type WorkspaceComparison = {
  id: string;
  taskId: string;
  status: string;
  executionPolicy: 'strict_serial';
  arms: ComparisonArm[];
};
type StoredComparisonRef = { comparisonId: string; taskId: string };

const COMPARISON_STORAGE_KEY = 'rsi-workspace-comparisons-v1';
const LAST_WORKSPACE_STORAGE_KEY = 'rsi-last-workspace-v1';
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
const rememberWorkspace = (workspaceId: string) => {
  if (workspaceId) window.localStorage.setItem(LAST_WORKSPACE_STORAGE_KEY, workspaceId);
};

const comparisonArm = (comparison: WorkspaceComparison | null, strategy: ComparisonArm['strategy']) =>
  comparison?.arms.find(arm => arm.strategy === strategy) || null;
const armRun = (arm?: ComparisonArm | null): Run | null => arm ? {
  ...arm.runDetail,
  id: arm.runId,
  taskId: arm.taskId,
  status: arm.status,
  phase: arm.phase || arm.runDetail?.phase || '',
  strategy: arm.strategy,
  events: arm.timeline || arm.runDetail?.events || [],
  metrics: arm.metrics || arm.runDetail?.metrics || {},
  evaluation: arm.evaluation || arm.runDetail?.evaluation,
  submission: arm.submission || arm.runDetail?.submission,
  pollUrl: arm.pollUrl || arm.runDetail?.pollUrl,
  reportUrl: arm.reportUrl || arm.runDetail?.reportUrl,
  reportDownloadUrl: arm.reportDownloadUrl || arm.runDetail?.reportDownloadUrl,
  selectionDownloadUrl: arm.selectionDownloadUrl || arm.runDetail?.selectionDownloadUrl,
} : null;
const comparisonStatus = (arms: ComparisonArm[]) => {
  const statuses = new Set(arms.map(arm => arm.status));
  if (statuses.has('running')) return 'running';
  if (statuses.has('queued')) return 'queued';
  if (statuses.size === 1 && statuses.has('completed')) return 'completed';
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

function WorkspaceRunLane({
  arm,
  run,
  error,
  waiting,
}: {
  arm: 'traditional' | 'rsi';
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
  const learningState = run
    ? (run as Run & { learningEnabled?: boolean }).learningEnabled === true
      ? '在线学习已开启'
      : (run as Run & { learningEnabled?: boolean }).learningEnabled === false
        ? '在线学习已关闭'
        : '学习写入状态未返回'
    : '等待运行创建';

  return <article className={`workspace-agent-lane ${arm}`}>
    <header>
      <div>
        <small>{isRsi ? 'ONLINE RSI AGENT' : 'TRADITIONAL AGENT'}</small>
        <h3>{isRsi ? '在线 RSI Agent' : '传统 Agent'}</h3>
      </div>
      <span className={run?.status === 'completed' ? 'done' : activeRun(run) ? 'active' : error ? 'failed' : ''}>
        {run ? statusName[run.status] || run.status : error ? '启动失败' : waiting}
      </span>
    </header>

    <div className="workspace-agent-metrics">
      <Metric label="LLM 请求" value={optionalCount(run?.metrics.modelRequests)} hint="真实 provider 请求" />
      <Metric label="Token" value={optionalTokens(run?.metrics)} hint="输入 + 输出" />
      <Metric label="工具调用" value={optionalCount(run?.metrics.toolCalls)} hint={run?.metrics.toolErrors == null ? '错误数等待/不可用' : `${formatCount(run.metrics.toolErrors)} 次错误`} />
      <Metric label="串行耗时" value={run ? formatMs(run.metrics.durationMs) : '等待/不可用'} hint={run?.phase || '端到端'} />
    </div>

    <div className="workspace-agent-current">
      <span>{activeRun(run) ? '正在执行' : terminalRun(run) ? '执行已保存' : '等待真实 run'}</span>
      <strong>{selectedEvent ? eventTitle(selectedEvent) : waiting}</strong>
      <small>{run ? `${events.length} 个真实事件 · ${run.id}` : '后端创建 run 后开始显示事件'}</small>
      {isRsi && <em>{learningState}</em>}
    </div>

    {error && <p className="workspace-run-error">{error}</p>}

    <div className="workspace-lane-events" aria-label={`${isRsi ? '在线 RSI Agent' : '传统 Agent'}真实事件`}>
      {events.map(event => <button
        key={event.seq}
        className={`${eventChannel(event)} ${selectedEvent?.seq === event.seq ? 'selected' : ''}`}
        onClick={() => setSelectedEventSeq(event.seq)}
      >
        <i>{eventChannel(event) === 'model' ? 'M' : eventChannel(event) === 'rsi' ? 'R' : eventChannel(event) === 'tool' ? 'T' : 'C'}</i>
        <span><strong>{eventTitle(event)}</strong><small>{event.elapsedMs == null ? '时间未返回' : formatMs(event.elapsedMs)}</small></span>
        {event.type === 'observation' && event.detail?.ok === false && <em>错误</em>}
      </button>)}
      {!events.length && <p>{error ? '该臂没有可回放事件。' : waiting}</p>}
    </div>

    {selectedEvent && <div className={`workspace-event-detail ${eventChannel(selectedEvent)}`}>
      <header>
        <span>{eventChannel(selectedEvent) === 'model' ? 'LLM' : eventChannel(selectedEvent) === 'rsi' ? 'RSI RUNTIME' : eventChannel(selectedEvent) === 'tool' ? 'TOOL' : 'CONTROL'}</span>
        <strong>{eventTitle(selectedEvent)}</strong>
      </header>
      {eventDetailLines(selectedEvent).length > 0
        ? <ul>{eventDetailLines(selectedEvent).map((line, index) => <li key={`${selectedEvent.seq}-${index}`}>{line}</li>)}</ul>
        : <p>该真实事件没有返回额外展示字段。</p>}
    </div>}

    <details className="workspace-agent-audit">
      <summary>技术审计 · 图、参数与完整轨迹</summary>
      {run ? <>
        <GraphView run={run} />
        {Boolean(run.trajectoryMatch || run.evolution?.trajectoryCompilation) && <div className="workspace-trajectory">
          <strong>轨迹来源 · G{run.evolution?.generation ?? '—'} / M{run.evolution?.matchVersion ?? '—'}</strong>
          <pre>{JSON.stringify({ match: run.trajectoryMatch, compilation: run.evolution?.trajectoryCompilation }, null, 2)}</pre>
        </div>}
      </> : <p>等待后端返回运行结构。</p>}
    </details>

    <section className="workspace-lane-report">
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
    </section>
  </article>;
}

export default function WorkspaceWorkbench() {
  const input = useRef<HTMLInputElement>(null);
  const requestArea = useRef<HTMLTextAreaElement>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [savedWorkspaces, setSavedWorkspaces] = useState<Workspace[]>([]);
  useEffect(() => {
    void api<Workspace[]>('/api/workspaces').then(items => {
      setSavedWorkspaces(items);
      const lastWorkspaceId = window.localStorage.getItem(LAST_WORKSPACE_STORAGE_KEY);
      const lastWorkspace = items.find(item => item.id === lastWorkspaceId);
      if (lastWorkspace) void activateWorkspace(lastWorkspace);
    }).catch(() => {});
  }, []);
  const [role, setRole] = useState<Role>('finance');
  const [tableId, setTableId] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [request, setRequest] = useState('');
  const [readyTask, setReadyTask] = useState<WorkspaceTask | null>(null);
  const [clarifications, setClarifications] = useState<{ id: string; question: string }[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [costConfirmed, setCostConfirmed] = useState(false);
  const [comparison, setComparison] = useState<WorkspaceComparison | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [followup, setFollowup] = useState('');
  const [busy, setBusy] = useState<'workspace' | 'upload' | 'prepare' | 'run' | ''>('');
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');

  const selectedRole = ROLES.find(item => item.key === role) || ROLES[0];
  const traditionalArm = comparisonArm(comparison, 'plan_react');
  const rsiArm = comparisonArm(comparison, 'graph_rsi');
  const traditionalRun = armRun(traditionalArm);
  const rsiRun = armRun(rsiArm);
  const active = Boolean(busy === 'run' || comparison && ['queued', 'running'].includes(comparison.status));
  const referenceRun = rsiRun || traditionalRun;

  useEffect(() => {
    const area = requestArea.current;
    if (!area) return;
    area.style.height = 'auto';
    area.style.height = `${Math.max(122, area.scrollHeight)}px`;
  }, [request]);

  async function createWorkspace(nextRole: Role, resetDraft = true): Promise<Workspace | null> {
    setBusy('workspace'); setError('');
    if (resetDraft) {
      setComparison(null); setReadyTask(null); setClarifications([]); setAnswers({}); setCostConfirmed(false); setRequest('');
    }
    try {
      const item = await api<Workspace>('/api/workspaces', { method: 'POST', body: JSON.stringify({ role: nextRole, label: `${ROLES.find(roleItem => roleItem.key === nextRole)?.label || nextRole}工作区` }) });
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
    setSavedWorkspaces(current => [item, ...current.filter(value => value.id !== item.id)]);
    if (!tableId && item.tables[0]) setTableId(item.tables[0].id);
    const history = await api<{ runs: RunSummary[] }>(`/api/workspaces/runs?workspaceId=${id}`);
    setRuns(history.runs);
  }

  async function restoreComparison(workspaceId: string, workspaceSnapshot?: Workspace) {
    const saved = storedComparisonRefs()[workspaceId];
    if (!saved) { setComparison(null); return; }
    try {
      const restored = await api<WorkspaceComparison>(`/api/workspaces/comparison-runs/${saved.comparisonId}`);
      setComparison(restored);
      const task = (workspaceSnapshot || workspace)?.tasks.find(item => item.id === saved.taskId);
      if (task) { setReadyTask(task); setRequest(task.task); }
    } catch (reason) {
      setError(`无法恢复已保存的双轨执行：${(reason as Error).message}`);
    }
  }

  async function activateWorkspace(item: Workspace) {
    setRole(item.role); setWorkspace(item); setTableId(item.tables[0]?.id || ''); setComparison(null);
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

  function chooseRole(nextRole: Role) {
    if (nextRole === role) return;
    setRole(nextRole); setWorkspace(null); setTableId(''); setPreview(null); setComparison(null); setRuns([]);
    setReadyTask(null); setClarifications([]); setAnswers({}); setCostConfirmed(false); setFollowup(''); setRequest('');
  }

  async function addFiles(files: FileList | File[]) {
    const pendingFiles = Array.from(files);
    if (!pendingFiles.length || busy) return;
    const target = workspace || await createWorkspace(role, false);
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

  async function prepareTask(followupRunId?: string) {
    const target = workspace || await createWorkspace(role, false);
    if (!target) return;
    setBusy('prepare'); setError(''); setClarifications([]);
    try {
      const body = { request: followupRunId ? followup : request, answers, followupRunId };
      const response = await api<{ status: string; task?: WorkspaceTask; clarifications?: { id: string; question: string }[] }>(`/api/workspaces/${target.id}/tasks`, { method: 'POST', body: JSON.stringify(body) });
      if (response.status === 'needs_clarification') { setClarifications(response.clarifications || []); return; }
      const nextTask = response.task || null;
      setReadyTask(nextTask);
      if (followupRunId && nextTask?.task) setRequest(nextTask.task);
      setCostConfirmed(false); setFollowup(''); await refreshWorkspace(target.id);
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

  async function openRun(item: RunSummary) {
    try {
      const sameTask = runs.filter(candidate => candidate.taskId === item.taskId);
      const traditionalSummary = sameTask.find(candidate => candidate.strategy === 'plan_react');
      const rsiSummary = sameTask.find(candidate => candidate.strategy === 'graph_rsi');
      const [traditional, rsi] = await Promise.all([
        traditionalSummary ? api<Run>(`/api/workspaces/runs/${traditionalSummary.id}`) : Promise.resolve(null),
        rsiSummary ? api<Run>(`/api/workspaces/runs/${rsiSummary.id}`) : Promise.resolve(null),
      ]);
      const arms: ComparisonArm[] = [traditional, rsi].filter((run): run is Run => Boolean(run)).map(run => ({
        runId: run.id,
        taskId: run.taskId,
        label: run.strategy === 'graph_rsi' ? 'Graph RSI · 历史图执行' : '传统 Agent · 每次规划',
        strategy: run.strategy as ComparisonArm['strategy'],
        status: run.status,
        phase: run.phase,
        timeline: run.events,
        metrics: run.metrics,
        evaluation: run.evaluation,
        submission: run.submission,
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
    id: '', role, label: `${selectedRole.label}工作区`,
    folderName: '首次输入后创建', folderPath: '上传首份资料或提交工作要求后创建本地目录',
    sources: [], tables: [], tasks: [], reports: [], exports: [],
  };
  const columns = preview?.table.fields || [];

  return <main className="workspace-shell">
    <header className="workspace-topbar"><div className="workspace-brand"><Bot size={19} /><span>上传资料，交给两个数字员工对照分析</span></div><div className="workspace-topbar-status"><span><i />本次资料独立保存</span><span title={visibleWorkspace.folderPath}><FolderOpen size={12} />{visibleWorkspace.folderName}</span></div></header>
    <details className="workspace-return"><summary>继续之前的工作</summary><select aria-label="选择已保存工作区" value={workspace?.id || ''} disabled={active} onChange={event => { const old = savedWorkspaces.find(w => w.id === event.target.value); if (old) void activateWorkspace(old); }}><option value="">选择已保存的业务工作</option>{savedWorkspaces.filter(w => w.sources.length > 0 || w.tasks.length > 0).map(w => <option key={w.id} value={w.id}>{w.label} · {w.tasks.length} 次请求</option>)}</select></details>
    <section className="workspace-header"><div><p>选择业务能力 · 输入问题与附件</p><h1>{selectedRole.label}</h1><span>{selectedRole.caption}</span></div><div className="workspace-role-picker">{ROLES.map(item => <button key={item.key} className={item.key === role ? 'selected' : ''} onClick={() => chooseRole(item.key)} disabled={active || busy === 'workspace'}><small>{item.key === 'finance' ? 'FINANCE' : item.key === 'support' ? 'SUPPORT' : 'ENGINEERING'}</small>{item.label}</button>)}</div></section>

    {error && <div className="workspace-error"><AlertCircle size={16} /><span>{error}</span><button onClick={() => setError('')} title="关闭错误"><X size={15} /></button></div>}
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
        <div className="workspace-request"><header><div><small>工作要求</small><strong>{readyTask?.followupRunId ? '已准备追问任务' : readyTask ? '已准备双轨任务' : '输入业务需求'}</strong></div><span>{active ? '双轨执行中' : readyTask?.followupRunId ? '追问等待启动' : readyTask ? '等待启动' : '未运行'}</span></header>
          <textarea ref={requestArea} value={request} onChange={event => { setRequest(event.target.value); setReadyTask(null); setClarifications([]); }} disabled={active} placeholder={role === 'finance' ? '例如：核对订单、支付和退款，列出需要人工复核的金额差异及依据。' : role === 'support' ? '例如：按投诉渠道、企业响应与公开叙述生成跟进队列，并标出待核查项。' : '例如：按未分派、里程碑和活动记录形成工程分诊清单，给出每项依据。'} />
          <footer>{!readyTask && <button className="workspace-primary" onClick={() => void prepareTask()} disabled={!request.trim() || active || busy === 'prepare'}>{busy === 'prepare' ? <LoaderCircle size={15} /> : <Sparkles size={15} />}解析请求</button>}{readyTask && <><div className="workspace-dual-protocol"><strong>两个 run 同时创建</strong><span>模型请求严格串行，排队臂等待模型槽</span></div><label className="workspace-cost"><input type="checkbox" checked={costConfirmed} onChange={event => setCostConfirmed(event.target.checked)} disabled={active} /><span>我确认启动 2 次真实 Agent 运行并产生模型费用</span></label><button className="workspace-primary" onClick={() => void startWork()} disabled={!costConfirmed || active || busy === 'run'}>{busy === 'run' ? <LoaderCircle size={15} /> : <Play size={15} />}开始双轨对照</button></>}{active && <button className="workspace-stop" onClick={() => void stopWork()}><CircleStop size={15} />取消两臂</button>}</footer>
        </div>

        {clarifications.length > 0 && <section className="workspace-clarify"><header><MessageSquareText size={17} /><div><small>需要确认</small><strong>补齐影响结论的资料范围</strong></div></header>{clarifications.map(item => <label key={item.id}><span>{item.question}</span><input value={answers[item.id] || ''} onChange={event => setAnswers(current => ({ ...current, [item.id]: event.target.value }))} placeholder="填写说明或上传相应资料" /></label>)}<button className="workspace-secondary" onClick={() => void prepareTask()} disabled={busy === 'prepare'}><RefreshCw size={14} />提交确认</button></section>}

        <section className="workspace-data"><header><div><small>资料预览</small><strong>{preview?.table.sheet || '尚未选择数据表'}</strong></div>{preview && <span>{formatCount(preview.table.rowCount)} 行 · {preview.table.fields.length} 列</span>}</header>{preview ? <><details className="employee-audit"><summary>字段类型与缺失值</summary><div className="workspace-fields">{preview.table.fields.map(field => <span key={field}><b>{field}</b><small>{preview.table.types[field]} · 缺失 {preview.table.missing[field] || 0}</small></span>)}</div></details><div className="workspace-table-scroll"><table><thead><tr>{columns.slice(0, 6).map(field => <th key={field}>{field}</th>)}</tr></thead><tbody>{preview.records.map((row, index) => <tr key={String(row.rowId || index)}>{columns.slice(0, 6).map(field => <td key={field}>{String(row[field] ?? '—')}</td>)}</tr>)}</tbody></table></div></> : <div className="workspace-empty"><FolderOpen size={20} /><span>上传资料后显示解析预览</span></div>}</section>

        {(comparison || readyTask) && <section className="workspace-comparison"><header><div><small>同一任务 · 两个真实 RUN</small><h2>传统 Agent 与在线 RSI Agent</h2></div><p>两臂读取同一任务和附件。两个 run 同时创建，模型请求严格串行。页面只展示后端保存的状态、事件、用量与报告。</p></header><div className="workspace-agent-grid">
          <WorkspaceRunLane arm="traditional" run={traditionalRun} waiting={comparison ? (traditionalArm?.status === 'queued' ? '已创建，等待模型槽' : '后端未返回传统 run') : '等待点击启动'} />
          <WorkspaceRunLane arm="rsi" run={rsiRun} waiting={comparison ? (rsiArm?.status === 'queued' ? '已创建，等待模型槽' : '后端未返回 RSI run') : '等待点击启动'} />
        </div></section>}
      </section>

      <aside className="workspace-history"><header><div><small>工作记录</small><strong>{runs.length} 次 run</strong></div><PanelRightOpen size={16} /></header><div className="workspace-history-list">{runs.map(item => { const task = visibleWorkspace.tasks.find(row => row.id === item.taskId); const selected = item.taskId === comparison?.taskId; return <button key={item.id} className={selected ? 'selected' : ''} onClick={() => void openRun(item)}><span className={item.status}><i />{item.strategy === 'graph_rsi' ? 'RSI · ' : '传统 · '}{statusName[item.status] || item.status}</span><strong>{task?.title || item.taskId.slice(0, 8)}</strong><small>{task?.followupRunId ? '追问 · ' : ''}{optionalTokens(item.metrics)} token · {formatMs(item.metrics.durationMs)}</small></button>; })}{!runs.length && <div className="workspace-history-empty"><FileSearch size={18} /><span>开始双轨工作后，两臂真实轨迹会保存在这里。</span></div>}</div>{referenceRun && !active && <section className="workspace-followup"><small>继续追问</small><textarea value={followup} onChange={event => setFollowup(event.target.value)} placeholder="基于当前报告继续分析…" /><button onClick={() => void prepareTask(referenceRun.id)} disabled={!followup.trim() || busy === 'prepare'}><ArrowRight size={14} />准备双轨追问</button></section>}</aside>
    </section>
  </main>;
}
