import { useEffect, useMemo, useState } from 'react';
import { Activity, ArrowRight, CheckCircle2, Circle, Database, Play, Square, Zap } from 'lucide-react';
import { api } from './api';
import { TraceGraph } from './ExecutionDemo';
import { activeRun, traceAt, traceDuration } from './executionTrace';
import type { TraceRun } from './executionTrace';
import './live-comparison.css';

type Task = { id: string; scenario: string; family: string; title: string; task: string; split: string; recordCount: number };
type CompactRun = { id: string; taskId: string; status: string; strategy: string; metrics: Record<string, number>; evolution?: Record<string, unknown> | null };
type LivePair = { index: number; taskId: string; status: string; runs: { baseline?: CompactRun; rsi?: CompactRun } };
type Session = {
  id: string; status: string; taskIds: string[]; events: { at: string; kind: string; taskId: string; arm?: string; detail?: unknown }[];
  pairs: LivePair[]; protocol: Record<string, unknown>;
  summary: { baseline: Record<string, number>; rsi: Record<string, number>; tokenSavingRate?: number | null; modelRequestSavingRate?: number | null };
};

const n = (value?: number) => new Intl.NumberFormat('zh-CN').format(Math.round(value || 0));
const seconds = (value?: number) => `${((value || 0) / 1000).toFixed(1)}s`;
const token = (metrics?: { inputTokens?: number; outputTokens?: number }) => (metrics?.inputTokens || 0) + (metrics?.outputTokens || 0);
const label: Record<string, string> = { finance: '财务运营', support: '客服运营', tickets: '技术工单' };

function LiveLane({ arm, run }: { arm: 'baseline' | 'rsi'; run: TraceRun | null }) {
  const view = run ? traceAt(run, activeRun(run) ? Math.max(run.metrics.durationMs || 0, Date.now() - Date.parse(run.startedAt || run.createdAt)) : traceDuration(run)) : null;
  const metrics = view?.metrics || run?.metrics;
  const overhead = Number((run as any)?.runtimeOverhead?.totalMs || metrics?.runtimeOverheadMs || 0);
  const latest = view?.events.at(-1);
  const structural = arm === 'rsi';
  return <article className={`live-agent-lane ${structural ? 'rsi' : 'baseline'}`}>
    <header><div><small>{arm === 'baseline' ? 'BASELINE / PLAN + REACT' : 'RSI / GRAPH EXECUTION'}</small><h2>{run ? (activeRun(run) ? '正在执行' : run.evaluation?.status === 'passed' ? '已完成' : run.status) : '等待调度'}</h2></div><span className={run?.evaluation?.status === 'passed' ? 'good' : ''}>{run?.evaluation?.status === 'passed' ? <CheckCircle2 size={15} /> : <Circle size={13} />}{run?.evaluation?.status === 'passed' ? '通过' : run ? run.phase : '—'}</span></header>
    <div className="live-agent-counts"><div><small>LLM</small><strong>{n(metrics?.modelRequests)}</strong></div><div><small>token</small><strong>{n(token(metrics))}</strong></div><div><small>工具</small><strong>{n(metrics?.toolCalls)}</strong></div><div><small>本地 overhead</small><strong>{overhead ? `${overhead.toFixed(1)}ms` : '—'}</strong></div></div>
    <p className="live-event"><span>{structural ? <Database size={14} /> : <Zap size={14} />}</span>{latest?.title || (run ? '正在等待下一事件' : '当前 session 尚未调度此 Agent')}</p>
    {structural && view?.nodes?.length ? <div className="live-dag"><TraceGraph nodes={view.nodes} states={view.states} prefix={`live-${arm}-${run?.id || 'pending'}`} /></div> : <div className="live-react-flow"><span>模型</span><ArrowRight size={15} /><span>工具</span><ArrowRight size={15} /><span>观察 / 报告</span></div>}
    <div className="live-trace">{(view?.events || []).slice(-7).reverse().map(event => <div key={event.seq} className={event.type === 'model' || event.type === 'model_start' ? 'model' : event.detail?.executor === 'graph' ? 'structured' : ''}><b>{event.type === 'model' ? 'LLM' : event.detail?.executor === 'graph' ? '结构' : '控制'}</b><span>{event.title}</span><time>{seconds(event.elapsedMs)}</time></div>)}{!view?.events?.length && <p>等待真实事件…</p>}</div>
  </article>;
}

