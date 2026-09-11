import { ArrowRight, Braces, CheckCircle2, ChevronDown, CircleDot, ExternalLink, GitBranch, PlayCircle, Wrench } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { GraphNode, PairDetail, SHOWCASE_EXPERIMENT, Showcase, Step, duration, number, shorterTool, taskFromHash, total } from './showcase';
import './showcase.css';

function Dag({ nodes }: { nodes: GraphNode[] }) {
  if (!nodes.length) return <div className="dag-empty">Baseline 在模型轮次中动态选择下一次工具调用。</div>;
  const levels = new Map<string, number>();
  for (let pass = 0; pass < nodes.length; pass++) for (const node of nodes) if (!levels.has(node.id) && node.dependencies.every(id => levels.has(id))) levels.set(node.id, Math.max(-1, ...node.dependencies.map(id => levels.get(id) || 0)) + 1);
  const groups = [...new Set(nodes.map(node => levels.get(node.id) || 0))];
  return <div className="dag-canvas">{groups.map((level, index) => <div className="dag-column" key={level}>{nodes.filter(node => (levels.get(node.id) || 0) === level).map(node => <div className="dag-node" key={node.id}><small>{node.id}</small><strong>{shorterTool(node.tool)}</strong>{node.filter && <span>筛选 {node.filter.field} = {String(node.filter.value)}</span>}{node.boundArguments[0] && <em>{bindingText(node.boundArguments[0])}</em>}</div>)}{index < groups.length - 1 && <ArrowRight className="dag-arrow" size={16} />}</div>)}</div>;
}

function bindingText(value: Record<string, unknown> | string) {
  if (typeof value === 'string') return value;
  return Object.entries(value).map(([key, item]) => `${key} ← ${String(item).slice(0, 18)}`).join(' · ');
}

function readable(detail: Step['detail']) { return Array.isArray(detail) ? detail.filter(Boolean).join(' → ') : typeof detail === 'string' ? detail : Object.entries(detail).map(([key, value]) => `${key}: ${String(value)}`).join(' · '); }

function TraceColumn({ label, run, accent }: { label: string; run: PairDetail['runs']['baseline']; accent: 'baseline' | 'rsi' }) {
  const displayed = run.steps.filter(step => ['plan', 'graph', 'motif', 'binding', 'tool', 'observation', 'model', 'check'].includes(step.kind));
  return <article className={`replay-lane ${accent}`}><header><div><small>{label}</small><h2>{accent === 'baseline' ? 'Plan + ReAct' : 'Graph RSI'}</h2></div><span>{run.evaluation.status === 'passed' ? <CheckCircle2 size={15} /> : <CircleDot size={15} />}{run.evaluation.status}</span></header><div className="replay-kpis"><div><span>LLM</span><strong>{run.metrics.modelRequests}</strong></div><div><span>token</span><strong>{number(total(run.metrics))}</strong></div><div><span>工具</span><strong>{run.metrics.toolCalls}</strong></div><div><span>时长</span><strong>{duration(Number(run.metrics.durationMs))}</strong></div></div>{accent === 'rsi' && <div className="replay-dag"><Dag nodes={run.graphNodes} /></div>}{accent === 'baseline' && <div className="replay-dag baseline-dag"><Dag nodes={run.graphNodes} /></div>}<div className="trace-steps">{displayed.map((step, index) => <div className={`trace-step ${step.kind}`} key={index}><span>{step.kind === 'tool' ? <Wrench size={14} /> : step.kind === 'graph' || step.kind === 'motif' || step.kind === 'binding' ? <GitBranch size={14} /> : step.kind === 'model' ? <PlayCircle size={14} /> : <Braces size={14} />}</span><div><b>{step.title}</b><p>{readable(step.detail)}</p>{step.executor && <small>{step.executor === 'graph' ? '图执行器' : '模型调度'}</small>}</div></div>)}</div>{typeof run.report.summary === 'string' && <div className="replay-report-summary"><small>业务结论</small><p>{run.report.summary}</p></div>}<footer><a href={run.id ? `/api/online-e2e/${SHOWCASE_EXPERIMENT}/runs/${accent}/${run.id}/report` : '#'} target="_blank" rel="noreferrer">业务报告 <ExternalLink size={13} /></a><details><summary>审计数据</summary><pre>{JSON.stringify(run.report, null, 2)}</pre></details></footer></article>;
}

