import { ArrowRight, Braces, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, CircleDot, ExternalLink, GitBranch, Network, Pause, Play, PlayCircle, RotateCcw, Wrench } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { GraphNode, PairDetail, SHOWCASE_EXPERIMENT, Showcase, Step, TimelineEvent, duration, number, shorterTool, taskFromHash, total } from './showcase';
import './showcase.css';

function Dag({ nodes, activeNodeId }: { nodes: GraphNode[]; activeNodeId?: string | null }) {
  if (!nodes.length) return <div className="dag-empty">Baseline 在模型轮次中动态选择下一次工具调用。</div>;
  const levels = new Map<string, number>();
  for (let pass = 0; pass < nodes.length; pass++) for (const node of nodes) if (!levels.has(node.id) && node.dependencies.every(id => levels.has(id))) levels.set(node.id, Math.max(-1, ...node.dependencies.map(id => levels.get(id) || 0)) + 1);
  const groups = [...new Set(nodes.map(node => levels.get(node.id) || 0))];
  return <div className="dag-canvas">{groups.map((level, index) => <div className="dag-column" key={level}>{nodes.filter(node => (levels.get(node.id) || 0) === level).map(node => <div className={`dag-node ${activeNodeId === node.id ? 'active' : ''}`} key={node.id}><small>{node.id}</small><strong>{shorterTool(node.tool)}</strong>{node.filter && <span>筛选 {node.filter.field} = {String(node.filter.value)}</span>}{node.boundArguments[0] && <em>{bindingText(node.boundArguments[0])}</em>}</div>)}{index < groups.length - 1 && <ArrowRight className="dag-arrow" size={16} />}</div>)}</div>;
}

function bindingText(value: Record<string, unknown> | string) {
  if (typeof value === 'string') return value;
  return Object.entries(value).map(([key, item]) => `${key} ← ${String(item).slice(0, 18)}`).join(' · ');
}

function readable(detail: Step['detail']) { return Array.isArray(detail) ? detail.filter(Boolean).join(' → ') : typeof detail === 'string' ? detail : Object.entries(detail).map(([key, value]) => `${key}: ${String(value)}`).join(' · '); }

function eventAt(timeline: TimelineEvent[], step: number) { return timeline[Math.min(step, Math.max(0, timeline.length - 1))]; }
function channelName(event?: TimelineEvent) { return event?.channel === 'model' ? '模型决策' : event?.channel === 'structured' ? '结构化执行' : '校验 / 控制'; }
function modelTurns(run: PairDetail['runs']['baseline']) { return run.timeline.filter(event => event.kind === 'model_start').length; }
function modelToolCalls(run: PairDetail['runs']['baseline']) { return run.timeline.filter(event => event.kind === 'action' && event.executor === 'model').length; }
function structuredSteps(run: PairDetail['runs']['baseline']) { return run.timeline.filter(event => event.channel === 'structured').length; }
function graphToolCalls(run: PairDetail['runs']['baseline']) { return run.timeline.filter(event => event.kind === 'action' && event.executor === 'graph').length; }

function EventRail({ timeline, step, onStep }: { timeline: TimelineEvent[]; step: number; onStep: (next: number) => void }) {
  return <div className="event-rail" aria-label="保存的细粒度执行事件">{timeline.map((event, index) => <button key={event.position} onClick={() => onStep(index)} className={`${event.channel} ${index === step ? 'active' : ''} ${index < step ? 'done' : ''}`} title={`${index + 1}. ${event.title}`} aria-label={`${index + 1}. ${event.title}`}><span>{event.channel === 'model' ? 'M' : event.channel === 'structured' ? 'S' : 'C'}</span></button>)}</div>;
}

