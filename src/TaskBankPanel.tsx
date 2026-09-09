import { useEffect, useState } from 'react';
import { Database, Play, RefreshCw, ArrowDownToLine } from 'lucide-react';
import { api } from './api';
import type { ToolCard } from '../shared/types';

type Scenario = 'finance' | 'support' | 'tickets';
type Task = { id: string; scenario: Scenario; family: string; title: string; split: string; task: string; recordIds: string[]; recordCount: number; asOf: string; sourceUrl: string; acceptance: { metricKeys: string[]; selectedIdsOrderMatters: boolean; prose: string } };
type Manifest = { manifest: { taskCount: number; scenarios: Record<Scenario, { provider: string; tasks: number; selectedRecords: number; note: string }> } | null; ready: boolean };
const names = { finance: '财务运营', support: '客户投诉运营', tickets: '技术工单' };
const splits: Record<string, string> = { train: '训练', validation: '验证', test: '测试' };

export default function TaskBankPanel() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [scenario, setScenario] = useState<Scenario>('finance');
  const [family, setFamily] = useState('');
  const [split, setSplit] = useState('');
  const [selected, setSelected] = useState('');
  const [tools, setTools] = useState<ToolCard[]>([]);
  const [toolName, setToolName] = useState('');
  const [args, setArgs] = useState('{}');
  const [session, setSession] = useState('');
  const [output, setOutput] = useState<unknown>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { let closed = false; Promise.all([api<Manifest>('/api/taskbank/manifest'), api<Task[]>('/api/taskbank/tasks')]).then(([m, t]) => { if (!closed) { setManifest(m); setTasks(t); } }).catch(e => { if (!closed) setError(e.message); }); return () => { closed = true; }; }, []);
  const scoped = tasks.filter(t => t.scenario === scenario);
  const filtered = scoped.filter(t => (!family || t.family === family) && (!split || t.split === split));
  const task = filtered.find(t => t.id === selected) || filtered[0];
  useEffect(() => {
    setSession(''); setOutput(null); setTools([]); setToolName(''); setArgs('{}');
    let cancelled = false;
    if (task && manifest?.ready) api<ToolCard[]>(`/api/taskbank/tasks/${task.id}/tools`).then(v => { if (!cancelled) { setTools(v); setToolName(v[0]?.name || ''); setArgs(JSON.stringify({ page: 1, pageSize: 10 }, null, 2)); } }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [task?.id, manifest?.ready]);
  const tool = tools.find(t => t.name === toolName);
  async function invoke() {
    if (!task || !tool) return;
    setBusy(true); setError('');
    try {
      const parameters = JSON.parse(args);
      let key = session;
      if (!key) { const result = await api<{ id: string }>('/api/taskbank/sessions', { method: 'POST', body: JSON.stringify({ taskId: task.id }) }); key = result.id; setSession(key); }
      setOutput(await api(`/api/taskbank/sessions/${key}/call`, { method: 'POST', body: JSON.stringify({ tool: tool.name, arguments: parameters }) }));
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  function chooseTool(name: string) {
    setToolName(name);
    const parameter = scenario === 'finance' ? 'orderId' : scenario === 'support' ? 'complaintId' : 'issueId';
    const candidate = tools.find(t => t.name === name);
    const props = candidate?.parameters.properties as Record<string, unknown> | undefined;
    setArgs(JSON.stringify(props?.page ? { page: 1, pageSize: 10 } : props?.[parameter] ? { [parameter]: task?.recordIds[0] } : props?.values ? { values: [] } : props?.direction ? { records: [], direction: 'desc', limit: 3 } : {}, null, 2));
  }
  return <div className="taskbank-workspace">
    <div className="page-heading"><h1>真实数据任务库</h1><span><Database size={18} /> {manifest?.manifest?.taskCount || 0} 个任务</span></div>
    <div className="taskbank-toolbar"><div className="segmented">{(Object.keys(names) as Scenario[]).map(key => <button disabled={busy} className={scenario === key ? 'selected' : ''} key={key} onClick={() => { setScenario(key); setFamily(''); setSplit(''); setSelected(''); }}>{names[key]} · {tasks.filter(t => t.scenario === key).length}</button>)}</div>
      <label>任务类型 <select disabled={busy} value={family} onChange={e => setFamily(e.target.value)}><option value="">全部类型</option>{[...new Map(scoped.map(t => [t.family, t.title])).entries()].map(([f, title]) => <option key={f} value={f}>{title}</option>)}</select></label>
      <label>数据划分 <select disabled={busy} value={split} onChange={e => setSplit(e.target.value)}><option value="">全部</option>{Object.entries(splits).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <a className="text-button" href={`/api/taskbank/tasks?scenario=${scenario}`}><ArrowDownToLine size={14} />导出任务</a>
    </div>
    <p>{manifest?.manifest?.scenarios[scenario].provider} · {manifest?.manifest?.scenarios[scenario].selectedRecords} 条来源记录 · 60 训练 / 20 验证 / 20 测试</p>
    <p>{manifest?.manifest?.scenarios[scenario].note}</p>
    {!manifest?.ready && <p>数据未安装：运行 npm run taskbank:build 恢复冻结来源记录。</p>}
    {error && <p role="alert" className="error-banner">{error}</p>}
    <div className="taskbank-layout">
      <div className="taskbank-list" role="navigation" aria-label="任务列表">{filtered.map(t => <button disabled={busy} key={t.id} className={t.id === task?.id ? 'selected' : ''} onClick={() => setSelected(t.id)}><strong>{t.title}</strong><small>{t.id} · {splits[t.split]}</small></button>)}</div>
      <div className="taskbank-detail">{task && <>
        <h2>{task.id}</h2><p>{task.task}</p>
        <p>评分：结构化事实与证据匹配；报告文字未评分。工具调试不调用 LLM。</p>
        <details><summary>来源记录与验收字段</summary><pre>{JSON.stringify({ source: task.sourceUrl, recordIds: task.recordIds, acceptance: task.acceptance }, null, 2)}</pre></details>
        <h2>工具接口 · {tools.length} 个</h2>
        <label>工具 <select disabled={busy} value={toolName} onChange={e => chooseTool(e.target.value)}>{tools.map(t => <option key={t.name}>{t.name}</option>)}</select></label>
        <p>{tool?.description}</p><details><summary>JSON Schema</summary><pre>{JSON.stringify(tool?.parameters, null, 2)}</pre></details>
        <label>调用参数<textarea aria-label="任务工具调用参数" disabled={busy} value={args} onChange={e => setArgs(e.target.value)} /></label>
        <div className="taskbank-toolbar"><button className="button primary" disabled={busy || !tool} onClick={() => void invoke()}><Play size={15} />调用工具</button><button className="button secondary" disabled={busy || !session} onClick={() => { setSession(''); setOutput(null); }}><RefreshCw size={15} />新会话</button></div>
        {output !== null && <pre aria-label="工具返回结果">{JSON.stringify(output, null, 2)}</pre>}
      </>}</div>
    </div>
  </div>;
}
