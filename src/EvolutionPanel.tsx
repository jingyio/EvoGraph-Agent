import { useEffect, useState } from 'react';
import { Play, Square, GitBranch, ExternalLink } from 'lucide-react';
import { api } from './api';
import type { Scenario, TaskGraph, RunMetrics } from '../shared/types';

type Generation = { generation: number; parentGraphId: string | null; status: string; reason?: string; sourceRunId?: string; candidate?: TaskGraph; baselineRunId?: string; candidateRunId?: string; baselineMetrics?: RunMetrics; candidateMetrics?: RunMetrics };
type Experiment = { id: string; scenario: Scenario; status: string; phase: string; totalModelRequests: number; totalTokens: number; rounds: Generation[] };
const labels: Record<string, string> = { learning: '候选生成中', promoted: '暂定晋升', rejected: '拒绝晋升', stagnated: '结构停滞', completed: '已结束', running: '运行中', failed: '失败', cancelled: '已取消', interrupted: '已中断' };

export default function EvolutionPanel() {
  const [items, setItems] = useState<Experiment[]>([]);
  const [selected, setSelected] = useState('');
  const [scenario, setScenario] = useState<Scenario>('support');
  const [rounds, setRounds] = useState(3);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { const result = await api<Experiment[]>('/api/evolutions'); if (!stopped) setItems(result); }
      catch (e) { if (!stopped) setError((e as Error).message); }
      if (!stopped) timer = setTimeout(poll, 1500);
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, []);
  const item = items.find(x => x.id === selected) || items[0];
  const busy = pending || items.some(x => x.status === 'running');
  async function start() {
    setPending(true); setError('');
    try {
      const result = await api<Experiment>('/api/evolutions', { method: 'POST', body: JSON.stringify({ scenario, rounds }) });
      setItems(old => [result, ...old]); setSelected(result.id);
    } catch (e) { setError((e as Error).message); } finally { setPending(false); }
  }
  return <>
    <div className="page-heading"><h1>递归进化实验</h1><GitBranch size={24} /></div>
    <div className="graph-guidance">合成沙箱 · 读取图进化 · 完整业务状态门槛 · 报告语义未评分</div>
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', margin: '20px 0' }}>
      <label>岗位 <select value={scenario} disabled={busy} onChange={e => setScenario(e.target.value as Scenario)}><option value="support">客服工单处理</option><option value="finance">财务运营</option></select></label>
      <label>最大轮数 <input aria-label="最大进化轮数" type="number" min={1} max={5} value={rounds} disabled={busy} onChange={e => setRounds(Math.max(1, Math.min(5, Number(e.target.value) || 1)))} style={{ width: 60 }} /></label>
      <button className="button primary" disabled={busy} onClick={() => void start()}><Play size={16} />开始实验</button>
      {item?.status === 'running' && <button className="button" onClick={() => { void api(`/api/evolutions/${item.id}/cancel`, { method: 'POST', body: '{}' }).catch(e => setError(e.message)); }}><Square size={16} />停止</button>}
    </div>
    {error && <p role="alert">{error}</p>}
    <label>实验记录 <select value={item?.id || ''} onChange={e => setSelected(e.target.value)}><option value="" disabled>暂无实验</option>{items.map(x => <option key={x.id} value={x.id}>{x.scenario} · {x.id.slice(0, 8)} · {labels[x.status]}</option>)}</select></label>
    {item && <>
      <div className="graph-facts"><div><span>当前阶段</span><strong>{item.phase}</strong></div><div><span>全实验 LLM 请求</span><strong>{item.totalModelRequests}</strong></div><div><span>已记录 token（含训练和验证）</span><strong>{item.totalTokens}</strong></div></div>
      {item.rounds.map(row => <section key={row.generation} style={{ borderTop: '1px solid #d5d9df', padding: '20px 0' }}>
        <h2>第 {row.generation} 轮 · {labels[row.status]}</h2>
        <p>父版本 {row.parentGraphId?.slice(0, 8) || 'ReAct 冷启动'} → 候选 {row.candidate?.id.slice(0, 8) || '待生成'}</p>
        <p>{row.reason}</p>
        {row.candidate && <p>候选结构：{row.candidate.nodes.map(n => n.tool + (n.foreach ? '（遍历）' : '')).join(' → ')} · 影子读取 {row.candidate.validation.toolCalls} 次</p>}
        {row.baselineMetrics && row.candidateMetrics && <table style={{ width: '100%' }}><thead><tr><th>验证指标</th><th>父版本</th><th>候选版本</th></tr></thead><tbody>{(['modelRequests', 'toolCalls', 'toolErrors', 'inputTokens', 'outputTokens'] as const).map(key => <tr key={key}><td>{key}</td><td>{row.baselineMetrics![key]}</td><td>{row.candidateMetrics![key]}</td></tr>)}</tbody></table>}
        <div style={{ display: 'flex', gap: 20 }}>{[[row.sourceRunId, '来源轨迹'], [row.baselineRunId, '父版本验证'], [row.candidateRunId, '候选验证']].map(([id, label]) => id && <a key={id} href={`/api/runs/${id}/export/json`} className="text-button"><ExternalLink size={14} />{label}</a>)}</div>
      </section>)}
    </>}
  </>;
}
