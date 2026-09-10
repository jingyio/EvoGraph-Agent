import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownToLine, ArrowRight, ArrowUpRight, BookOpen, Check, CheckCircle2, ChevronDown, ChevronRight, CircleDollarSign, Clock3, Database, FileText, Headphones, Layers3, LoaderCircle, Pause, Play, PlugZap, RefreshCw, Settings2, ShieldCheck, Sparkles, Terminal, TriangleAlert, Wrench, X } from 'lucide-react';
import GraphPanel from './GraphPanel';
import EvolutionPanel from './OnlineEvolutionPanel';
import NegativeMotifPanel from './NegativeMotifPanel';
import ReliabilityPanel from './ReliabilityPanel';
import TaskBankPanel from './TaskBankPanel';
import { api } from './api';
import { PRESETS, type TaskGraph, type EvaluationProfile, type AgentStrategy, type SnapshotVariant, type AgentRun, type DataSource, type PublicConfig, type RunMode, type Scenario, type ToolCard, type World } from '../shared/types';

const currency = (cents: number) => `¥${(cents / 100).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`;
const names = { finance: '财务运营', support: '客服运营' };
const statusNames = { running: '执行中', completed: '执行结束', failed: '执行失败', cancelled: '已取消', limited: '达到执行上限' };
type History = Pick<AgentRun, 'id' | 'request' | 'status' | 'startedAt' | 'metrics'>;
type ConnectionResult = { platform: string; status: string; message: string; latencyMs?: number };

