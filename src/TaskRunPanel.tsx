import { useEffect, useState } from 'react';
import { Play, Square } from 'lucide-react';
import { api } from './api';
type ReadGraph = { status: string; nodes: { id: string; tool: string; dependencies: string[] }[]; nodeStates: Record<string, string> };
type Run = { id: string; taskId: string; status: string; phase: string; models: { planner: string; executor: string; distinctModels: boolean }; metrics: { modelRequests: number; toolCalls: number; toolErrors: number; controlErrors?: number; inputTokens: number; outputTokens: number; usageComplete: boolean; peakReads: number; queueMs: number }; phaseMetrics?: Record<string, { requests: number; inputTokens: number; outputTokens: number }>; evaluation: { status: string; issues: string[] }; plan?: unknown; graph?: ReadGraph; retrieval?: unknown; submission?: unknown; error?: string; fallback?: string };

function ReadGraphView({ graph }: { graph: ReadGraph }) {
  const depth = new Map<string, number>();
  for (let i = 0; i < graph.nodes.length; i++) for (const n of graph.nodes) if (!depth.has(n.id) && n.dependencies.every(k => depth.has(k))) depth.set(n.id, Math.max(-1, ...n.dependencies.map(k => depth.get(k)!)) + 1);
  const position = new Map(graph.nodes.map(n => [n.id, { x: 15 + (depth.get(n.id) || 0) * 210, y: 20 + graph.nodes.filter(p => depth.get(p.id) === depth.get(n.id)).findIndex(p => p.id === n.id) * 82 }]));
  const width = Math.max(440, ...[...position.values()].map(p => p.x + 200));
  const height = Math.max(110, ...[...position.values()].map(p => p.y + 85));
  return <div style={{ overflowX: 'auto', margin: '16px 0' }}><svg role="img" aria-label="本次自动生成的读取依赖图" viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', minWidth: 440 }}>
    <defs><marker id="task-dag-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#81909f" /></marker></defs>
    {graph.nodes.flatMap(n => n.dependencies.map(dep => { const a = position.get(dep)!, b = position.get(n.id)!; return <path key={dep + n.id} d={`M${a.x + 180},${a.y + 28} L${b.x},${b.y + 28}`} fill="none" stroke="#81909f" markerEnd="url(#task-dag-arrow)" />; }))}
    {graph.nodes.map(n => { const p = position.get(n.id)!; return <g key={n.id} transform={`translate(${p.x},${p.y})`}><title>{n.tool}</title><rect width="180" height="60" rx="5" fill={graph.nodeStates[n.id] === 'failed' ? '#fff0f0' : '#edf4f1'} stroke="#b8c8c0" /><text x="9" y="22" fontSize="11">{n.tool.length > 25 ? n.tool.slice(0, 23) + '…' : n.tool}</text><text x="9" y="43" fontSize="10">{n.id.slice(0, 20)} · {graph.nodeStates[n.id]}</text></g>; })}
  </svg></div>;
}
export default function TaskRunPanel({ taskId }: { taskId: string }) {
  const [strategy, setStrategy] = useState('autotool');
  const [runs, setRuns] = useState<Run[]>([]);
  const [current, setCurrent] = useState('');
  const [detail, setDetail] = useState<Run | null>(null);
  const [scheduler, setScheduler] = useState<{ queued: number; active: { runs: number; models: number; reads: number } } | null>(null);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  useEffect(() => {
    let stopped = false; let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const data = await api<{ runs: Run[]; scheduler: typeof scheduler }>('/api/taskbank/runs');
        if (!stopped) { setRuns(data.runs); setScheduler(data.scheduler); }
        if (current) { const run = await api<Run>('/api/taskbank/runs/' + current); if (!stopped) setDetail(run); }
      } catch (e) { if (!stopped) setError((e as Error).message); }
      if (!stopped) timer = setTimeout(poll, 1500);
    }
    void poll(); return () => { stopped = true; clearTimeout(timer); };
  }, [current]);
  async function start() {
    setPending(true); setError('');
    try { const run = await api<{ id: string }>('/api/taskbank/runs', { method: 'POST', body: JSON.stringify({ taskId, strategy }) }); setCurrent(run.id); setDetail(null); }
    catch (e) { setError((e as Error).message); } finally { setPending(false); }
  }
  return <section style={{ borderTop: '1px solid #ccd4da', marginTop: 18, paddingTop: 12 }}>
    <h2>Agent 执行 · Plan / AutoTool</h2>
    <div className="taskbank-toolbar"><select aria-label="任务执行策略" value={strategy} onChange={e => setStrategy(e.target.value)}><option value="react">ReAct 基线</option><option value="plan_react">Plan + ReAct</option><option value="autotool">Plan + AutoTool DAG</option></select><button className="button primary" disabled={pending} onClick={() => void start()}><Play size={14} />提交任务</button></div>
    {scheduler && <p>排队 {scheduler.queued} · 执行 {scheduler.active.runs} · 模型请求并发 {scheduler.active.models} · 读取并发 {scheduler.active.reads}</p>}
    {error && <p role="alert">{error}</p>}
    <label>执行记录 <select value={current} onChange={e => { setCurrent(e.target.value); setDetail(null); }}><option value="">选择运行</option>{runs.map(r => <option key={r.id} value={r.id}>{r.taskId} · {r.id.slice(0, 6)} · {r.status}</option>)}</select></label>
    {detail && <>
      <p>{detail.phase} · {detail.status} · 结构化评分 {detail.evaluation.status}</p>
      <p>规划模型：{detail.models.planner} · 执行模型：{detail.models.executor} · {detail.models.distinctModels ? '不同模型' : '同模型（未配置独立规划模型）'}</p>
      <p>LLM {detail.metrics.modelRequests} 次 · 工具 {detail.metrics.toolCalls} 次 · 工具错误 {detail.metrics.toolErrors} 次 · 输入/输出 token {detail.metrics.inputTokens}/{detail.metrics.outputTokens}{!detail.metrics.usageComplete && '（统计不完整）'} · 读取峰值 {detail.metrics.peakReads}</p>
      <p>Plan/图格式错误 {detail.metrics.controlErrors ?? '未记录'} · 排队 {detail.metrics.queueMs} ms</p>
      {detail.graph && <ReadGraphView graph={detail.graph} />}
      {['running', 'queued'].includes(detail.status) && <button className="button" onClick={() => { void api(`/api/taskbank/runs/${detail.id}/cancel`, { method: 'POST', body: '{}' }).catch(e => setError(e.message)); }}><Square size={14} />取消</button>}
      {detail.error && <p>{detail.error}</p>}{detail.fallback && <p>回退：{detail.fallback}</p>}
      {Object.entries({ '阶段计量': detail.phaseMetrics, 'Plan': detail.plan, '意图与工具召回': detail.retrieval, '读取 DAG': detail.graph, '报告与评分': { submission: detail.submission, evaluation: detail.evaluation } }).map(([label, value]) => <details key={label}><summary>{label}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>)}
    </>}
  </section>;
}
