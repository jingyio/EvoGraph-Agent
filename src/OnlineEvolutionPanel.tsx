import { useEffect, useState } from 'react';
import { GitBranch } from 'lucide-react';
import { api } from './api';
import TaskRunPanel from './TaskRunPanel';

type Version = {
  id: string; parentGraphId: string | null; generation: number; scenario: string; family: string;
  sourceRunId: string; sourceTaskId: string; status: string; scope: string;
  patches: { operation: string; nodeId?: string; sourceNodeId?: string; condition?: { field: string; operator: string; value: unknown }; reason: string; fields?: string[] }[];
  nodes: { id: string; tool: string; dependencies: string[]; foreach?: { filter?: { field: string; operator: string; value: unknown } }; reuse?: { fields: string[]; onMissing?: string }; defer?: boolean }[];
  evidence: { runId: string; taskId: string; split: string; passed: boolean; graphFallback: boolean; tokens: number; durationMs: number; modelRequests: number }[];
};
type Run = { id: string; taskId: string; split: string; status: string; metrics: { inputTokens: number; outputTokens: number; modelRequests: number; durationMs: number; toolErrors: number }; evaluation: { status: string }; evolution?: { usedVersionId?: string; generation?: number; maintenanceMs?: number; lookupMs?: number; extraModelRequests?: number; extraToolCalls?: number; shadowRollouts?: number; note?: string; maintenanceError?: string; tinyEdgeMaintenance?: { workflowStatus?: string; miningStatus?: string; reasonCode?: string; reason?: string } } };
type TinyEdge = { id: string; scenario: string; support: number; length: number; intent: string; inputSlots: string[]; outputSlots: string[]; sourceRunIds: string[]; sourceWorkflowIds: string[]; nodeTemplates: { tool: string }[] };
type ToolInertia = { toolPaths: { tools: string[]; support: number; sourceRunIds: string[] }[]; parameterEdges: { sourceTool: string; sourcePath: string[]; targetTool: string; targetParameter: string; support: number; sourceRunIds: string[] }[] };
type Task = { id: string; scenario: string; family: string; split: string; title: string };
const names: Record<string, string> = { finance: '财务运营 · Olist', support: '客服运营 · CFPB', tickets: '技术工单 · Zammad GitHub Issues' };
const states: Record<string, string> = { probation: '同类任务试用', 'family-supported': '适用证据已积累', 'needs-repair': '待修订' };
const patchNames: Record<string, string> = { compile_observed_graph: '保存轨迹图', rebuild_after_failure: '失败后重新编译', reuse_with_fallback: '字段复用 + 缺失补查', filter_then_enrich: '筛选后补查 Motif', defer_subgraph: '失败子图交接模型' };