function FilmLane({ label, run, accent, step, onStep }: { label: string; run: PairDetail['runs']['baseline']; accent: 'baseline' | 'rsi'; step: number; onStep: (next: number) => void }) {
  const event = eventAt(run.timeline, step);
  const metrics = event?.metrics || {};
  const isGraphAction = event?.kind === 'action' && event.executor === 'graph';
  const isModelAction = event?.kind === 'action' && event.executor === 'model';
  return <article className={`film-lane ${accent}`}><header><div><small>{label}</small><h3>{accent === 'baseline' ? '模型持续决定下一步' : '模型完成语义，图执行确定部分'}</h3></div><span>{modelTurns(run)} 次模型</span></header><div className="film-counts"><div><b>{modelTurns(run)}</b><span>模型请求</span></div><div><b>{accent === 'baseline' ? modelToolCalls(run) : graphToolCalls(run)}</b><span>{accent === 'baseline' ? '模型调度工具' : '图调度工具'}</span></div><div><b>{accent === 'rsi' ? structuredSteps(run) : 0}</b><span>{accent === 'rsi' ? '结构步骤' : '图结构步骤'}</span></div></div><div className={`film-current ${event?.channel || 'control'}`}><small>{channelName(event)} · #{Math.min(step + 1, run.timeline.length)}/{run.timeline.length}</small><strong>{event?.title || '等待开始'}</strong><div><span>{metrics.modelRequests || 0} LLM</span><span>{number(total(metrics))} token</span><span>{metrics.toolCalls || 0} 工具</span><span>{duration(Number(metrics.durationMs || event?.elapsedMs))}</span></div>{isGraphAction && <em>此工具调用由已保存 DAG 与当前观察参数直接绑定，不新增模型请求。</em>}{isModelAction && <em>此工具调用前的下一步选择由模型请求产生。</em>}</div>{accent === 'rsi' && <div className="film-dag"><Dag nodes={run.graphNodes} activeNodeId={event?.nodeId} /></div>}{accent === 'baseline' && <div className="film-baseline-map"><Network size={17} /><span>每次读取后的下一步工具选择，继续交由模型。</span></div>}<EventRail timeline={run.timeline} step={Math.min(step, Math.max(0, run.timeline.length - 1))} onStep={onStep} /></article>;
}

function FineReplay({ detail }: { detail: PairDetail }) {
  const baseline = detail.runs.baseline, rsi = detail.runs.rsi;
  const max = Math.max(baseline.timeline.length, rsi.timeline.length) - 1;
  const [step, setStep] = useState(0); const [playing, setPlaying] = useState(false); const [speed, setSpeed] = useState(1);
  useEffect(() => { setStep(0); setPlaying(false); }, [detail.taskId]);
  useEffect(() => { if (!playing) return; const timer = window.setInterval(() => setStep(value => value >= max ? 0 : value + 1), Math.round(700 / speed)); return () => window.clearInterval(timer); }, [playing, max, speed]);
  return <section className="fine-replay"><header><div><p className="showcase-kicker">DECISION SUBSTITUTION / FINE-GRAINED SAVED TRACE</p><h2>把“再问模型”换成可验证的执行结构。</h2><p>每一步来自保存事件；M 为模型请求，S 为图绑定、筛选或图执行，C 为评分和恢复控制。</p></div><div className="fine-controls"><button onClick={() => setStep(value => Math.max(0, value - 1))} aria-label="上一步" title="上一步"><ChevronLeft size={16} /></button><button onClick={() => setPlaying(value => !value)} aria-label={playing ? '暂停播放' : '播放细粒度回放'} title={playing ? '暂停' : '播放'}>{playing ? <Pause size={16} /> : <Play size={16} />}</button><button onClick={() => setStep(value => Math.min(max, value + 1))} aria-label="下一步" title="下一步"><ChevronRight size={16} /></button><button onClick={() => { setPlaying(false); setStep(0); }} aria-label="重置" title="重置"><RotateCcw size={16} /></button><button className="speed-control" onClick={() => setSpeed(value => value === .5 ? 1 : value === 1 ? 2 : .5)} aria-label="切换播放速度" title="切换播放速度">{speed}×</button></div></header><input className="fine-scrubber" type="range" min="0" max={max} value={step} onChange={event => { setPlaying(false); setStep(Number(event.target.value)); }} aria-label="细粒度回放时间步" /><div className="fine-summary"><div><span>Baseline</span><strong>{modelTurns(baseline)}</strong><small>模型请求，读取后继续由模型决定</small></div><i>→</i><div className="rsi-summary"><span>RSI</span><strong>{modelTurns(rsi)}</strong><small>模型请求 + {structuredSteps(rsi)} 个结构步骤</small></div><div><span>参数绑定</span><strong>{rsi.metrics.deterministicBindings || 0}</strong><small>来自当前任务观察，不复用旧业务值</small></div><div><span>跳过详情</span><strong>{rsi.metrics.filteredOutDetailReads || 0}</strong><small>由当前筛选结果决定</small></div></div><div className="film-lanes"><FilmLane label="A / BASELINE" run={baseline} accent="baseline" step={step} onStep={setStep} /><FilmLane label="B / RSI" run={rsi} accent="rsi" step={step} onStep={setStep} /></div></section>;
}

