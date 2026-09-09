import { useState } from 'react';
import { ArrowDownToLine, GitBranch, LoaderCircle, Play, ShieldCheck } from 'lucide-react';
import type { AgentRun, TaskGraph } from '../shared/types';

export default function GraphPanel({ graphs, run, busy, onLearn, onUse }: { graphs: TaskGraph[]; run: AgentRun | null; busy: boolean; onLearn: () => Promise<void>; onUse: (graph: TaskGraph) => void }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [nodeId, setNodeId] = useState<string | null>(null);
  const [learning, setLearning] = useState(false);
  const graph = graphs.find(item => item.id === selected) || graphs[0];
  const node = graph?.nodes.find(item => item.id === nodeId);
  const depths = new Map<string, number>();
  if (graph) for (let attempt = 0; attempt < graph.nodes.length; attempt++) for (const item of graph.nodes) if (!depths.has(item.id) && item.dependencies.every(id => depths.has(id))) depths.set(item.id, Math.max(-1, ...item.dependencies.map(id => depths.get(id)!)) + 1);
  const levels = graph ? [...new Set(depths.values())].sort() : [];
  const maxRows = Math.max(1, ...levels.map(level => graph!.nodes.filter(item => depths.get(item.id) === level).length));
  const positions = new Map(graph?.nodes.map(item => [item.id, { x: 25 + (depths.get(item.id) || 0) * 252, y: 22 + graph.nodes.filter(peer => depths.get(peer.id) === depths.get(item.id)).findIndex(peer => peer.id === item.id) * 94 }]) || []);
  return <>
    <div className="page-heading"><div><div className="eyebrow">EXPERIENCE / GRAPH-BASED RSI</div><h1>任务图经验库</h1><p>从真实轨迹提取读取结构，绑定本次数据，按依赖执行。</p></div><button className="button primary" disabled={busy || learning || run?.request.mode !== 'live' || run?.status !== 'completed'} onClick={async () => { setLearning(true); try { await onLearn(); } finally { setLearning(false); } }}>{learning ? <LoaderCircle size={16} className="spin" /> : <GitBranch size={16} />}从当前运行学习</button></div>
    <div className="graph-guidance"><ShieldCheck size={17} /><span>图只复用读取步骤。写入、回复和报告由模型处理；“影子验证通过”表示接口与数据绑定可执行，不代表报告语义完全正确。</span></div>
    {!graph ? <section className="panel"><div className="empty-state"><span><GitBranch size={28} /></span><h3>还没有经过验证的任务图</h3><p>从左侧历史加载一次真实模型运行后点击“从当前运行学习”；也可选择 Graph RSI 运行任务，冷启动完成后自动学习。</p></div></section> : <div className="graph-workspace">
      <aside className="panel graph-list">{graphs.map(item => <button key={item.id} className={item.id === graph.id ? 'selected' : ''} onClick={() => { setSelected(item.id); setNodeId(null); }}><strong>{item.source} · v{item.version}</strong><span>{item.nodes.length} 个节点 · 来源 {item.sourceRunId.slice(0, 8)}</span><p>{item.task.slice(0, 74)}{item.task.length > 74 ? '…' : ''}</p></button>)}</aside>
      <section className="panel"><div className="panel-heading"><h2><GitBranch size={16} />读取任务图 v{graph.version}</h2><button className="text-button" disabled={busy} onClick={() => onUse(graph)}><Play size={14} />使用这份经验</button></div>
        <div className="graph-canvas"><svg role="img" aria-label="任务图数据依赖关系" width={Math.max(510, levels.length * 252 + 30)} height={maxRows * 94 + 24}>
          <defs><marker id="graph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#a3b796" /></marker></defs>
          {graph.nodes.flatMap(item => item.dependencies.map(dependency => { const start = positions.get(dependency), end = positions.get(item.id); return start && end ? <path key={`${dependency}-${item.id}`} d={`M${start.x + 218},${start.y + 31} C${start.x + 236},${start.y + 31} ${end.x - 20},${end.y + 31} ${end.x},${end.y + 31}`} fill="none" stroke="#b5c7a9" markerEnd="url(#graph-arrow)" /> : null; }))}
          {graph.nodes.map(item => { const point = positions.get(item.id)!; const state = run?.graph?.graphId === graph.id ? run.graph.nodeStates[item.id] : undefined; return <g key={item.id} transform={`translate(${point.x},${point.y})`} role="button" tabIndex={0} aria-label={`图节点 ${item.id} ${item.tool}`} onClick={() => setNodeId(item.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') setNodeId(item.id); }} className={`graph-node ${node?.id === item.id ? 'selected' : ''} ${state || ''}`}><rect width="218" height="66" rx="9" /><text x="12" y="20" className="graph-node-id">{item.id} · {item.foreach ? '遍历本次记录' : item.paginate ? '自动分页' : '读取'}</text><text x="12" y="43" className="graph-node-label">{item.tool.length > 28 ? item.tool.slice(0, 26) + '…' : item.tool}</text>{state === 'done' && <text x="196" y="20">✓</text>}</g>; })}
        </svg></div>
        <div className="graph-facts"><div><span>学习来源模型请求</span><strong>{graph.sourceModelRequests}</strong></div><div><span>影子验证工具调用</span><strong>{graph.validation.toolCalls}</strong></div><div><span>编译＋验证耗时</span><strong>{graph.validation.compileMs + graph.validation.durationMs}<small> ms</small></strong></div><div><span>学习额外 LLM 请求</span><strong>{graph.validation.learningModelRequests}</strong></div></div>
        <div className="graph-detail"><h3>{node ? `${node.id} · 参数绑定` : '适用任务'}</h3>{node ? <pre>{JSON.stringify({ arguments: node.arguments, foreach: node.foreach, paginate: node.paginate, dependencies: node.dependencies, sourceEvents: node.sourceEventSeqs }, null, 2)}</pre> : <p>{graph.task}</p>}<p className="graph-footnote">来源运行 {graph.sourceRunId}。复用时重新调用工具；图文件不保存历史工具输出或回复内容。</p><a className="text-button" href={`/api/graphs/${graph.id}/export`}><ArrowDownToLine size={14} />导出任务图 JSON</a></div>
      </section>
    </div>}
  </>;
}