export default function OnlineEvolutionPanel() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [data, setData] = useState<{ versions: Version[]; tinyEdges: TinyEdge[]; toolInertia?: ToolInertia; runs: Run[] }>({ versions: [], tinyEdges: [], runs: [] });
  const [scenario, setScenario] = useState('tickets');
  const [family, setFamily] = useState('');
  const [taskId, setTaskId] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let stopped = false; let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const [next, list] = await Promise.all([api<typeof data>('/api/taskbank/evolution'), api<Task[]>('/api/taskbank/tasks')]);
        if (!stopped) { setData({ ...next, tinyEdges: next.tinyEdges || [] }); setTasks(list); setError(''); }
      } catch (e) { if (!stopped) setError((e as Error).message); }
      if (!stopped) timer = setTimeout(poll, 2000);
    }
    void poll(); return () => { stopped = true; clearTimeout(timer); };
  }, []);
  const scoped = tasks.filter(t => t.scenario === scenario && (!family || t.family === family));
  const task = scoped.find(t => t.id === taskId) || scoped[0];
  const versions = data.versions.filter(v => v.scenario === scenario && (!family || v.family === family));
  const ids = new Set(scoped.map(t => t.id));
  const runs = data.runs.filter(r => ids.has(r.taskId));
  const maintenanceFailures = runs.filter(r => r.evolution?.maintenanceError || r.evolution?.tinyEdgeMaintenance?.miningStatus === 'failed');
  const parentName = (id: string | null) => { const v = data.versions.find(x => x.id === id); return v ? `G${v.generation} · ${v.id.slice(0, 6)}` : '冷启动'; };
  return <div className="online-evolution">
    <div className="page-heading"><h1>Graph RSI · 随任务进化</h1><GitBranch size={24} /></div>
    <p>公开真实历史记录上的自建任务。每次提交只执行一个正常任务；成功轨迹优化读取结构，失败与有效恢复轨迹生成后继版本。</p>
    <div className="taskbank-toolbar">
      <label>场景 <select value={scenario} onChange={e => { setScenario(e.target.value); setFamily(''); setTaskId(''); }}>{Object.entries(names).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label>
      <label>任务类型 <select value={family} onChange={e => { setFamily(e.target.value); setTaskId(''); }}><option value="">全部</option>{[...new Map(tasks.filter(t => t.scenario === scenario).map(t => [t.family, t.title])).entries()].map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label>
      <label>正常任务 <select value={task?.id || ''} onChange={e => setTaskId(e.target.value)}>{scoped.map(t => <option key={t.id} value={t.id}>{t.id} · {t.split}</option>)}</select></label>
    </div>
    {error && <p role="alert">{error}</p>}
    <div className="graph-facts"><div><span>结构版本</span><strong>{versions.length}</strong></div><div><span>正常任务执行</span><strong>{runs.length}</strong></div><div><span>额外影子 rollout</span><strong>{runs.reduce((n, r) => n + (r.evolution?.shadowRollouts || 0), 0)}</strong></div><div><span>图维护耗时总计</span><strong>{runs.reduce((n, r) => n + (r.evolution?.maintenanceMs || 0) + (r.evolution?.lookupMs || 0), 0).toFixed(2)} ms</strong></div></div>
    <p>进化维护额外 LLM {runs.reduce((n, r) => n + (r.evolution?.extraModelRequests || 0), 0)} 次 · 额外工具 {runs.reduce((n, r) => n + (r.evolution?.extraToolCalls || 0), 0)} 次。当前任务的恢复调用计入正常执行成本。</p>
    {maintenanceFailures.length > 0 && <div role="alert" className="taskbank-comparison"><strong>经验维护异常 {maintenanceFailures.length} 次</strong><p>任务即使完成也不会掩盖维护失败；请查看对应运行的原因和原始轨迹。</p><details><summary>维护失败明细</summary><pre>{JSON.stringify(maintenanceFailures.map(run => ({ taskId: run.taskId, runId: run.id, maintenanceError: run.evolution?.maintenanceError, tinyEdgeMaintenance: run.evolution?.tinyEdgeMaintenance })), null, 2)}</pre></details></div>}
    <p>训练集生成 Patch；验证集只累计适用证据；测试集使用已获支持的图且不更新经验。三个不同任务通过是应用门槛，不是统计显著性或成本优势证明。</p>
    {task && <TaskRunPanel taskId={task.id} defaultStrategy="graph_rsi" />}
    <h2>AutoTool 惯性经验</h2>
    <p>仅通过评分的模型来源 train 轨迹更新；Graph 与惯性执行不自我强化。运行时只绑定当前观察，具体接受/拒绝和成本在任务回放中展示。</p>
    {!data.toolInertia?.toolPaths.length && <p>尚无可用的模型来源串行工具路径。</p>}
    {data.toolInertia?.toolPaths.map(path => <section key={path.tools.join('→')} className="online-version"><h3>{path.tools.join(' → ')} · 支持 {path.support}</h3><p>来源运行 {path.sourceRunIds.map(id => id.slice(0, 8)).join(' · ')}</p></section>)}
    {data.toolInertia?.parameterEdges.length ? <details><summary>参数来源契约（不保存旧业务值）</summary><pre>{JSON.stringify(data.toolInertia.parameterEdges, null, 2)}</pre></details> : null}
    <h2>Persistent TinyEdge</h2>
    {!data.tinyEdges.filter(edge => edge.scenario === scenario).length && <p>尚无达到支持度门槛的可执行片段。仅通过评分的 train 图执行会增加支持度；验证和测试不会写入。</p>}
    {data.tinyEdges.filter(edge => edge.scenario === scenario).map(edge => <section key={edge.id} className="online-version"><h3>{edge.id.slice(0, 14)} · 支持 {edge.support} · {edge.length} 节点</h3><p>{edge.intent}</p><p>工具 {edge.nodeTemplates.map(node => node.tool).join(' → ')} · 输入槽 {edge.inputSlots.join(', ') || '无'} · 输出槽 {edge.outputSlots.join(', ') || '无'}</p><p>来源运行 {edge.sourceRunIds.map(id => id.slice(0, 8)).join(' · ')}；执行时只绑定当前任务参数。</p><details><summary>片段规范化身份与来源</summary><pre>{JSON.stringify(edge, null, 2)}</pre></details></section>)}
    <h2>版本关系与结构修改</h2>
    {!versions.length && <p>尚无版本。提交训练任务后，系统从实际成功轨迹保存读取图；结构不变时只累计证据。</p>}
    {versions.map(v => <section key={v.id} className="online-version">
      <h3>{parentName(v.parentGraphId)} → G{v.generation} · {v.id.slice(0, 6)} <span>{states[v.status] || v.status}</span></h3>
      <p>{v.family} · {v.scope}</p>
      <p>来源任务 {v.sourceTaskId} · <a href={`/api/taskbank/runs/${v.sourceRunId}`} target="_blank" rel="noreferrer">查看来源轨迹</a></p>
      {v.patches.map((p, i) => <p key={i}><strong>{patchNames[p.operation] || p.operation}</strong> {p.nodeId || ''}{p.fields ? ` [${p.fields.join(', ')}]` : ''}{p.condition ? ` · ${p.condition.field}=${String(p.condition.value)}` : ''}：{p.reason}</p>)}
      <div className="online-nodes">{v.nodes.map(n => <div key={n.id}><strong>{n.tool}</strong><small>{n.dependencies.length ? `依赖 ${n.dependencies.join(', ')}` : '入口'}</small><span>{n.defer ? '交接模型' : n.foreach?.filter ? `筛选 ${n.foreach.filter.field}=${String(n.foreach.filter.value)} 后补查` : n.reuse ? `复用 ${n.reuse.fields.join(', ')}${n.reuse.onMissing ? ' · 缺失时补查' : ''}` : '调用工具'}</span></div>)}</div>
      <p>正常任务证据 {v.evidence.length} 次 · 评分通过 {v.evidence.filter(e => e.passed).length} 次 · 图交接恢复 {v.evidence.filter(e => e.graphFallback).length} 次</p>
      <details><summary>完整图与验证证据</summary><pre>{JSON.stringify(v, null, 2)}</pre></details>
    </section>)}
    <h2>运行成本与结果</h2>
    <p>总 token 和延迟包含当前任务恢复成本；图维护耗时另列并计入总延迟。下表是自然任务记录，不是相同任务的因果对照。</p>
    <div className="reliability-table"><table><thead><tr><th>任务 / 运行</th><th>使用图</th><th>评分</th><th>LLM</th><th>Token</th><th>总延迟 ms</th><th>图维护</th><th>工具错误</th></tr></thead><tbody>{runs.map(r => <tr key={r.id}><td><a href={`/api/taskbank/runs/${r.id}`} target="_blank" rel="noreferrer">{r.taskId} · {r.id.slice(0, 6)}</a></td><td>{r.evolution?.usedVersionId ? `G${r.evolution.generation} · ${r.evolution.usedVersionId.slice(0, 6)}` : '冷启动'}</td><td>{r.evaluation.status}</td><td>{r.metrics.modelRequests}</td><td>{r.metrics.inputTokens + r.metrics.outputTokens}</td><td>{r.metrics.durationMs}</td><td>{r.evolution?.maintenanceError || r.evolution?.tinyEdgeMaintenance?.miningStatus === 'failed' ? `失败：${r.evolution?.tinyEdgeMaintenance?.reasonCode || r.evolution?.maintenanceError}` : `${((r.evolution?.lookupMs || 0) + (r.evolution?.maintenanceMs || 0)).toFixed(2)} ms`}</td><td>{r.metrics.toolErrors}</td></tr>)}</tbody></table></div>
  </div>;
}