function TraceColumn({ label, run, accent }: { label: string; run: PairDetail['runs']['baseline']; accent: 'baseline' | 'rsi' }) {
  const displayed = run.steps.filter(step => ['plan', 'graph', 'motif', 'binding', 'tool', 'observation', 'model', 'check'].includes(step.kind));
  return <article className={`replay-lane ${accent}`}><header><div><small>{label}</small><h2>{accent === 'baseline' ? 'Plan + ReAct' : 'Graph RSI'}</h2></div><span>{run.evaluation.status === 'passed' ? <CheckCircle2 size={15} /> : <CircleDot size={15} />}{run.evaluation.status}</span></header><div className="replay-kpis"><div><span>LLM</span><strong>{run.metrics.modelRequests}</strong></div><div><span>token</span><strong>{number(total(run.metrics))}</strong></div><div><span>工具</span><strong>{run.metrics.toolCalls}</strong></div><div><span>时长</span><strong>{duration(Number(run.metrics.durationMs))}</strong></div></div>{accent === 'rsi' && <div className="replay-dag"><Dag nodes={run.graphNodes} /></div>}{accent === 'baseline' && <div className="replay-dag baseline-dag"><Dag nodes={run.graphNodes} /></div>}<div className="trace-steps">{displayed.map((step, index) => <div className={`trace-step ${step.kind}`} key={index}><span>{step.kind === 'tool' ? <Wrench size={14} /> : step.kind === 'graph' || step.kind === 'motif' || step.kind === 'binding' ? <GitBranch size={14} /> : step.kind === 'model' ? <PlayCircle size={14} /> : <Braces size={14} />}</span><div><b>{step.title}</b><p>{readable(step.detail)}</p>{step.executor && <small>{step.executor === 'graph' ? '图执行器' : '模型调度'}</small>}</div></div>)}</div>{typeof run.report.summary === 'string' && <div className="replay-report-summary"><small>业务结论</small><p>{run.report.summary}</p></div>}<footer><a href={run.id ? `/api/online-e2e/${SHOWCASE_EXPERIMENT}/runs/${accent}/${run.id}/report` : '#'} target="_blank" rel="noreferrer">业务报告 <ExternalLink size={13} /></a><details><summary>审计数据</summary><pre>{JSON.stringify(run.report, null, 2)}</pre></details></footer></article>;
}