export default function App() {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [snapshot, setSnapshot] = useState<World | null>(null);
  const [scenario, setScenario] = useState<Scenario>('finance');
  const [mode, setMode] = useState<RunMode>('fixture');
  const [strategy, setStrategy] = useState<AgentStrategy>('react');
  const [negativeMotifs, setNegativeMotifs] = useState(false);
  const [variant, setVariant] = useState<SnapshotVariant>('base');
  const [evaluationProfile, setEvaluationProfile] = useState<EvaluationProfile>('auto');
  const [graphs, setGraphs] = useState<TaskGraph[]>([]);
  const [source, setSource] = useState<DataSource>('sandbox');
  const [task, setTask] = useState(PRESETS.finance);
  const [page, setPage] = useState<'workbench' | 'tools' | 'platforms' | 'graphs' | 'evolution' | 'negative' | 'reliability' | 'taskbank'>(window.location.hash === '#taskbank' ? 'taskbank' : window.location.hash === '#reliability' ? 'reliability' : window.location.hash === '#negative' ? 'negative' : window.location.hash === '#evolution' ? 'evolution' : 'workbench');
  const [tab, setTab] = useState<'overview' | 'trace' | 'report'>('overview');
  const [run, setRun] = useState<AgentRun | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [tools, setTools] = useState<ToolCard[]>([]);
  const [history, setHistory] = useState<History[]>([]);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [checking, setChecking] = useState(false);
  const [taskCollapsed, setTaskCollapsed] = useState(false);
  const [connections, setConnections] = useState<ConnectionResult[]>([]);
  const pollGeneration = useRef(0);
  const busy = submitting || run?.status === 'running';

  useEffect(() => {
    Promise.all([api<PublicConfig>('/api/config'), api<World>('/api/snapshot'), api<History[]>('/api/runs')])
      .then(([nextConfig, nextSnapshot, nextHistory]) => { setConfig(nextConfig); setSnapshot(nextSnapshot); setHistory(nextHistory); })
      .catch(error => setError(String(error.message)));
  }, []);
  useEffect(() => {
    let cancelled = false;
    api<ToolCard[]>(`/api/tools?scenario=${scenario}&source=${source}`).then(items => { if (!cancelled) setTools(items); }).catch(error => { if (!cancelled) setError(error.message); });
    return () => { cancelled = true; };
  }, [scenario, source]);
  useEffect(() => {
    let cancelled = false;
    api<World>('/api/snapshot?variant=' + variant).then(value => { if (!cancelled) setSnapshot(value); }).catch(error => setError(error.message));
    return () => { cancelled = true; };
  }, [variant]);
  useEffect(() => {
    let cancelled = false;
    api<TaskGraph[]>(`/api/graphs?scenario=${scenario}&source=${source}`).then(value => { if (!cancelled) setGraphs(value); }).catch(error => setError(error.message));
    return () => { cancelled = true; };
  }, [scenario, source, run?.status, run?.graph?.learnedGraphId]);
  useEffect(() => {
    if (!runId) return;
    const generation = ++pollGeneration.current;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<AgentRun>(`/api/runs/${runId}`);
        if (pollGeneration.current !== generation) return;
        setRun(next);
        if (next.status === 'running') timer = setTimeout(poll, 500);
        else { setTaskCollapsed(Boolean(next.report)); setHistory(await api<History[]>('/api/runs')); }
      } catch (error) { if (pollGeneration.current === generation) setError((error as Error).message); }
    };
    void poll();
    return () => { pollGeneration.current++; clearTimeout(timer); };
  }, [runId]);

  function changeScenario(next: Scenario) {
    setScenario(next); setTask(PRESETS[next]); setRun(null); setRunId(null); setSource('sandbox'); setPage('workbench'); setTab('overview'); setError(''); setTaskCollapsed(false); setVariant('base'); setEvaluationProfile('auto');
  }
  function changeMode(next: RunMode) { setMode(next); setRun(null); setRunId(null); setTaskCollapsed(false); if (next === 'fixture') { setStrategy('react'); setVariant('base'); setEvaluationProfile('auto'); setTask(PRESETS[scenario]); setSource('sandbox'); } }
  async function start() {
    setError(''); setSubmitting(true); setRun(null); setRunId(null); setTaskCollapsed(false);
    try {
      const result = await api<{ id: string }>('/api/runs', { method: 'POST', body: JSON.stringify({ scenario, mode, source, task, strategy, snapshot: variant, evaluationProfile, negativeMotifs: negativeMotifs && mode === 'live' && source === 'sandbox' && scenario === 'finance' }) });
      setRunId(result.id); setPage('workbench'); setTab('trace');
    } catch (error) { setError((error as Error).message); }
    finally { setSubmitting(false); }
  }
  async function loadHistory(item: History) {
    setNegativeMotifs(Boolean(item.request.negativeMotifs));
    setEvaluationProfile(item.request.evaluationProfile || 'auto'); setStrategy(item.request.strategy || 'react'); setVariant(item.request.snapshot || 'base'); setScenario(item.request.scenario); setMode(item.request.mode); setSource(item.request.source); setTask(item.request.task); setRun(null); setRunId(item.id); setPage('workbench'); setTab('report'); setError('');
  }
  async function checkConnections() {
    setChecking(true); setError('');
    try { setConnections(await api<ConnectionResult[]>('/api/platforms/check', { method: 'POST', body: '{}' })); }
    catch (error) { setError((error as Error).message); }
    finally { setChecking(false); }
  }

  async function learnCurrent() {
    if (!run) return; setError('');
    try { await api(`/api/runs/${run.id}/learn`, { method: 'POST', body: '{}' }); setGraphs(await api<TaskGraph[]>(`/api/graphs?scenario=${scenario}&source=${source}`)); } catch (error) { setError((error as Error).message); }
  }
  function useGraph(graph: TaskGraph) {
    setEvaluationProfile('auto'); setScenario(graph.scenario); setSource(graph.source); setTask(graph.task); setMode('live'); setStrategy('graph'); setRun(null); setRunId(null); setTaskCollapsed(false); setPage('workbench'); setTab('trace');
    if (graph.source !== 'sandbox') setVariant('base');
  }
  const world = run?.state || snapshot;
  const synthetic = source === 'sandbox';
  const active = world?.tickets.filter(item => item.status !== 'closed') || [];
  const total = world?.invoices.reduce((sum, item) => sum + item.amountCents, 0) || 0;
  const matched = world?.allocations.reduce((sum, item) => sum + item.amountCents, 0) || 0;
  const overdue = active.filter(item => Date.parse(item.dueAt) < Date.parse(world?.asOf || '')).length;
  const stats = scenario === 'finance' ? [
    { label: '应收原始金额', value: currency(total), note: `${world?.invoices.length || 0} 张应收发票`, icon: CircleDollarSign },
    { label: '已分配回款', value: currency(matched), note: '沙箱匹配 · 不代表新增回款', icon: CheckCircle2 },
    { label: '剩余应收', value: currency(total - matched), note: '包含部分回款与待核查项目', icon: Clock3 },
    { label: '已登记异常', value: String(world?.cases.length || 0).padStart(2, '0'), note: '基于实际保存的核查事项', icon: TriangleAlert },
  ] : [
    { label: '未关闭工单', value: String(active.length).padStart(2, '0'), note: '当前业务快照', icon: Headphones },
    { label: '已分派工单', value: String(active.filter(item => item.ownerId).length).padStart(2, '0'), note: '技能与容量校验', icon: CheckCircle2 },
    { label: 'SLA 已超时', value: String(overdue).padStart(2, '0'), note: '分派后仍然计为超时', icon: Clock3 },
    { label: '回复草稿', value: String(world?.drafts.length || 0).padStart(2, '0'), note: '保存至沙箱 · 未发送', icon: FileText },
  ];
  const actionEvents = run?.events.filter(event => event.type === 'action') || [];
  const observationEvents = run?.events.filter(event => event.type === 'observation') || [];

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="数字员工实验台首页"><span className="brand-icon"><Layers3 size={22} /></span><span>数字员工<span className="brand-sub">OPERATIONS LAB</span></span></a>
      <div className="workspace-label">工作空间 <span>BASELINE / 01</span></div>
      <div className="nav-label">业务场景</div>
      <button className={`nav-item ${page === 'workbench' && scenario === 'finance' ? 'active' : ''}`} disabled={busy} onClick={() => changeScenario('finance')}><CircleDollarSign size={19} />财务运营<ChevronRight size={15} /></button>
      <button className={`nav-item ${page === 'workbench' && scenario === 'support' ? 'active' : ''}`} disabled={busy} onClick={() => changeScenario('support')}><Headphones size={19} />客服运营<ChevronRight size={15} /></button>
      <div className="nav-label second">实验管理</div>
      <button className={`nav-item ${page === 'taskbank' ? 'active' : ''}`} onClick={() => setPage('taskbank')}><Database size={18} />真实数据任务库</button>
      <button className={`nav-item ${page === 'reliability' ? 'active' : ''}`} onClick={() => setPage('reliability')}><Activity size={18} />长程稳定性对照</button>
      <button className={`nav-item ${page === 'negative' ? 'active' : ''}`} onClick={() => setPage('negative')}><TriangleAlert size={18} />负 Motif · 失败反思</button>
      <button className={`nav-item ${page === 'evolution' ? 'active' : ''}`} onClick={() => setPage('evolution')}><RefreshCw size={18} />递归进化实验</button>
      <button className={`nav-item ${page === 'tools' ? 'active' : ''}`} onClick={() => setPage('tools')}><Wrench size={18} />工具目录<span className="nav-count">{tools.length}</span></button>
      <button className={`nav-item ${page === 'platforms' ? 'active' : ''}`} onClick={() => setPage('platforms')}><PlugZap size={18} />平台连接</button>
      <button className={`nav-item ${page === 'graphs' ? 'active' : ''}`} onClick={() => setPage('graphs')}><Layers3 size={18} />任务图经验库<span className="nav-count">{graphs.length}</span></button>
      <div className="nav-label second">最近运行 <span>{history.length}</span></div>
      <div className="history">
        {!history.length && <p>完成任务后，执行记录会保存在这里。</p>}
        {history.slice(0, 5).map(item => <button key={item.id} disabled={busy} onClick={() => void loadHistory(item)} className={runId === item.id ? 'selected' : ''}><span className={`dot ${item.status === 'completed' ? 'green' : 'amber'}`} /><span>{names[item.request.scenario]}<small>{new Date(item.startedAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })} · {item.request.mode === 'fixture' ? '离线示例' : item.request.strategy === 'graph' ? 'Graph RSI' : 'ReAct'}</small></span></button>)}
      </div>
      <div className="sidebar-bottom"><div className="small-logo">R</div><div>{config?.backend === 'python' ? 'Python 执行器' : 'ReAct 执行器'}<small>选择工具 → 观察 → 继续执行</small></div><span className="dot green" /></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div><span>工作空间</span><ChevronRight size={14} />{page === 'tools' ? '工具目录' : page === 'platforms' ? '平台连接' : page === 'graphs' ? '任务图经验库' : names[scenario]}</div><div className="topbar-right"><span className="environment"><span className="dot green" />本地实验环境</span><span className="avatar">OP</span></div></header>
      <main>
        {page === 'taskbank' && <TaskBankPanel />}
        {page === 'reliability' && <ReliabilityPanel />}
        {page === 'negative' && <NegativeMotifPanel run={run} />}
        {page === 'evolution' && <EvolutionPanel />}
        {error && <div className="error-banner" role="alert"><TriangleAlert size={18} /><span>{error}</span><button onClick={() => setError('')} aria-label="关闭错误提示"><X size={16} /></button></div>}
        {page === 'workbench' && <>
          <div className="page-heading"><div><div className="eyebrow">DIGITAL WORKFORCE / {scenario === 'finance' ? 'FINANCE' : 'CUSTOMER SERVICE'}</div><h1>{names[scenario]}工作台<span className="version">Python · RSI v0.3</span></h1><p>{scenario === 'finance' ? '从回款核对到异常处理，每一步都有业务依据。' : '从工单巡检到回复准备，让每一项服务动作可追溯。'}</p></div><div className="snapshot-pill"><Database size={15} />{synthetic ? `合成业务快照 · ${variant === 'base' ? '原始' : variant === 'changed' ? '新周次' : '例外'}` : `${source} · 实例只读数据`}</div></div>
          <div className="stats-grid">{stats.map((stat, index) => <div className={`stat-card stat-${index}`} key={stat.label}><div className="stat-label">{stat.label}<stat.icon size={18} /></div><strong>{synthetic ? stat.value : '—'}</strong><small>{synthetic ? stat.note : '平台结果见工具观察与报告'}</small></div>)}</div>
          <section className={`task-card ${taskCollapsed ? 'collapsed' : ''}`}>
            <div className="task-top"><div className="section-title"><span className="icon-tile"><Sparkles size={19} /></span><div><h2>{taskCollapsed ? '本次任务已生成简报' : '交给数字员工'}</h2><p>{mode === 'fixture' ? '固定流程验证工具闭环；本模式不调用 LLM。' : '模型根据任务与工具观察，逐步决定下一项操作。'}</p></div></div><div className="task-top-controls">{run?.report && !busy && <button className="text-button" onClick={() => setTaskCollapsed(!taskCollapsed)}>{taskCollapsed ? '展开任务' : '收起任务'}<ChevronDown size={14} /></button>}{taskCollapsed && <button className="button secondary" disabled={busy} onClick={() => void start()}><RefreshCw size={14} />再次运行</button>}<div className="segmented"><button className={mode === 'fixture' ? 'selected' : ''} disabled={busy} onClick={() => changeMode('fixture')}>离线流程示例</button><button className={mode === 'live' && strategy === 'react' ? 'selected' : ''} disabled={busy} onClick={() => { changeMode('live'); setStrategy('react'); }}>真实模型 ReAct</button><button className={mode === 'live' && strategy === 'graph' ? 'selected' : ''} disabled={busy} onClick={() => { changeMode('live'); setStrategy('graph'); }}>Graph RSI</button></div></div></div>
            <textarea aria-label="任务说明" value={task} readOnly={mode === 'fixture'} disabled={busy} onChange={event => setTask(event.target.value)} />
            {mode === 'live' && source === 'sandbox' && scenario === 'finance' && <label style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0' }}><input type="checkbox" disabled={busy} checked={negativeMotifs} onChange={e => setNegativeMotifs(e.target.checked)} />启用已验证负 motif（可独立消融）</label>}
            <div className="task-bottom"><div className="task-options"><label><Database size={14} /><select aria-label="业务数据源" value={source} disabled={busy || mode === 'fixture'} onChange={event => { setSource(event.target.value as DataSource); setVariant('base'); setRun(null); setRunId(null); setTask(scenario === 'finance' ? '分页核查可见的应收发票和客户收款，读取必要详情，识别有依据的待核查事项并输出只读运营简报。不要修改账务。' : '读取可见工单及状态和优先级字典，核查工单详情和往来内容，识别服务风险并输出有依据的只读简报。不要发送消息或修改工单。'); }}><option value="sandbox">独立业务沙箱</option><option value={scenario === 'finance' ? 'erpnext' : 'zammad'} disabled={!config?.connectors[scenario === 'finance' ? 'erpnext' : 'zammad']}>{scenario === 'finance' ? 'ERPNext' : 'Zammad'} · 只读</option></select></label>{mode === 'live' && source === 'sandbox' && <select aria-label="业务快照" disabled={busy} value={variant} onChange={event => { setVariant(event.target.value as SnapshotVariant); setRun(null); setRunId(null); }}><option value="base">原始快照</option><option value="changed">新周次 · 新 ID 与金额</option><option value="exception">例外 · 请假与归属冲突</option></select>}{mode === 'live' && source === 'sandbox' && <select aria-label="结果校验目标" disabled={busy} value={evaluationProfile} onChange={event => setEvaluationProfile(event.target.value as EvaluationProfile)}><option value="auto">自动选择校验目标</option><option value="invariants">仅检查状态约束</option><option value={scenario + '_full'}>岗位完整流程</option></select>}<span className="tool-count"><Wrench size={14} />{tools.length} 个工具</span><span className={`mode-note ${mode === 'fixture' ? 'amber-text' : ''}`}>{mode === 'fixture' ? '固定预设 · 无模型指标' : config?.modelConfigured ? config.model : '尚未配置模型'}</span></div>
              {busy ? <button className="button secondary" onClick={() => runId && void api(`/api/runs/${runId}/cancel`, { method: 'POST', body: '{}' }).catch(error => setError(error.message))}><Pause size={16} />停止执行</button> : <button className="button primary" disabled={!config || !task.trim() || (mode === 'live' && !config.modelConfigured)} onClick={() => void start()}><Play size={16} fill="currentColor" />{mode === 'fixture' ? '运行流程示例' : '开始执行'}<ArrowRight size={17} /></button>}
            </div>
            {mode === 'live' && !config?.modelConfigured && <div className="config-note">在项目 .env 中填写 LLM_API_KEY、LLM_MODEL 和服务地址后重启，即可执行自定义任务。密钥只保存在服务端。</div>}
          </section>
          {run?.evaluation && <section className={`evaluation-card ${run.evaluation.status}`}><div><ShieldCheck size={18} /><strong>{run.evaluation.status === 'failed' ? '任务结果存在缺项' : run.evaluation.status === 'not_evaluated' ? '结果需要独立评估' : '业务状态校验通过'}</strong><span>{run.evaluation.scope}</span></div><p>{run.evaluation.note}</p>{run.evaluation.issues.length > 0 && <ul>{run.evaluation.issues.map((issue, index) => <li key={index}>{issue.entityId}：{issue.message}</li>)}</ul>}</section>}
          <div className="content-toolbar"><div className="tabs"><button className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}><Database size={16} />业务数据</button><button className={tab === 'trace' ? 'active' : ''} onClick={() => setTab('trace')}><Activity size={16} />执行轨迹{run && <span>{actionEvents.length}</span>}</button><button className={tab === 'report' ? 'active' : ''} onClick={() => setTab('report')}><FileText size={16} />运营简报{run?.report && <span className="ready-dot" />}</button></div><div className="run-state">{run ? <><span className={`dot ${run.status === 'completed' ? 'green' : 'amber'}`} />{statusNames[run.status]}<code>{run.id.slice(0, 8)}</code></> : '每次运行均从原始快照开始'}</div></div>
          <div className="workspace-grid"><div className="main-panel">
            {tab === 'overview' && <section className="panel"><div className="panel-heading"><h2>{scenario === 'finance' ? '应收账款明细' : '服务工单队列'}</h2><span>{synthetic ? `${scenario === 'finance' ? world?.invoices.length || 0 : active.length} 条记录` : '外部只读模式'}</span></div>{!synthetic ? <Empty icon={Database} title="平台原始数据保留在执行观察中" description="运行任务后，可在执行轨迹查看真实 API 字段与分页信息，并在运营简报查看引用的资源。" /> : world && <BusinessTable world={world} scenario={scenario} />}
              {synthetic && <div className="table-foot"><ShieldCheck size={14} />{scenario === 'finance' ? '金额使用整数分计算；重复流水不会自动分配。' : '分派检查坐席技能与容量；回复仅保存为草稿。'}</div>}
            </section>}
            {tab === 'trace' && <section className="panel trace-panel"><div className="panel-heading"><h2>执行轨迹<span className="subtle-tag">ACTION / OBSERVATION</span></h2>{run && <a href={`/api/runs/${run.id}/export/json`} className="text-button"><ArrowDownToLine size={14} />原始记录</a>}</div>{!run ? <Empty icon={Activity} title="等待第一次执行" description="运行任务后，这里会记录每次工具调用、实际返回结果以及模型计量。" /> : <div className="timeline">{run.events.filter(event => event.type !== 'model').map(event => <div className={`timeline-event event-${event.type}`} key={event.seq}><span className="timeline-symbol">{event.type === 'action' ? <Wrench size={13} /> : event.type === 'observation' ? <Check size={13} /> : event.type === 'error' ? <X size={13} /> : <Play size={12} />}</span><div className="timeline-body"><div className="event-title"><strong>{event.title}</strong><small>{event.durationMs !== undefined ? `${event.durationMs} ms` : new Date(event.at).toLocaleTimeString('zh-CN', { hour12: false })}</small></div>{event.detail !== undefined && <details><summary>{event.type === 'action' ? '查看调用参数' : event.type === 'observation' ? '查看工具返回' : '查看详情'}<ChevronDown size={12} /></summary><pre>{JSON.stringify(event.detail, null, 2)}</pre></details>}</div></div>)}</div>}</section>}
            {tab === 'report' && <section className="panel report-panel"><div className="panel-heading"><h2>运营简报</h2>{run?.report && <a href={`/api/runs/${run.id}/export/md`} className="text-button"><ArrowDownToLine size={14} />导出 Markdown</a>}</div>{run?.report ? <div className="report-content"><div className="report-kicker">OPERATIONS BRIEF / {run.request.mode === 'fixture' ? '离线流程示例' : '真实模型执行'}</div><h2>{run.report.title}</h2><p className="report-summary">{run.report.summary}</p><div className="report-metrics">{run.report.metrics.map(item => <div key={item.label}><span>{item.label}</span><strong>{item.value}</strong></div>)}</div><div className="table-scroll"><table><thead><tr>{run.report.columns.map(item => <th key={item}>{item}</th>)}</tr></thead><tbody>{run.report.rows.map((row, index) => <tr key={index}>{row.map((item, cell) => <td key={cell}>{item}</td>)}</tr>)}</tbody></table></div><h3>核查结论与待办</h3><ul className="findings">{run.report.findings.map((item, index) => <li key={index}>{item}</li>)}</ul>{run.finalText && <div className="final-text"><CheckCircle2 size={18} /><p>{run.finalText}</p></div>}</div> : <Empty icon={FileText} title="让结果成为一份可交付的简报" description={run?.finalText || '执行完成并调用报告工具后，这里将呈现基于实际业务状态的结果。'} />}</section>}
          </div><aside className="inspector"><section className="panel"><div className="panel-heading"><h2>执行计量</h2><Activity size={16} /></div><div className="runtime-mode"><span className={`dot ${mode === 'live' ? 'green' : 'amber'}`} />{run ? run.request.mode === 'fixture' ? '离线固定流程 · 非 LLM' : run.model : mode === 'fixture' ? '离线固定流程 · 非 LLM' : config?.model || '等待模型配置'}</div><div className="metric-list"><div><span>LLM 请求</span><strong>{run?.metrics.modelRequests ?? '—'}<small>次</small></strong></div><div><span>工具调用</span><strong>{run?.metrics.toolCalls ?? '—'}<small>次</small></strong></div><div><span>输入 / 输出 token</span><strong className="tokens">{run ? `${run.metrics.inputTokens ?? '未知'} / ${run.metrics.outputTokens ?? '未知'}` : '—'}</strong></div><div><span>执行耗时</span><strong>{run ? (run.metrics.durationMs / 1000).toFixed(2) : '—'}<small>s</small></strong></div></div><div className="meter-caption">{run?.modelSettings?.enableThinking === false && <div>思考模式已请求关闭 · reasoning token {run.metrics.reasoningTokens ?? '未提供'}</div>}{run?.modelSettings?.parallelToolCalls && <div>独立工具批量调用已开启</div>}{mode === 'fixture' ? '离线示例用于验证流程和界面，耗时不能用于比较模型性能。' : run && !run.metrics.usageComplete ? '部分请求未返回 token 用量；当前 token 统计不完整。' : '记录真实请求与供应商返回用量，不预填成本收益。'}</div></section>
            <section className="panel"><div className="panel-heading"><h2>{scenario === 'finance' ? '匹配进度' : '分派进度'}</h2><ArrowUpRight size={16} /></div><div className="progress-block"><div className="progress-number">{synthetic ? scenario === 'finance' ? `${total ? Math.round(matched / total * 100) : 0}%` : `${active.filter(item => item.ownerId).length} / ${active.length}` : '—'}<small>{scenario === 'finance' ? '应收金额已匹配' : '未关闭工单已分派'}</small></div><div className="progress-track"><span style={{ width: `${!synthetic ? 0 : scenario === 'finance' ? total ? matched / total * 100 : 0 : active.length ? active.filter(item => item.ownerId).length / active.length * 100 : 0}%` }} /></div><p>{scenario === 'finance' ? '匹配进度来自已保存的分配记录。' : '分派完成度不等于问题解决率。'}</p></div></section>
            <section className="context-card"><div><BookOpen size={17} /><h3>经验复用</h3></div><p>{run?.graph ? `${run.graph.status === 'hit' ? '命中历史图' : run.graph.status === 'fallback' ? '图执行回退模型' : '冷启动 ReAct'} · ${run.graph.completedNodes} 个节点完成，${run.graph.toolCalls} 次工具调用由图执行。规划调用 ${run.graph.plannerRequests || 0} 次，已计入 LLM 总数。` : 'Graph RSI 从真实轨迹学习读取图；相似任务由经验规划器选择节点，写入和报告继续由模型执行。'}</p>{run?.graph?.reason && <p>{run.graph.reason}</p>}{run?.graph?.learning && <p>学习成本另列：{run.graph.learning.toolCalls} 次读取，{run.graph.learning.compileMs + run.graph.learning.durationMs} ms，无额外 LLM。</p>}{run?.graph?.learningError && <p>学习未通过：{run.graph.learningError}</p>}<button className="text-button" onClick={() => setPage('graphs')}>查看任务图与来源<ArrowRight size={13} /></button></section>
          </aside></div>
          {run?.error && <div className="error-banner"><TriangleAlert size={18} /><span>{run.error}</span></div>}
          {tab === 'overview' && synthetic && world && <div className="detail-grid"><section className="panel"><div className="panel-heading"><h2>{scenario === 'finance' ? '待核查事项' : '回复草稿'}</h2><span>{scenario === 'finance' ? world.cases.length : world.drafts.length} 项</span></div><div className="detail-list">{scenario === 'finance' ? world.cases.length ? world.cases.map(item => <div className="detail-item" key={item.id}><span className="detail-icon amber-text"><TriangleAlert size={17} /></span><div><strong>{item.id} · {item.kind === 'duplicate' ? '疑似重复流水' : item.kind === 'unmatched' ? '回款用途待确认' : '逾期应收'}</strong><p>{item.summary}</p><code>{item.evidenceIds.join(' · ')}</code></div></div>) : <p className="muted empty-inline">尚未登记事项。运行任务后，这里会出现有记录依据的异常。</p> : world.drafts.length ? world.drafts.map(item => <details className="draft-item" key={item.ticketId}><summary><span>{item.ticketId}<small>内部草稿 · 未发送</small></span><ChevronDown size={14} /></summary><p>{item.body}</p><code>知识来源：{item.articleIds.join(', ')}</code></details>) : <p className="muted empty-inline">尚未生成草稿。回复将关联知识库来源并保留待审核。</p>}</div></section><section className="panel"><div className="panel-heading"><h2>{scenario === 'finance' ? '回款记录' : '坐席容量'}</h2><span>当前快照</span></div>{scenario === 'finance' ? <div className="payments-list">{world.payments.map(item => <div key={item.id}><span><strong>{item.id}</strong><small>{item.bankRef}</small></span><span>{currency(item.amountCents)}<small>{world.payments.filter(peer => peer.bankRef === item.bankRef).length > 1 ? '重复流水引用 · 待核查' : item.invoiceRefs.join(' / ') || '无发票引用'}</small></span></div>)}</div> : <div className="capacity-list">{world.agents.map(agent => { const count = active.filter(item => item.ownerId === agent.id).length; return <div key={agent.id}><div><strong>{agent.name}<small>{agent.available ? '可用' : '休假'}</small></strong><span>{count} / {agent.capacity}</span></div><div className={`progress-track ${agent.available ? '' : 'unavailable'}`}><span style={{ width: `${count / agent.capacity * 100}%` }} /></div></div>; })}</div>}</section></div>}
        </>}
        {page === 'graphs' && <GraphPanel graphs={graphs} run={run} busy={Boolean(busy)} onLearn={learnCurrent} onUse={useGraph} />}
        {page === 'tools' && <><div className="page-heading"><div><div className="eyebrow">CAPABILITIES / TOOL REGISTRY</div><h1>工具目录</h1><p>{names[scenario]} · {source === 'sandbox' ? '独立业务沙箱' : source} · 参数校验后执行</p></div><span className="snapshot-pill"><Wrench size={15} />{tools.length} 个可用工具</span></div><div className="tool-grid">{tools.map(tool => <section className="panel tool-card" key={tool.name}><div><span className="icon-tile"><Wrench size={18} /></span><span className={`effect ${tool.effect}`}>{tool.effect === 'read' ? '读取 / 计算' : tool.effect === 'artifact' ? '成品输出' : '沙箱写入'}</span></div><h3>{tool.name}</h3><p>{tool.description}</p>{tool.origin && <div className="autotool-origin">AutoTool · {tool.origin.spec}<small>契约 {tool.origin.digest.slice(0, 10)}</small></div>}<details><summary>参数 schema<ChevronDown size={13} /></summary><pre>{JSON.stringify(tool.parameters, null, 2)}</pre></details></section>)}</div></>}
        {page === 'platforms' && <><div className="page-heading"><div><div className="eyebrow">BUSINESS SYSTEMS / CONNECTIONS</div><h1>平台连接</h1><p>沙箱负责完整闭环，外部平台连接器提供真实数据的只读核查。</p></div><button className="button secondary" disabled={checking} onClick={() => void checkConnections()}>{checking ? <LoaderCircle size={16} className="spin" /> : <RefreshCw size={16} />}检查 API 连接</button></div><div className="platform-grid">{[{ id: 'erpnext' as const, name: 'ERPNext', role: '财务运营', icon: CircleDollarSign, description: '应收发票、客户收款、客户主数据。保留原生金额与币种语义。', url: 'https://github.com/frappe/erpnext', keys: 'ERPNEXT_BASE_URL\nERPNEXT_API_KEY\nERPNEXT_API_SECRET' }, { id: 'zammad' as const, name: 'Zammad', role: '客服运营', icon: Headphones, description: '工单、往来内容、状态与优先级字典。可见范围由 token 权限决定。', url: 'https://github.com/zammad/zammad', keys: 'ZAMMAD_BASE_URL\nZAMMAD_API_TOKEN' }].map(platform => { const result = connections.find(item => item.platform === platform.id); return <section className="panel platform-card" key={platform.id}><div className="platform-top"><span className="platform-icon"><platform.icon size={28} /></span><span className={`connection-badge ${result?.status === 'reachable' ? 'good' : ''}`}>{result?.status === 'reachable' ? 'API 可达' : config?.connectors[platform.id] ? '已配置 · 待验证' : '未配置'}</span></div><h2>{platform.name}</h2><span className="platform-role">{platform.role} / READ ONLY</span><p>{platform.description}</p><div className="env-block"><span>.env 配置项</span><pre>{platform.keys}</pre></div>{result && <div className={`connection-result ${result.status === 'failed' ? 'bad' : ''}`}>{result.message}{result.latencyMs !== undefined && ` · ${result.latencyMs} ms`}</div>}<a className="text-button" href={platform.url} target="_blank" rel="noreferrer">官方开源仓库<ArrowUpRight size={15} /></a></section>; })}</div><section className="panel platform-notes"><h2>可用性调研与接入边界</h2><p>ERPNext 提供官方 Docker 演示方案；Zammad 提供 Docker Compose 部署方案。Frappe Helpdesk 是客服侧的备选，可与 ERPNext 共用 Frappe 技术栈。当前连接器支持读取与报告，尚未接入外部账务写入、工单修改或消息发送。</p><p>完整调研、部署前置条件、已验证项目和待验证项目见项目 docs/platform-research.md。</p><div className="platform-note-footer"><ShieldCheck size={17} />业务凭据仅由服务端环境变量读取，不返回浏览器。</div></section></>}
        <footer><span>OPERATIONS LAB <i /> 基础数字员工实验台</span><span>可重置的业务状态 · 可导出的执行记录</span></footer>
      </main>
    </div>
  </div>;
}