export default function LiveComparison() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState('finance-cancelled_payments-01');
  const [steps, setSteps] = useState(2);
  const [session, setSession] = useState<Session | null>(null);
  const [runs, setRuns] = useState<Record<string, TraceRun>>({});
  const [error, setError] = useState('');
  const running = session?.status === 'queued' || session?.status === 'running';
  const activePair = useMemo(() => session?.pairs.find(pair => pair.status === 'running') || session?.pairs.filter(pair => Object.keys(pair.runs).length).at(-1), [session]);

  useEffect(() => { api<Task[]>('/api/taskbank/tasks?split=train').then(setTasks).catch(error => setError(error.message)); }, []);
  useEffect(() => {
    if (!session) return;
    let stopped = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const current = await api<Session>(`/api/live-showcase/${session.id}`);
        if (stopped) return;
        setSession(current);
        const present = current.pairs.flatMap(pair => (['baseline', 'rsi'] as const).map(arm => ({ arm, run: pair.runs[arm] })).filter((entry): entry is { arm: 'baseline' | 'rsi'; run: CompactRun } => !!entry.run));
        const details = await Promise.all(present.map(async entry => [`${entry.arm}:${entry.run.id}`, await api<TraceRun>(`/api/live-showcase/${current.id}/runs/${entry.arm}/${entry.run.id}`)] as const));
        if (!stopped) setRuns(Object.fromEntries(details));
        if (current.status === 'queued' || current.status === 'running') timer = window.setTimeout(poll, 600);
      } catch (failure) {
        if (!stopped) setError((failure as Error).message);
      }
    };
    void poll();
    return () => { stopped = true; if (timer) window.clearTimeout(timer); };
  }, [session?.id]);

  const selected = tasks.find(task => task.id === taskId);
  const currentBaseline = activePair?.runs.baseline ? runs[`baseline:${activePair.runs.baseline.id}`] || null : null;
  const currentRsi = activePair?.runs.rsi ? runs[`rsi:${activePair.runs.rsi.id}`] || null : null;
  const canStart = !!selected && !running;

  async function start() {
    if (!canStart) return;
    setError(''); setRuns({}); setSession(null);
    try {
      const created = await api<{ id: string }>('/api/live-showcase', { method: 'POST', body: JSON.stringify({ taskId, steps }) });
      setSession({ id: created.id, status: 'queued', taskIds: [], events: [], pairs: [], protocol: {}, summary: { baseline: {}, rsi: {} } });
    } catch (failure) { setError((failure as Error).message); }
  }
  async function cancel() { if (session) await api(`/api/live-showcase/${session.id}/cancel`, { method: 'POST', body: '{}' }); }

  return <main className="showcase-page live-comparison-page">
    <section className="live-hero"><div><p className="showcase-kicker">ONLINE COMPARISON / REAL MODEL REQUESTS</p><h1>现场跑一次，而不是只回放。</h1><p>同族 train 任务、空的独立 RSI 经验、严格 1 / 1 / 1。结果仅用于录制演示，不并入已冻结的 36-task 主结论。</p></div><div className="live-hero-status"><Activity size={17} /><strong>{running ? 'LIVE' : session?.status === 'completed' ? 'SAVED' : 'READY'}</strong><span>{session ? `会话 ${session.id.slice(0, 8)}` : '等待一条真实任务'}</span></div></section>
    <section className="live-controls"><label>领域<select disabled={running} value={selected?.scenario || 'finance'} onChange={event => { const next = tasks.find(task => task.scenario === event.target.value); if (next) setTaskId(next.id); }}>{['finance', 'support', 'tickets'].map(key => <option key={key} value={key}>{label[key]}</option>)}</select></label><label>训练任务<select disabled={running} value={taskId} onChange={event => setTaskId(event.target.value)}>{tasks.filter(task => task.scenario === selected?.scenario).map(task => <option key={task.id} value={task.id}>{task.id} · {task.recordCount} 条记录</option>)}</select></label><label>在线序列<select disabled={running} value={steps} onChange={event => setSteps(Number(event.target.value))}><option value={2}>同族两任务：形成 → 复用</option><option value={1}>单任务：冷启动对照</option></select></label><button className="live-start" disabled={!canStart} onClick={() => void start()}><Play size={15} />开始真实运行</button>{running && <button className="live-stop" onClick={() => void cancel()}><Square size={14} />停止</button>}</section>
    {error && <p className="showcase-error">{error}</p>}
    <section className="live-protocol"><span>Baseline 无跨任务学习</span><i /> <span>RSI 从空经验开始</span><i /> <span>模型 / 读取 / Agent 均为 1</span><i /> <span>Judge 不运行</span></section>
    <section className="live-session-strip"><div><small>当前任务</small><strong>{activePair?.taskId || session?.taskIds?.join(' → ') || '—'}</strong></div><div><small>顺序</small><strong>Baseline → RSI</strong></div><div><small>RSI 图</small><strong>{currentRsi?.evolution?.usedVersionId ? 'Fast 复用' : currentRsi ? '冷启动 / Fallback' : '等待'}</strong></div><div><small>累计 token 差</small><strong>{session?.summary.tokenSavingRate == null ? '—' : `${(session.summary.tokenSavingRate * 100).toFixed(1)}%`}</strong></div></section>
    <section className="live-agent-grid"><LiveLane arm="baseline" run={currentBaseline} /><LiveLane arm="rsi" run={currentRsi} /></section>
    <section className="live-ledger"><div><p className="showcase-kicker">RUNTIME OVERHEAD / SEPARATE LEDGER</p><h2>本地编排开销单列，不挤进 token。</h2><p>图查找、冷启动编译、确定性绑定、维护和持久化均为 0 LLM token；它们仍属于端到端 wall time，因此保留在独立账本。</p></div><div className="live-ledger-numbers"><span><small>Baseline 本地账本</small><b>{(session?.summary.baseline.runtimeOverheadMs || 0).toFixed(1)}ms</b></span><span><small>RSI 本地账本</small><b>{(session?.summary.rsi.runtimeOverheadMs || 0).toFixed(1)}ms</b></span><span><small>RSI 模型请求</small><b>{n(session?.summary.rsi.modelRequests)}</b></span></div></section>
    <section className="live-events"><p className="showcase-kicker">SESSION LOG</p>{session?.events?.length ? session.events.map((event, index) => <div key={`${event.at}-${index}`}><time>{new Date(event.at).toLocaleTimeString('zh-CN')}</time><b>{event.taskId}</b><span>{event.arm ? `${event.arm} · ` : ''}{typeof event.detail === 'string' ? event.detail : JSON.stringify(event.detail)}</span></div>) : <p>启动后，模型请求、图绑定、工具调用和最终报告会实时写入这里。</p>}</section>
  </main>;
}
