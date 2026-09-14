import { AlertCircle, ArrowDownToLine, ArrowRight, Bot, Check, ChevronLeft, ChevronRight, CircleStop, FileBarChart2, FilePlus2, FileSearch, FileText, FolderOpen, LoaderCircle, MessageSquareText, Network, PanelRightOpen, Play, Plus, RefreshCw, ShieldCheck, Sparkles, Table2, Trash2, UploadCloud, X } from 'lucide-react';
import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from 'react';
import { api, upload } from './api';
import './workspace.css';

type Role = 'finance' | 'support' | 'tickets';
type Table = { id: string; sourceId: string; sourceName: string; sheet: string; fields: string[]; types: Record<string, string>; missing: Record<string, number>; rowCount: number };
type Source = { id: string; name: string; format: string; sizeBytes: number; tableIds: string[]; status: string; downloadPath?: string; provenance?: { kind?: string; source?: string } };
type WorkspaceTask = { id: string; title: string; task: string; createdAt: string; split: string; scenario: Role; sourceStatus?: string; followupRunId?: string | null };
type Workspace = { id: string; role: Role; label: string; sources: Source[]; tables: Table[]; tasks: WorkspaceTask[]; reports: ReportSummary[]; exports: ExportItem[] };
type Preview = { table: Table; records: Record<string, unknown>[] };
type ReportSummary = { id: string; runId: string; taskId: string; title: string; createdAt: string; metrics: Record<string, unknown>; selectedIds: string[]; evidenceCount: number; summary: string };
type ExportItem = { id: string; name: string; rowCount: number; createdAt: string };
type TraceEvent = { seq: number; type: string; title: string; detail?: any; elapsedMs?: number; metrics?: Metrics };
type Metrics = { modelRequests?: number; toolCalls?: number; inputTokens?: number; outputTokens?: number; durationMs?: number; toolErrors?: number; reportAttempts?: number; runtimeOverheadMs?: number };
type Run = { id: string; taskId: string; status: string; phase: string; strategy: string; events: TraceEvent[]; metrics: Metrics; evaluation: { status: string; issues?: string[] }; submission?: { metrics?: Record<string, unknown>; selectedIds?: string[]; evidenceIds?: string[]; summary?: string; assumptions?: string[] }; graph?: { nodes: GraphNode[]; nodeStates: Record<string, string> }; fallback?: string; evolution?: { planningPath?: string; usedVersionId?: string; lookupMs?: number; localCompileMs?: number; bindingMs?: number }; error?: string };
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

