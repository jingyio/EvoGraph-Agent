import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownToLine, CheckCircle2, Circle, GitBranch, Pause, Play, RotateCcw, Square, Wrench, Zap } from 'lucide-react';
import { api } from './api';
import { activeRun, eventTime, spansAt, strategyNames, traceAt, traceDuration } from './executionTrace';
import type { GraphNode, RunSummary, Strategy, TraceEvent, TraceRun } from './executionTrace';
import './execution-demo.css';

type Task = { id: string; scenario: string; family: string; title: string; task: string; split: string; sourceUrl: string; recordCount: number };
const sources: Record<string, string> = { tickets: '技术工单 · Zammad GitHub Issues', finance: '财务运营 · Olist', support: '客服运营 · CFPB' };
const eventNames: Record<string, string> = { model_start: '请求模型', model: '模型返回', model_error: '模型请求失败', action: '调用工具', observation: '工具返回', plan: '计划', composition: '局部片段组合', graph: '图执行', graph_created: '读取图就绪', motif: '筛选后补查', inertia: 'AutoTool 惯性', evaluation: '结果校验', validation: '格式校验', fallback: '恢复执行', recovery: '补查字段', finished: '执行结束', retrieval: '工具检索' };
const stateNames: Record<string, string> = { pending: '等待依赖', running: '执行中', done: '完成', reused: '复用结果', failed: '失败', 'model-handoff': '交接模型' };
const n = (value: number) => Math.round(value).toLocaleString('zh-CN');
const seconds = (ms: number) => `${(ms / 1000).toFixed(1)}s`;
function pretty(value: unknown) { return typeof value === 'string' ? value : JSON.stringify(value, null, 2); }