export default function TaskReplay() {
  const [data, setData] = useState<Showcase | null>(null); const [taskId, setTaskId] = useState(taskFromHash()); const [detail, setDetail] = useState<PairDetail | null>(null); const [error, setError] = useState('');
  useEffect(() => { api<Showcase>(`/api/showcase/${SHOWCASE_EXPERIMENT}`).then(value => { setData(value); setTaskId(current => value.pairs.some(pair => pair.taskId === current) ? current : 'finance-cancelled_payments-02'); }).catch(error => setError(error.message)); }, []);
  useEffect(() => { if (!taskId) return; setDetail(null); api<PairDetail>(`/api/showcase/${SHOWCASE_EXPERIMENT}/pairs/${encodeURIComponent(taskId)}`).then(setDetail).catch(error => setError(error.message)); }, [taskId]);
  const familyPairs = useMemo(() => data?.pairs.filter(pair => pair.scenario === detail?.scenario && pair.family === detail?.family) || [], [data, detail]);
  if (error) return <main className="showcase-page"><p className="showcase-error">读取任务回放失败：{error}</p></main>;
  if (!data || !detail) return <main className="showcase-page showcase-loading">正在打开已保存的 Agent 轨迹…</main>;
  const baseline = detail.runs.baseline, rsi = detail.runs.rsi;
  return <main className="showcase-page replay-page">
    <section className="replay-heading"><div><p className="showcase-kicker">TASK REPLAY / SAVED EXECUTION TRACE</p><h1>任务本身，和每一步执行。</h1><p>{detail.task.task}</p></div><div className="replay-select"><label>任务族<select value={`${detail.scenario}/${detail.family}`} onChange={event => { const first = data.pairs.find(pair => `${pair.scenario}/${pair.family}` === event.target.value); if (first) { setTaskId(first.taskId); window.history.replaceState(null, '', `#replay?task=${encodeURIComponent(first.taskId)}`); } }}>{data.families.map(family => <option key={family.id} value={`${family.scenario}/${family.family}`}>{family.label}</option>)}</select></label><label>族内任务<select value={taskId} onChange={event => { setTaskId(event.target.value); window.history.replaceState(null, '', `#replay?task=${encodeURIComponent(event.target.value)}`); }}>{familyPairs.map(pair => <option key={pair.taskId} value={pair.taskId}>{pair.taskId}</option>)}</select></label></div></section>
    <section className="replay-task"><div><span>{detail.familyLabel}</span><h2>{detail.taskId}</h2><p>{detail.recordCount} 条记录 · 第 {detail.round} 轮 · {detail.launchOrder.join(' → ')}</p></div><div><span>结构化结果</span><strong>{baseline.evaluation.status} / {rsi.evaluation.status}</strong><p>metrics、selectedIds、evidenceIds 精确验收</p></div><div><span>本次 RSI 路径</span><strong>{rsi.evolution?.planningPath === 'fast' ? 'Fast 复用' : 'Fallback'}</strong><p>{rsi.evolution?.usedVersionId ? `Workflow ${String(rsi.evolution.usedVersionId).slice(0, 8)}` : '从当前任务编译 G0'}</p></div></section>
    <section className="replay-verdict"><div><span>同一任务的 token 差</span><strong>{number(total(baseline.metrics) - total(rsi.metrics))}</strong><small>Baseline {number(total(baseline.metrics))} · RSI {number(total(rsi.metrics))}</small></div><div><span>模型调用差</span><strong>{Number(baseline.metrics.modelRequests) - Number(rsi.metrics.modelRequests)}</strong><small>Baseline {baseline.metrics.modelRequests} · RSI {rsi.metrics.modelRequests}</small></div><a href={detail.links.rsi.trace} target="_blank" rel="noreferrer">打开 RSI 原始 JSON <ExternalLink size={14} /></a></section>
    <section className="replay-lanes"><TraceColumn label="A / BASELINE" run={baseline} accent="baseline" /><TraceColumn label="B / RSI" run={rsi} accent="rsi" /></section>
    <section className="replay-footer"><ChevronDown size={16} /><p>模型输出展示的是可见的计划、工具调用说明和业务结论，不展示隐藏思维链。DAG 的箭头代表已保存的节点依赖，节点内参数是本次任务的实际绑定值。</p></section>
  </main>;
}