export default function WorkspaceWorkbench() {
  const input = useRef<HTMLInputElement>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [role, setRole] = useState<Role>('finance');
  const [tableId, setTableId] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [request, setRequest] = useState('');
  const [readyTask, setReadyTask] = useState<WorkspaceTask | null>(null);
  const [clarifications, setClarifications] = useState<{ id: string; question: string }[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [costConfirmed, setCostConfirmed] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [strategy, setStrategy] = useState<'plan_react' | 'graph_rsi'>('graph_rsi');
  const [followup, setFollowup] = useState('');
  const [busy, setBusy] = useState<'workspace' | 'upload' | 'prepare' | 'run' | ''>('');
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');
  const [selectedEventSeq, setSelectedEventSeq] = useState<number | null>(null);

  const selectedRole = ROLES.find(item => item.key === role) || ROLES[0];
  const active = run && ['queued', 'running'].includes(run.status);
  const replayEvents = useMemo(() => (run?.events || []).filter(event => !['model_start'].includes(event.type)), [run]);
  const selectedEvent = replayEvents.find(event => event.seq === selectedEventSeq) || replayEvents.at(-1);
  const selectedEventIndex = Math.max(0, replayEvents.findIndex(event => event.seq === selectedEvent?.seq));
  const exports = useMemo(() => (run?.events || []).flatMap(event => event.detail?.result?.downloadPath ? [{ path: event.detail.result.downloadPath, rowCount: event.detail.result.rowCount }] : []), [run]);
  async function createWorkspace(nextRole: Role) {
    setBusy('workspace'); setError(''); setRun(null); setReadyTask(null); setClarifications([]); setAnswers({}); setCostConfirmed(false); setRequest('');
    setStrategy('graph_rsi');
    try {
      const item = await api<Workspace>('/api/workspaces', { method: 'POST', body: JSON.stringify({ role: nextRole, label: `${ROLES.find(roleItem => roleItem.key === nextRole)?.label || nextRole}工作区` }) });
      setWorkspace(item); setTableId(item.tables[0]?.id || ''); setPreview(null); setRuns([]);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(''); }
  }

  async function refreshWorkspace(id = workspace?.id) {
    if (!id) return;
    const item = await api<Workspace>(`/api/workspaces/${id}`);
    setWorkspace(item);
    if (!tableId && item.tables[0]) setTableId(item.tables[0].id);
    const history = await api<{ runs: RunSummary[] }>(`/api/workspaces/runs?workspaceId=${id}`);
    setRuns(history.runs);
  }

  useEffect(() => { void createWorkspace('finance'); }, []);
  useEffect(() => { setSelectedEventSeq(null); }, [run?.id]);
  useEffect(() => {
    if (!workspace || !tableId) { setPreview(null); return; }
    api<Preview>(`/api/workspaces/${workspace.id}/tables/${encodeURIComponent(tableId)}/preview`).then(setPreview).catch(reason => setError(reason.message));
  }, [workspace?.id, tableId]);
  useEffect(() => {
    if (!run || !active) return;
    const timer = window.setInterval(() => {
      api<Run>(`/api/workspaces/runs/${run.id}`).then(value => { setRun(value); if (!['queued', 'running'].includes(value.status)) void refreshWorkspace(); }).catch(reason => setError(reason.message));
    }, 800);
    return () => window.clearInterval(timer);
  }, [run?.id, active]);

  async function chooseRole(nextRole: Role) { setRole(nextRole); await createWorkspace(nextRole); }
  async function addFiles(files: FileList | File[]) {
    if (!workspace || !files.length || busy) return;
    setBusy('upload'); setError('');
    try {
      for (const file of Array.from(files)) await upload(`/api/workspaces/${workspace.id}/files`, file);
      await refreshWorkspace();
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
    if (!workspace) return;
    setBusy('prepare'); setError(''); setClarifications([]);
    try {
      const body = { request: followupRunId ? followup : request, answers, followupRunId };
      const response = await api<{ status: string; task?: WorkspaceTask; clarifications?: { id: string; question: string }[] }>(`/api/workspaces/${workspace.id}/tasks`, { method: 'POST', body: JSON.stringify(body) });
      if (response.status === 'needs_clarification') { setClarifications(response.clarifications || []); return; }
      const nextTask = response.task || null;
      setReadyTask(nextTask);
      // A follow-up is a distinct task. Keep the visible request synchronized
      // with the task that will actually be sent to the runtime.
      if (followupRunId && nextTask?.task) setRequest(nextTask.task);
      setCostConfirmed(false); setFollowup(''); await refreshWorkspace();
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(''); }
  }
  async function startWork() {
    if (!readyTask || !costConfirmed) return;
    setBusy('run'); setError('');
    try {
      const result = await api<{ id: string }>(`/api/workspaces/tasks/${readyTask.id}/runs`, { method: 'POST', body: JSON.stringify({ strategy, confirmCost: true }) });
      setRun(await api<Run>(`/api/workspaces/runs/${result.id}`));
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(''); }
  }
  async function stopWork() {
    if (!run) return;
    await api(`/api/workspaces/runs/${run.id}/cancel`, { method: 'POST', body: '{}' });
  }
  async function openRun(item: RunSummary) { try { setRun(await api<Run>(`/api/workspaces/runs/${item.id}`)); } catch (reason) { setError((reason as Error).message); } }
  function filesChanged(event: ChangeEvent<HTMLInputElement>) { if (event.target.files) void addFiles(event.target.files); event.target.value = ''; }
  function dropped(event: DragEvent<HTMLDivElement>) { event.preventDefault(); setDragging(false); if (event.dataTransfer.files) void addFiles(event.dataTransfer.files); }

  if (!workspace) return <main className="workspace-shell"><div className="workspace-loading"><LoaderCircle size={20} />准备工作区</div></main>;
  const report = run?.submission;
  const columns = preview?.table.fields || [];
  return <main className="workspace-shell">
    <header className="workspace-topbar"><div className="workspace-brand"><Bot size={19} /><span>OPERATIONS EMPLOYEE</span><small>WORKSPACE</small></div><div className="workspace-topbar-status"><span><i />当前资料隔离</span><span>模型思考关闭</span><a href="#experiments">实验中心</a></div></header>
    <section className="workspace-header"><div><p>三岗位数字员工</p><h1>{selectedRole.label}</h1><span>{selectedRole.caption}</span></div><div className="workspace-role-picker">{ROLES.map(item => <button key={item.key} className={item.key === role ? 'selected' : ''} onClick={() => void chooseRole(item.key)} disabled={Boolean(active) || busy === 'workspace'}><small>{item.key === 'finance' ? 'FINANCE' : item.key === 'support' ? 'SUPPORT' : 'ENGINEERING'}</small>{item.label}</button>)}</div></section>

    {error && <div className="workspace-error"><AlertCircle size={16} /><span>{error}</span><button onClick={() => setError('')} title="关闭错误"><X size={15} /></button></div>}
    <section className="workspace-layout">
      <aside className="workspace-sources"><header><div><small>资料</small><strong>{workspace.sources.length} 个文件</strong></div><button onClick={() => input.current?.click()} title="添加资料" disabled={Boolean(active) || busy === 'upload'}><Plus size={16} /></button></header>
        <div className={`workspace-drop ${dragging ? 'dragging' : ''}`} onDragEnter={event => { event.preventDefault(); setDragging(true); }} onDragOver={event => event.preventDefault()} onDragLeave={() => setDragging(false)} onDrop={dropped} onClick={() => input.current?.click()}>
          <UploadCloud size={21} /><strong>{busy === 'upload' ? '正在解析资料' : '拖入资料'}</strong><span>CSV · XLSX · JSON · TXT</span><input ref={input} type="file" accept=".csv,.xlsx,.json,.txt" multiple onChange={filesChanged} />
        </div>
        <div className="workspace-source-list">{workspace.sources.map(source => <div key={source.id}><FileText size={15} /><span><strong>{source.name}</strong><small>{source.format.toUpperCase()} · {(source.sizeBytes / 1024).toFixed(1)} KB</small>{source.provenance?.source && <small className="workspace-provenance">{source.provenance.source}</small>}</span><span className="workspace-source-actions">{source.downloadPath && <a href={source.downloadPath} title="下载资料"><ArrowDownToLine size={13} /></a>}<button onClick={() => void removeSource(source)} title="移除资料" disabled={Boolean(active)}><Trash2 size={14} /></button></span></div>)}</div>
        <header className="workspace-table-header"><div><small>数据表</small><strong>{workspace.tables.length} 张</strong></div></header>
        <div className="workspace-table-list">{workspace.tables.map(table => <button key={table.id} className={table.id === tableId ? 'selected' : ''} onClick={() => setTableId(table.id)}><Table2 size={14} /><span>{table.sheet}<small>{formatCount(table.rowCount)} 行 · {table.fields.length} 列</small></span></button>)}</div>
      </aside>
      <section className="workspace-center">
        <div className="workspace-request"><header><div><small>工作要求</small><strong>{readyTask?.followupRunId ? '已准备追问任务' : readyTask ? '已准备当前任务' : '输入业务需求'}</strong></div><span>{active ? run?.phase || '执行中' : readyTask?.followupRunId ? '追问等待启动' : readyTask ? '等待启动' : '未运行'}</span></header>
          <textarea value={request} onChange={event => { setRequest(event.target.value); setReadyTask(null); setClarifications([]); }} disabled={Boolean(active)} placeholder={role === 'finance' ? '例如：核对订单、支付和退款，列出需要人工复核的金额差异及依据。' : role === 'support' ? '例如：按投诉渠道、企业响应与公开叙述生成跟进队列，并标出待核查项。' : '例如：按未分派、里程碑和活动记录形成工程分诊清单，给出每项依据。'} />
          <footer>{!readyTask && <button className="workspace-primary" onClick={() => void prepareTask()} disabled={!request.trim() || Boolean(active) || busy === 'prepare'}>{busy === 'prepare' ? <LoaderCircle size={15} /> : <Sparkles size={15} />}解析请求</button>}{readyTask && <><div className="workspace-strategy-picker" role="group" aria-label="本次工作策略"><button className={strategy === 'graph_rsi' ? 'selected' : ''} onClick={() => setStrategy('graph_rsi')} disabled={Boolean(active)}><small>GRAPH RSI</small>结构化执行</button><button className={strategy === 'plan_react' ? 'selected' : ''} onClick={() => setStrategy('plan_react')} disabled={Boolean(active)}><small>PLAN + REACT</small>模型调度</button></div><label className="workspace-cost"><input type="checkbox" checked={costConfirmed} onChange={event => setCostConfirmed(event.target.checked)} disabled={Boolean(active)} /><span>我确认这会启动一次真实模型 Agent</span></label><button className="workspace-primary" onClick={() => void startWork()} disabled={!costConfirmed || Boolean(active) || busy === 'run'}>{busy === 'run' ? <LoaderCircle size={15} /> : <Play size={15} />}开始工作</button></>}{active && <button className="workspace-stop" onClick={() => void stopWork()}><CircleStop size={15} />取消</button>}</footer>
        </div>
        {clarifications.length > 0 && <section className="workspace-clarify"><header><MessageSquareText size={17} /><div><small>需要确认</small><strong>补齐影响结论的资料范围</strong></div></header>{clarifications.map(item => <label key={item.id}><span>{item.question}</span><input value={answers[item.id] || ''} onChange={event => setAnswers(current => ({ ...current, [item.id]: event.target.value }))} placeholder="填写说明或上传相应资料" /></label>)}<button className="workspace-secondary" onClick={() => void prepareTask()} disabled={busy === 'prepare'}><RefreshCw size={14} />提交确认</button></section>}
        <section className="workspace-data"><header><div><small>资料预览</small><strong>{preview?.table.sheet || '尚未选择数据表'}</strong></div>{preview && <span>{formatCount(preview.table.rowCount)} 行 · {preview.table.fields.length} 列</span>}</header>{preview ? <><div className="workspace-fields">{preview.table.fields.map(field => <span key={field}><b>{field}</b><small>{preview.table.types[field]} · 缺失 {preview.table.missing[field] || 0}</small></span>)}</div><div className="workspace-table-scroll"><table><thead><tr>{columns.slice(0, 6).map(field => <th key={field}>{field}</th>)}</tr></thead><tbody>{preview.records.map((row, index) => <tr key={String(row.rowId || index)}>{columns.slice(0, 6).map(field => <td key={field}>{String(row[field] ?? '—')}</td>)}</tr>)}</tbody></table></div></> : <div className="workspace-empty"><FolderOpen size={20} /><span>上传资料后显示解析预览</span></div>}</section>
        {run && <section className="workspace-runtime"><header><div><small>真实执行过程</small><strong>{statusName[run.status] || run.status}</strong></div><div className="workspace-runtime-meta"><span>{run.strategy === 'graph_rsi' ? 'Graph RSI' : 'Plan + ReAct'}</span><span>{run.evolution?.planningPath === 'fast' ? 'Fast 复用' : run.evolution?.planningPath === 'fallback' ? 'Fallback' : '当前任务结构'}</span></div></header><div className="workspace-runtime-metrics"><Metric label="LLM 请求" value={formatCount(run.metrics.modelRequests)} hint="真实 provider 请求" /><Metric label="token" value={formatCount(totalTokens(run.metrics))} hint="输入 + 输出" /><Metric label="工具" value={formatCount(run.metrics.toolCalls)} hint="本次执行" /><Metric label="耗时" value={formatMs(run.metrics.durationMs)} hint={run.phase || '端到端'} /></div><GraphView run={run} />
          {replayEvents.length > 0 && <><div className="workspace-replay-controls"><button title="上一步" aria-label="上一步" disabled={selectedEventIndex <= 0} onClick={() => setSelectedEventSeq(replayEvents[selectedEventIndex - 1]?.seq ?? null)}><ChevronLeft size={15} /></button><span>步骤 {selectedEventIndex + 1} / {replayEvents.length}</span><button title="下一步" aria-label="下一步" disabled={selectedEventIndex >= replayEvents.length - 1} onClick={() => setSelectedEventSeq(replayEvents[selectedEventIndex + 1]?.seq ?? null)}><ChevronRight size={15} /></button></div><div className="workspace-events">{replayEvents.map(event => <button key={event.seq} className={`${eventChannel(event)} ${selectedEvent?.seq === event.seq ? 'selected' : ''}`} onClick={() => setSelectedEventSeq(event.seq)}><i>{eventChannel(event) === 'model' ? 'M' : eventChannel(event) === 'rsi' ? 'R' : eventChannel(event) === 'tool' ? 'T' : 'C'}</i><span><strong>{eventTitle(event)}</strong><small>{event.elapsedMs == null ? '—' : formatMs(event.elapsedMs)}</small></span>{event.type === 'observation' && event.detail?.ok === false && <em>错误</em>}</button>)}</div>{selectedEvent && <div className={`workspace-event-detail ${eventChannel(selectedEvent)}`}><header><span>{eventChannel(selectedEvent) === 'model' ? 'LLM' : eventChannel(selectedEvent) === 'rsi' ? 'RSI RUNTIME' : eventChannel(selectedEvent) === 'tool' ? 'TOOL' : 'CONTROL'}</span><strong>{eventTitle(selectedEvent)}</strong></header>{eventDetailLines(selectedEvent).length > 0 ? <ul>{eventDetailLines(selectedEvent).map((line, index) => <li key={`${selectedEvent.seq}-${index}`}>{line}</li>)}</ul> : <p>该步骤没有额外可展示字段。</p>}</div>}</>}{run.error && <p className="workspace-run-error">{run.error}</p>}</section>}
        {report && <section className="workspace-result"><header><div><FileBarChart2 size={18} /><div><small>交付成果</small><strong>{run?.evaluation.status === 'passed' ? '结构化校验通过' : '待用户复核'}</strong></div></div><div className="workspace-result-actions"><a href={`/api/workspaces/runs/${run?.id}/report`} target="_blank" rel="noreferrer">打开报告 <ArrowRight size={14} /></a><a href={`/api/workspaces/runs/${run?.id}/report/download`} download>下载报告 <ArrowDownToLine size={14} /></a></div></header><div className="workspace-result-grid"><div className="workspace-result-metrics">{Object.entries(report.metrics || {}).slice(0, 6).map(([key, value]) => <Metric key={key} label={key} value={typeof value === 'object' ? `${Object.keys(value as object).length} 项` : String(value)} />)}</div><div className="workspace-result-copy"><p>{report.summary || '报告尚未返回。'}</p><span>{report.evidenceIds?.length || 0} 条实际观察证据 · {report.selectedIds?.length || 0} 项清单</span>{report.assumptions?.length ? <small>假设：{report.assumptions.join('；')}</small> : null}</div></div>{exports.length > 0 && <div className="workspace-downloads">{exports.map(item => <a key={item.path} href={item.path}><ArrowDownToLine size={14} />下载清单 · {item.rowCount} 行</a>)}</div>}</section>}
      </section>
      <aside className="workspace-history"><header><div><small>工作记录</small><strong>{runs.length} 次</strong></div><PanelRightOpen size={16} /></header><div className="workspace-history-list">{runs.map(item => { const task = workspace.tasks.find(row => row.id === item.taskId); return <button key={item.id} className={item.id === run?.id ? 'selected' : ''} onClick={() => void openRun(item)}><span className={item.status}><i />{statusName[item.status] || item.status}</span><strong>{task?.title || item.taskId.slice(0, 8)}</strong><small>{task?.followupRunId ? '追问 · ' : ''}{formatCount(totalTokens(item.metrics))} token · {formatMs(item.metrics.durationMs)}</small></button>; })}{!runs.length && <div className="workspace-history-empty"><FileSearch size={18} /><span>开始一次工作后，完整轨迹会保存在这里。</span></div>}</div>{run && !active && <section className="workspace-followup"><small>继续追问</small><textarea value={followup} onChange={event => setFollowup(event.target.value)} placeholder="基于当前报告继续分析…" /><button onClick={() => void prepareTask(run.id)} disabled={!followup.trim() || busy === 'prepare'}><ArrowRight size={14} />准备追问</button></section>}</aside>
    </section>
  </main>;
}