export default function TaskReplay() {
  const [data, setData] = useState<Showcase | null>(null); const [taskId, setTaskId] = useState(taskFromHash()); const [detail, setDetail] = useState<PairDetail | null>(null); const [error, setError] = useState('');
  useEffect(() => { api<Showcase>(`/api/showcase/${SHOWCASE_EXPERIMENT}`).then(value => { setData(value); setTaskId(current => value.pairs.some(pair => pair.taskId === current) ? current : 'finance-cancelled_payments-02'); }).catch(error => setError(error.message)); }, []);
  useEffect(() => { if (!taskId) return; setDetail(null); api<PairDetail>(`/api/showcase/${SHOWCASE_EXPERIMENT}/pairs/${encodeURIComponent(taskId)}`).then(setDetail).catch(error => setError(error.message)); }, [taskId]);
  const scenarioPairs = useMemo(() => data?.pairs.filter(pair => pair.scenario === detail?.scenario) || [], [data, detail]);
  if (error) return <main className="showcase-page"><p className="showcase-error">读取任务回放失败：{error}</p></main>;
  if (!data || !detail) return <main className="showcase-page showcase-loading">正在打开已保存的 Agent 轨迹…</main>;
  const baseline = detail.runs.baseline, rsi = detail.runs.rsi;
  return <main className="showcase-page replay-page">
    <section className="replay-heading"><div><p className="showcase-kicker">TASK REPLAY / SAVED EXECUTION TRACE</p><h1>任务本身，和每一步执行。</h1><p>{detail.task.task}</p></div><div className="replay-select"><label>业务领域<select value={detail.scenario} onChange={event => { const first = data.pairs.find(pair => pair.scenario === event.target.value); if (first) { setTaskId(first.taskId); window.history.replaceState(null, '', `#replay?task=${encodeURIComponent(first.taskId)}`); } }}>{data.categories.map(category => <option key={category.scenario} value={category.scenario}>{category.label} · {category.taskCount} 任务</option>)}</select></label><label>领域内任务<select value={taskId} onChange={event => { setTaskId(event.target.value); window.history.replaceState(null, '', `#replay?task=${encodeURIComponent(event.target.value)}`); }}>{scenarioPairs.map(pair => <option key={pair.taskId} value={pair.taskId}>{pair.taskId}</option>)}</select></label></div></section>
    <section className="replay-task"><div><span>{detail.familyLabel}</span><h2>{detail.taskId}</h2><p>{detail.recordCount} 条记录 · 第 {detail.round} 轮 · {detail.launchOrder.join(' → ')}</p></div><div><span>结构化结果</span><strong>{baseline.evaluation.status} / {rsi.evaluation.status}</strong><p>metrics、selectedIds、evidenceIds 精确验收</p></div><div><span>本次 RSI 路径</span><strong>{rsi.evolution?.planningPath === 'fast' ? 'Fast 复用' : 'Fallback'}</strong><p>{rsi.evolution?.usedVersionId ? `Workflow ${String(rsi.evolution.usedVersionId).slice(0, 8)}` : '从当前任务编译 G0'}</p></div></section>
    <section className="replay-verdict"><div><span>同一任务的 token 差</span><strong>{number(total(baseline.metrics) - total(rsi.metrics))}</strong><small>Baseline {number(total(baseline.metrics))} · RSI {number(total(rsi.metrics))}</small></div><div><span>模型调用差</span><strong>{Number(baseline.metrics.modelRequests) - Number(rsi.metrics.modelRequests)}</strong><small>Baseline {baseline.metrics.modelRequests} · RSI {rsi.metrics.modelRequests}</small></div><a href={detail.links.rsi.trace} target="_blank" rel="noreferrer">打开 RSI 原始 JSON <ExternalLink size={14} /></a></section>
    <FineReplay detail={detail} />
    <section className="replay-lanes"><TraceColumn label="A / BASELINE" run={baseline} accent="baseline" /><TraceColumn label="B / RSI" run={rsi} accent="rsi" /></section>
    <section className="replay-footer"><ChevronDown size={16} /><p>模型输出展示的是可见的计划、工具调用说明和业务结论，不展示隐藏思维链。DAG 的箭头代表已保存的节点依赖，节点内参数是本次任务的实际绑定值。</p></section>
  </main>;
}