export function TraceGraph({ nodes, states, prefix }: { nodes: GraphNode[]; states: Record<string, string>; prefix: string }) {
  const depths = new Map<string, number>();
  for (let i = 0; i < nodes.length; i++) for (const node of nodes) if (!depths.has(node.id) && node.dependencies.every(d => depths.has(d))) depths.set(node.id, Math.max(-1, ...node.dependencies.map(d => depths.get(d)!)) + 1);
  const positions = new Map(nodes.map(node => [node.id, { x: 12 + (depths.get(node.id) || 0) * 224, y: 12 + nodes.filter(x => depths.get(x.id) === depths.get(node.id)).findIndex(x => x.id === node.id) * 83 }]));
  const width = Math.max(430, ...[...positions.values()].map(p => p.x + 215));
  const height = Math.max(100, ...[...positions.values()].map(p => p.y + 82));
  return <svg className="demo-dag" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="当前时刻的读取依赖图">
    <defs><marker id={`demo-arrow-${prefix}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#8293a4" /></marker></defs>
    {nodes.flatMap(node => node.dependencies.map(dep => { const a = positions.get(dep), b = positions.get(node.id)!; return a ? <path key={dep + node.id} d={`M${a.x + 197} ${a.y + 32} L${b.x} ${b.y + 32}`} stroke="#8293a4" fill="none" markerEnd={`url(#demo-arrow-${prefix})`} /> : null; }))}
    {nodes.map(node => { const p = positions.get(node.id)!, state = states[node.id] || 'pending', filter = node.foreach?.filter; return <g key={node.id} transform={`translate(${p.x},${p.y})`} className={`demo-node ${state}`}><title>{node.tool} · {node.id} · {stateNames[state]}</title><rect width="197" height="66" rx="9" /><text x="10" y="22" fontSize="11">{node.tool.length > 28 ? node.tool.slice(0, 26) + '…' : node.tool}</text><text x="10" y="43" fontSize="10">{filter ? `筛选 ${filter.field}=${String(filter.value)}` : node.reuse ? `复用 ${node.reuse.fields.join(', ')}` : node.defer ? '模型接管子图' : node.id.slice(0, 26)}</text><text x="10" y="58" fontSize="9">{stateNames[state] || state}</text></g>; })}
  </svg>;
}

function TimelineEvent({ event, run, onInspect }: { event: TraceEvent; run: TraceRun; onInspect: () => void }) {
  const bad = event.type === 'model_error' || event.type === 'fallback' || event.detail?.ok === false || (event.type === 'evaluation' && event.detail?.status === 'failed');
  const graph = event.detail?.executor === 'graph' || ['graph', 'graph_created', 'motif', 'recovery'].includes(event.type);
  const inertia = event.detail?.executor === 'inertia' || event.type === 'inertia';
  let summary = event.title;
  if (event.type === 'model') summary = (typeof event.detail?.content === 'string' ? event.detail.content.trim() : '') || (Array.isArray(event.detail?.toolCalls) ? event.detail.toolCalls.map((call: any) => call.function?.name).join(' · ') : '') || event.title;
  if (event.type === 'action') summary += ' · ' + String(event.detail?.arguments || '{}');
  if (event.type === 'observation') summary += event.detail?.ok ? ` · 成功${Array.isArray(event.detail?.result?.records) ? ` · ${event.detail.result.records.length} 条记录` : ''}` : ` · ${event.detail?.error || '工具错误'}`;

  return <button className={`demo-event ${bad ? 'bad' : ''} ${graph ? 'by-graph' : ''} ${inertia ? 'by-inertia' : ''}`} onClick={onInspect} aria-label={`查看事件 ${event.seq} ${eventNames[event.type] || event.type} ${event.title}`}>
    <span className="demo-event-icon">{bad ? <Activity size={14} /> : graph ? <GitBranch size={14} /> : event.type.startsWith('model') ? <Zap size={14} /> : <Wrench size={14} />}</span>
    <span><strong>{eventNames[event.type] || event.type}<em>{inertia ? '惯性' : graph ? '图' : event.detail?.executor === 'model' ? '模型调度' : ''}</em></strong><small title={summary}>{summary}</small></span>
    <time>{seconds(eventTime(run, event))}</time>
  </button>;
}

function RunLane({ label, strategy, run, cursor, live, timelineDuration, onInspect, onStop }: { label: string; strategy: Strategy; run: TraceRun | null; cursor: number; live: boolean; timelineDuration: number; onInspect: (event: TraceEvent) => void; onStop: () => void }) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  const view = run ? traceAt(run, cursor) : null;
  useEffect(() => { if (follow && bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight; }, [view?.events.length, follow]);
  const spans = run && view ? spansAt(run, view.events) : [];
  const pending = spans.filter(s => s.end === undefined);
  const current = run?.status === 'queued' && live ? '等待调度' : view?.finished ? (view.evaluation.status === 'passed' ? '任务通过' : '未通过 / 未完成') : pending.some(s => s.kind === 'model') ? '等待模型返回' : view?.events.at(-1)?.title || '等待开始';
  const finishedGood = view?.finished && view.evaluation.status === 'passed';
  const spanWidth = Math.max(1, timelineDuration);
  return <section className={`demo-lane ${strategy === 'graph_rsi' ? 'rsi-lane' : ''}`}>
    <header><div><span className="demo-lane-label">{label}</span><h2>{strategyNames[strategy]}</h2></div><span className={`demo-status ${view?.finished ? finishedGood ? 'good' : 'bad' : ''}`}>{finishedGood ? <CheckCircle2 size={14} /> : <Circle size={12} />}{run ? current : '尚未选择记录'}</span></header>
    <p className="demo-model-name">{run ? `执行 ${run.models.executor} · Plan ${run.models.planner}` : '选择历史记录或开始真实执行'}</p>
    <div className="demo-kpis">{[['LLM 调用', view?.metrics.modelRequests], ['工具调用', view?.metrics.toolCalls], ['输入 token', view?.metrics.inputTokens], ['输出 token', view?.metrics.outputTokens]].map(([title, value]) => <div key={title}><small>{title}</small><strong>{value === undefined ? '—' : n(value as number)}</strong></div>)}</div>
    {run && view && <>
      <div className="demo-lane-meta"><span>耗时 {seconds(view.finished ? run.metrics.durationMs : Math.min(cursor, spanWidth))}</span><span>排队 {seconds(run.metrics.queueMs)}</span><span>工具错误 {view.metrics.toolErrors}</span><span>图内消除 {view.metrics.elidedToolCalls || 0}</span>{run.metrics.motifSelectedRecords != null && <span>Motif 入选/排除 {view.metrics.motifSelectedRecords}/{view.metrics.motifFilteredOutRecords || 0}</span>}{!view.metrics.usageComplete && <b>用量不完整</b>}</div>
      <div className="demo-activity" aria-label="模型与工具时间分布">
        {(['model', 'graph', 'tool'] as const).map(kind => <div key={kind}><span>{kind === 'model' ? 'LLM' : kind === 'graph' ? '图工具' : '模型工具'}</span><div>{spans.filter(s => s.kind === kind).map(s => <i key={s.key} className={`${kind} ${s.error ? 'error' : ''} ${s.end === undefined ? 'pending' : ''}`} style={{ left: `${s.start / spanWidth * 100}%`, width: `${Math.max(.4, ((s.end ?? (Number.isFinite(cursor) ? cursor : spanWidth)) - s.start) / spanWidth * 100)}%` }} title={`${s.label} · ${seconds(s.start)} → ${s.end === undefined ? '执行中' : seconds(s.end)}`} />)}</div></div>)}
      </div>
      <div className="demo-structure">{view.nodes.length ? <TraceGraph nodes={view.nodes} states={view.states} prefix={label} /> : <div className="demo-react-flow"><span>模型选择操作</span><b>→</b><span>工具执行</span><b>→</b><span>返回观察</span><small>{run.strategy === 'react' ? '下方事件记录展示每一轮实际调用' : '读取图尚未出现；先观察当前计划与模型调用'}</small></div>}</div>
      <div className="demo-trace-heading"><strong>执行轨迹 <span>{view.events.length}</span></strong><label><input type="checkbox" checked={follow} onChange={e => setFollow(e.target.checked)} />跟随最新事件</label>{live && activeRun(run) && <button className="text-button" onClick={onStop}><Square size={12} />停止此 Agent</button>}</div>
      <div className="demo-trace" ref={bodyRef} role="log" aria-label={`${strategyNames[strategy]} 执行事件`} aria-live="off">{view.events.map(e => <TimelineEvent key={e.seq} event={e} run={run} onInspect={() => onInspect(e)} />)}{!view.events.length && <p className="demo-empty">尚无事件。回放从原始执行开始时刻播放。</p>}</div>
      <details className="demo-report"><summary>报告与评分 · {view.evaluation.status === 'passed' ? '通过' : view.evaluation.status === 'failed' ? '未通过' : '尚未评分'}</summary>{view.submission ? <><p>{view.submission.summary}</p><pre>{pretty({ metrics: view.submission.metrics, selectedIds: view.submission.selectedIds, evidenceIds: view.submission.evidenceIds })}</pre></> : <p>当前时刻尚未发布报告。</p>}{view.evaluation.issues?.length ? <p className="demo-inline-error">{view.evaluation.issues.join(' · ')}</p> : null}</details>
      {view.finished && run.evolution && <p className="demo-evolution-note"><GitBranch size={13} />{run.evolution.usedVersionId ? `使用 G${run.evolution.generation} · ${run.evolution.usedVersionId.slice(0, 6)}` : '冷启动'} · 图维护 {run.evolution.maintenanceMs ?? 0} ms · {run.evolution.note}</p>}
      {view.finished && <p className="demo-evolution-note"><a href={`/api/taskbank/runs/${run.id}/report`} target="_blank" rel="noreferrer">打开业务报告与逐条证据 ↗</a></p>}
      <footer><span>记录 {run.id.slice(0, 8)}{!run.traceVersion && ' · 旧记录缺少部分起止时间'}</span><a href={`/api/taskbank/runs/${run.id}`} target="_blank" rel="noreferrer">原始 JSON <ArrowDownToLine size={12} /></a></footer>
    </>}
    {!run && <div className="demo-empty"><Activity size={30} /><p>这里将显示实际模型请求、工具执行和结果。</p></div>}
  </section>;
}

function readSelection(): { taskId: string; strategies: [Strategy, Strategy] } {
  const params = new URLSearchParams(window.location.search);
  const a = params.get('a'), b = params.get('b');
  if (params.get('taskId') && a && b && a in strategyNames && b in strategyNames) return { taskId: params.get('taskId')!, strategies: [a as Strategy, b as Strategy] };
  try { const s = JSON.parse(localStorage.getItem('rsi-demo-selection') || '{}'); if (s.taskId && s.strategies?.length === 2 && s.strategies.every((x: string) => x in strategyNames)) return s; } catch { /* Use a known public task. */ }
  return { taskId: 'tickets-unassigned-02', strategies: ['react', 'graph_rsi'] };
}

export default function ExecutionDemo() {
  const initial = useRef(readSelection());
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskId, setTaskId] = useState(initial.current.taskId);
  const [strategies, setStrategies] = useState<[Strategy, Strategy]>(initial.current.strategies);
  const [summaries, setSummaries] = useState<RunSummary[]>([]);
  const [ids, setIds] = useState<[string, string]>(['', '']);
  const [runs, setRuns] = useState<[TraceRun | null, TraceRun | null]>([null, null]);
  const [live, setLive] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [speed, setSpeed] = useState(4);
  const [now, setNow] = useState(Date.now());
  const [pending, setPending] = useState(false);
  const [focus, setFocus] = useState(false);
  const [compact, setCompact] = useState(false);
  const [error, setError] = useState('');
  const [selection, setSelection] = useState<{ lane: number; seq: number } | null>(null);
  const fetching = useRef(false);
  const task = tasks.find(t => t.id === taskId);
  const busy = pending || runs.some(activeRun);
  const duration = Math.max(1, ...runs.filter((r): r is TraceRun => !!r).map(traceDuration));
  const readyReplay = runs.some(Boolean) && !runs.some(activeRun);
  useEffect(() => { let stopped = false; api<Task[]>('/api/taskbank/tasks').then(list => { if (!stopped) setTasks(list); }).catch(e => { if (!stopped) setError(e.message); }); return () => { stopped = true; }; }, []);
  useEffect(() => { localStorage.setItem('rsi-demo-selection', JSON.stringify({ taskId, strategies })); }, [taskId, strategies]);
  useEffect(() => {
    let stopped = false;
    setRuns([null, null]); setIds(['', '']); setSelection(null); setPlaying(false); setLive(false);
    api<{ runs: RunSummary[] }>(`/api/taskbank/runs?taskId=${encodeURIComponent(taskId)}&limit=500`).then(data => {
      if (stopped) return;
      setSummaries(data.runs);
      const params = new URLSearchParams(window.location.search);
      setIds(strategies.map((s, i) => data.runs.find(r => r.strategy === s && r.id === params.get(i === 0 ? 'left' : 'right'))?.id || data.runs.find(r => r.strategy === s)?.id || '') as [string, string]);
      setPosition(Infinity);
    }).catch(e => { if (!stopped) setError(e.message); });
    return () => { stopped = true; };
  }, [taskId, strategies]);
  useEffect(() => {
    let stopped = false; let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      fetching.current = true;
      const results = await Promise.allSettled(ids.map(id => id ? api<TraceRun>(`/api/taskbank/runs/${id}`) : Promise.resolve(null)));
      if (stopped) return;
      fetching.current = false;
      setRuns(old => results.map((r, i) => r.status === 'fulfilled' ? r.value : old[i]) as typeof runs);
      const failed = results.find(r => r.status === 'rejected');
      if (failed?.status === 'rejected') setError(`读取轨迹失败：${failed.reason.message}；稍后自动重连。`);
      else setError(old => old.startsWith('读取轨迹失败：') ? '' : old);
      setNow(Date.now());
      const ongoing = results.some(r => r.status === 'fulfilled' && activeRun(r.value));
      if (ongoing) { setLive(true); setPlaying(false); }
      if (ongoing || failed) timer = setTimeout(poll, 650);
    }
    void poll(); return () => { stopped = true; fetching.current = false; clearTimeout(timer); };
  }, [ids]);
  useEffect(() => {
    if (!live && !playing) return;
    let last = Date.now();
    const timer = setInterval(() => { const current = Date.now(); setNow(current); if (playing) setPosition(p => Math.min(duration, p + (current - last) * speed)); last = current; }, 100);
    return () => clearInterval(timer);
  }, [live, playing, duration, speed]);
  useEffect(() => { if (position >= duration) setPlaying(false); }, [position, duration]);
  const cursors = runs.map(run => !run ? 0 : live ? activeRun(run) ? Math.max(run.metrics.durationMs, now - Date.parse(run.startedAt || run.createdAt) - (run.startedAt ? 0 : run.metrics.queueMs)) : traceDuration(run) : Math.min(position, duration));
  const timelineDuration = Math.max(duration, ...(live ? cursors : [0]));
  const displayed = runs.map((r, i) => r ? traceAt(r, cursors[i]) : null);
  const selectedRun = selection ? runs[selection.lane] : null;
  const selectedEvent = selection ? displayed[selection.lane]?.events.find(e => e.seq === selection.seq) : null;
  const canCompare = runs.every(Boolean) && displayed.every(v => v?.finished && v.evaluation.status === 'passed' && v.metrics.usageComplete) && runs[0]?.taskId === runs[1]?.taskId && runs[0]?.models.executor === runs[1]?.models.executor;

  async function start() {
    if (!task || busy || fetching.current) return;
    setPending(true); setFocus(true); setCompact(true); setError(''); setSelection(null); setPlaying(false); setRuns([null, null]); setIds(['', '']); setLive(true); setPosition(0);
    const results = await Promise.allSettled(strategies.map(strategy => api<{ id: string }>('/api/taskbank/runs', { method: 'POST', body: JSON.stringify({ taskId, strategy }) })));
    setIds(results.map(r => r.status === 'fulfilled' ? r.value.id : '') as [string, string]);
    const failures = results.flatMap((r, i) => r.status === 'rejected' ? [`${strategyNames[strategies[i]]}：${r.reason.message}`] : []);
    if (failures.length) setError(`部分任务提交失败，已成功提交的任务仍继续：${failures.join('；')}`);
    setPending(false);
  }
  async function stop(i: number) {
    if (!ids[i]) return;
    try { await api(`/api/taskbank/runs/${ids[i]}/cancel`, { method: 'POST', body: '{}' }); } catch (e) { setError((e as Error).message); }
  }
  function chooseRun(i: number, id: string) { setPlaying(false); setLive(false); setPosition(Infinity); setSelection(null); setIds(old => old.map((x, index) => index === i ? id : x) as [string, string]); setRuns(old => old.map((x, index) => index === i ? null : x) as typeof old); }
  function changeStrategy(i: number, value: Strategy) { setStrategies(old => old.map((x, index) => index === i ? value : x) as typeof old); }
  return <div className={`execution-demo ${focus ? 'demo-focused' : ''}`}>
    <div className="demo-heading"><div><span className="demo-eyebrow">执行观测 / AGENT OBSERVATORY</span><h1>看见 Agent 如何完成工作</h1><p>同一个任务，两条真实执行轨迹。观察模型决策、图调度和每一次工具返回。</p></div><div className="demo-view-controls"><button onClick={() => { setFocus(!focus); setCompact(!focus); }}>{focus ? '退出专注' : '专注展示'}</button><span className={`demo-mode ${live ? 'live' : ''}`}><i />{live ? busy ? '实时执行' : '实时执行已结束' : '历史轨迹 · 回放'}</span></div></div>
    {compact && <div className="demo-compact-task"><span>{task?.title} · {taskId} · {task?.recordCount} 条记录</span><button onClick={() => setCompact(false)}>展开任务设置</button></div>}
    <section className={`demo-controls ${compact ? 'demo-hidden' : ''}`}>
      <div className="demo-task-controls"><label>业务场景<select disabled={busy} value={task?.scenario || 'tickets'} onChange={e => { const next = tasks.find(t => t.scenario === e.target.value); if (next) setTaskId(next.id); }}>{Object.entries(sources).map(([k, title]) => <option key={k} value={k}>{title}</option>)}</select></label><label className="demo-task-picker">任务<select aria-label="演示任务" disabled={busy} value={taskId} onChange={e => setTaskId(e.target.value)}>{tasks.filter(t => t.scenario === (task?.scenario || 'tickets')).map(t => <option key={t.id} value={t.id}>{t.title} · {t.id} · {t.split}</option>)}</select></label><button className="button primary" disabled={!task || busy} onClick={() => void start()}><Play size={16} />{pending ? '正在提交…' : '并排运行真实任务'}</button></div>
      {task && <><p className="demo-source"><span>{task.recordCount} 条记录</span><span>{task.split}</span><a href={task.sourceUrl} target="_blank" rel="noreferrer">数据来源 ↗</a><span>公开历史记录 · 项目设计任务</span></p><details><summary>查看完整任务要求</summary><p className="demo-task-text">{task.task}</p></details></>}
      <div className="demo-agent-controls">{strategies.map((strategy, i) => <div key={i}><label>Agent {i === 0 ? 'A' : 'B'}<select aria-label={`Agent ${i === 0 ? 'A' : 'B'} 策略`} value={strategy} disabled={busy} onChange={e => changeStrategy(i, e.target.value as Strategy)}>{Object.entries(strategyNames).map(([k, title]) => <option key={k} value={k}>{title}</option>)}</select></label><label>历史运行<select aria-label={`Agent ${i === 0 ? 'A' : 'B'} 历史运行`} disabled={busy} value={ids[i]} onChange={e => chooseRun(i, e.target.value)}><option value="">暂无记录 / 等待执行</option>{ids[i] && !summaries.some(r => r.id === ids[i]) && <option value={ids[i]}>{ids[i].slice(0, 8)} · 本次运行</option>}{summaries.filter(r => r.strategy === strategy).map(r => <option value={r.id} key={r.id}>{r.id.slice(0, 8)} · {r.evaluation.status} · {r.metrics.modelRequests} LLM</option>)}</select></label></div>)}</div>
    </section>
    {error && <div className="demo-error" role="alert">{error}<button onClick={() => setError('')}>关闭</button></div>}
    <div className="demo-player"><button disabled={!readyReplay} onClick={() => { setFocus(true); setCompact(true); setLive(false); setPosition(0); setSelection(null); setPlaying(true); }}><RotateCcw size={15} />从头回放</button><button aria-label={playing ? '暂停回放' : '播放回放'} disabled={!readyReplay} onClick={() => { setLive(false); if (position >= duration) setPosition(0); setPlaying(!playing); }}>{playing ? <Pause size={16} /> : <Play size={16} />}</button><input aria-label="轨迹回放进度" type="range" min="0" max={Math.ceil(timelineDuration)} step="1" value={live ? Math.max(...cursors) : Math.min(position, duration)} disabled={!readyReplay} onChange={e => { setLive(false); setPlaying(false); setPosition(Number(e.target.value)); }} /><time>{seconds(live ? Math.max(...cursors) : Math.min(position, duration))}{live && busy ? ' · 执行中' : ` / ${seconds(duration)}`}</time><select aria-label="回放速度" value={speed} onChange={e => setSpeed(Number(e.target.value))}>{[1, 2, 4, 8, 16].map(x => <option key={x} value={x}>{x}×</option>)}</select></div>
    <div className="demo-lanes">{strategies.map((s, i) => <RunLane key={`${i}-${ids[i]}`} label={i === 0 ? 'A' : 'B'} strategy={s} run={runs[i]} cursor={cursors[i]} live={live} timelineDuration={timelineDuration} onStop={() => void stop(i)} onInspect={event => setSelection({ lane: i, seq: event.seq })} />)}</div>
    <section className="demo-verdict"><h2>本次对照</h2>{canCompare && runs[0] && runs[1] ? <><p>两边结构化事实与证据评分均通过，报告文字未评分。B 相对 A：</p><div>{[['LLM 调用', runs[0].metrics.modelRequests - runs[1].metrics.modelRequests, '次'], ['总 token', runs[0].metrics.inputTokens + runs[0].metrics.outputTokens - runs[1].metrics.inputTokens - runs[1].metrics.outputTokens, ''], ['执行延迟', (runs[0].metrics.durationMs - runs[1].metrics.durationMs) / 1000, 's'], ['工具调用', runs[0].metrics.toolCalls - runs[1].metrics.toolCalls, '次']].map(([title, diff, unit]) => <article key={title}><small>{title}</small><strong className={Number(diff) > 0 ? 'saving' : Number(diff) < 0 ? 'regression' : ''}>{Number(diff) > 0 ? '减少' : Number(diff) < 0 ? '增加' : '相同'} {Number(diff) === 0 ? '' : title === '执行延迟' ? Math.abs(Number(diff)).toFixed(1) : n(Math.abs(Number(diff)))}{Number(diff) === 0 ? '' : unit}</strong></article>)}</div></> : <p>待两边执行结束、同任务同执行模型、用量完整且评分通过后展示差值。</p>}<p className="demo-footnote">单次演示不代表平均收益。两边共享调度资源；回放不调用模型。图内消除次数与相对基线减少次数分开统计。</p></section>
    {selectedEvent && selectedRun && <div className="demo-inspector" role="dialog" aria-modal="false" aria-label="执行事件详情"><header><strong>Agent {selection?.lane === 0 ? 'A' : 'B'} · #{selectedEvent.seq} · {eventNames[selectedEvent.type] || selectedEvent.type}</strong><button onClick={() => setSelection(null)} aria-label="关闭事件详情">关闭</button></header><h3>{selectedEvent.title}</h3><p>{selectedEvent.at} · 相对执行开始 {seconds(eventTime(selectedRun, selectedEvent))}</p><pre>{pretty(selectedEvent.detail)}</pre><small>展示模型返回的操作说明和工具数据，不展示隐藏思维链；所有内容来自这条运行记录。</small></div>}
  </div>;
}