function Empty({ icon: Icon, title, description }: { icon: typeof Activity; title: string; description: string }) {
  return <div className="empty-state"><span><Icon size={28} /></span><h3>{title}</h3><p>{description}</p></div>;
}
function BusinessTable({ world, scenario }: { world: World; scenario: Scenario }) {
  if (scenario === 'finance') return <div className="table-scroll"><table><thead><tr><th>发票 / 客户</th><th>应收金额</th><th>已分配</th><th>到期日</th><th>状态</th></tr></thead><tbody>{world.invoices.map(invoice => { const allocated = world.allocations.filter(item => item.invoiceId === invoice.id).reduce((sum, item) => sum + item.amountCents, 0); const remaining = invoice.amountCents - allocated; return <tr key={invoice.id}><td><strong>{invoice.id}</strong><small>{invoice.customer}</small></td><td className="numeric">{currency(invoice.amountCents)}</td><td className="numeric">{currency(allocated)}</td><td>{invoice.dueDate.slice(5).replace('-', '/')}</td><td><span className={`status-pill ${remaining === 0 ? 'good' : invoice.dueDate < world.asOf.slice(0, 10) ? 'warning' : ''}`}>{remaining === 0 ? '已匹配' : allocated ? '部分回款' : invoice.dueDate < world.asOf.slice(0, 10) ? '逾期待核查' : '未结清'}</span></td></tr>; })}</tbody></table></div>;
  return <div className="table-scroll"><table><thead><tr><th>工单 / 客户</th><th>问题</th><th>优先级</th><th>负责人</th><th>SLA</th></tr></thead><tbody>{world.tickets.filter(item => item.status !== 'closed').map(ticket => <tr key={ticket.id}><td><strong>{ticket.id}</strong><small>{ticket.customer}</small></td><td className="subject-cell">{ticket.subject}</td><td><span className={`priority ${ticket.priority}`}>{({ urgent: '紧急', high: '高', normal: '普通', low: '低' })[ticket.priority]}</span></td><td>{world.agents.find(agent => agent.id === ticket.ownerId)?.name || <span className="muted">待分派</span>}</td><td><span className={`status-pill ${Date.parse(ticket.dueAt) < Date.parse(world.asOf) ? 'warning' : 'good'}`}>{Date.parse(ticket.dueAt) < Date.parse(world.asOf) ? '已超时' : '时限内'}</span></td></tr>)}</tbody></table></div>;
}
