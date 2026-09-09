import { useEffect, useState } from 'react';
import { Play, Square, Activity, ArrowDownToLine } from 'lucide-react';
import { api } from './api';
import type { RunMetrics, Scenario } from '../shared/types';

type Counter = { attempts: number; errors: number };
type Totals = { runs: number; statePassed: number; runsWithToolErrors: number; modelRequests: number; toolCalls: number; toolErrors: number; guardHits: number; graphFallbacks?: number; interruptedRuns?: number; tokens: number; usageComplete: boolean; counters: Record<string, Counter> };
type Row = { round: number; snapshot: string; arm: string; runId: string; status: string; statePassed: boolean; metrics: RunMetrics; terminalError?: string; errors: { eventSeq: number; tool: string; error: string }[] };
type Experiment = { id: string; createdAt: string; status: string; phase: string; model: string; scenario: string; maxRounds: number; arms: string[]; rows: Row[]; totals: Record<string, Totals>; graph: { id: string }; negativeMotifs: { id: string }[] };
const names: Record<string, string> = { react: 'ReAct', graph: 'Graph', graph_negative: 'Graph + 负 motif' };
const colors: Record<string, string> = { react: '#c14c4c', graph: '#2979b8', graph_negative: '#22816b' };
const statuses: Record<string, string> = { running: '执行中', completed: '已结束', failed: '失败', cancelled: '已取消', interrupted: '已中断' };
const ratio = (n: number, total: number) => total ? `${n}/${total} · ${(100 * n / total).toFixed(1)}%` : '待执行';

function ErrorCurve({ item }: { item: Experiment }) {
  const series = item.arms.map(arm => {
    let sum = 0;
    const points = [0, ...item.rows.filter(r => r.arm === arm).map(r => sum += r.metrics.toolErrors)];
    return { arm, points };
  });
  const max = Math.max(1, ...series.flatMap(s => s.points));
  const x = (i: number) => 60 + 730 * i / item.maxRounds;
  const y = (v: number) => 200 - 155 * v / max;
  return <figure className="reliability-curve"><figcaption>累计工具错误（含修复前错误与前置拒绝）</figcaption>
    <svg role="img" aria-label="各策略累计工具错误随任务次数变化" viewBox="0 0 840 250">
      {[...new Set([0, Math.ceil(max / 2), max])].map(v => <g key={v}><line x1="60" x2="790" y1={y(v)} y2={y(v)} stroke="#e1e5e9" /><text x="45" y={y(v) + 4} textAnchor="end" fontSize="12">{v}</text></g>)}
      {Array.from({ length: Math.min(item.maxRounds, 10) + 1 }, (_, i) => Math.round(i * item.maxRounds / Math.min(item.maxRounds, 10))).map(i => <text key={i} x={x(i)} y="222" textAnchor="middle" fontSize="12">{i}</text>)}
      {series.map(s => <g key={s.arm}><polyline points={s.points.map((v, i) => `${x(i)},${y(v)}`).join(' ')} fill="none" stroke={colors[s.arm]} strokeWidth="2.5" strokeDasharray={s.arm === 'graph_negative' ? '8 5' : s.arm === 'graph' ? '3 3' : undefined} />{s.points.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r="3" fill={colors[s.arm]} />)}</g>)}
      <text x="420" y="245" textAnchor="middle" fontSize="12">每组已执行任务数</text>
    </svg>
    <div className="reliability-legend">{item.arms.map(arm => <span key={arm}><i style={{ background: colors[arm] }} />{names[arm]} · {item.totals[arm].toolErrors} 次错误</span>)}</div>
  </figure>;
}

export default function ReliabilityPanel() {
  const [items, setItems] = useState<Experiment[]>([]);
  const [selected, setSelected] = useState('');
  const [scenario, setScenario] = useState<Scenario>('finance');
  const [rounds, setRounds] = useState(3);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { const value = await api<Experiment[]>('/api/reliability'); if (!stopped) setItems(value); }
      catch (e) { if (!stopped) setError((e as Error).message); }
      if (!stopped) timer = setTimeout(poll, 2000);
    }
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, []);
  const item = items.find(x => x.id === selected) || items[0];
  const busy = pending || items.some(x => x.status === 'running');
  async function start() {
    setPending(true); setError('');
    try {
      const value = await api<Experiment>('/api/reliability', { method: 'POST', body: JSON.stringify({ scenario, rounds }) });
      setSelected(value.id); setItems(old => [value, ...old]);
    } catch (e) { setError((e as Error).message); } finally { setPending(false); }
  }
  return <div className="reliability-workspace">
    <div className="page-heading"><h1>长程稳定性对照</h1><Activity size={24} /></div>
    <div className="reliability-controls">
      <label>岗位 <select disabled={busy} value={scenario} onChange={e => setScenario(e.target.value as Scenario)}><option value="finance">财务 · 三组对照</option><option value="support">客服 · 两组对照</option></select></label>
      <label>轮数 <input aria-label="稳定性实验轮数" type="number" min={1} max={30} value={rounds} disabled={busy} onChange={e => setRounds(Math.max(1, Math.min(30, Number(e.target.value) || 1)))} /></label>
      <span>{rounds * (scenario === 'finance' ? 3 : 2)} 次完整任务</span>
      <button className="button primary" disabled={busy} onClick={() => void start()}><Play size={16} />开始对照</button>
      {item?.status === 'running' && <button className="button" onClick={() => { void api(`/api/reliability/${item.id}/cancel`, { method: 'POST', body: '{}' }).catch(e => setError(e.message)); }}><Square size={16} />停止实验</button>}
    </div>
    {error && <p role="alert" className="error-banner">{error}</p>}
    <label>实验记录 <select value={item?.id || ''} onChange={e => setSelected(e.target.value)}><option value="" disabled>暂无记录</option>{items.map(x => <option key={x.id} value={x.id}>{x.scenario} · {x.id.slice(0, 8)} · {statuses[x.status]}</option>)}</select></label>
    {item && <>
      <div className="reliability-status"><strong>{item.phase}</strong><span>{item.rows.length}/{item.maxRounds * item.arms.length} 次已结束 · {item.model}</span><a className="text-button" href={`/api/reliability/${item.id}/export`}><ArrowDownToLine size={15} />导出证据</a></div>
      <p>合成快照 · 批量调用已开启 · 基础模型与经验冻结 · 顺序轮换 · 报告文字未评分</p>
      <ErrorCurve item={item} />
      <div className="reliability-table"><table><thead><tr><th>逐次累计指标</th>{item.arms.map(arm => <th key={arm}>{names[arm]}</th>)}</tr></thead><tbody>
        <tr><td>有工具错误的任务</td>{item.arms.map(arm => { const t = item.totals[arm]; return <td key={arm}>{ratio(t.runsWithToolErrors, t.runs)}</td>; })}</tr>
        <tr><td>最终业务状态未通过 / 未完成</td>{item.arms.map(arm => { const t = item.totals[arm]; return <td key={arm}>{ratio(t.runs - t.statePassed, t.runs)}</td>; })}</tr>
        <tr><td>其中执行中断 / 服务错误</td>{item.arms.map(arm => <td key={arm}>{item.totals[arm].interruptedRuns ?? '待核对'}</td>)}</tr>
        <tr><td>全部工具错误 / 尝试次数</td>{item.arms.map(arm => { const t = item.totals[arm]; return <td key={arm}>{ratio(t.toolErrors, t.toolCalls)}</td>; })}</tr>
        {(['graph', 'model', 'read'] as const).map(key => <tr key={key}><td>{{ graph: '图执行错误 / 调用', model: '模型决策调用错误 / 调用', read: '所有读取错误 / 调用' }[key]}</td>{item.arms.map(arm => { const c = item.totals[arm].counters[key]; return <td key={arm}>{c.attempts ? `${c.errors}/${c.attempts}` : '—'}</td>; })}</tr>)}
        <tr><td>LLM 请求合计</td>{item.arms.map(arm => <td key={arm}>{item.totals[arm].modelRequests}</td>)}</tr>
        <tr><td>图执行回退次数</td>{item.arms.map(arm => <td key={arm}>{arm === 'react' ? '—' : item.totals[arm].graphFallbacks ?? '待核对'}</td>)}</tr>
        <tr><td>已记录 token</td>{item.arms.map(arm => <td key={arm}>{item.totals[arm].tokens.toLocaleString()}{!item.totals[arm].usageComplete && '（不完整）'}</td>)}</tr>
        <tr><td>负 motif 前置拒绝（已计入错误）</td>{item.arms.map(arm => <td key={arm}>{item.totals[arm].guardHits}</td>)}</tr>
      </tbody></table></div>
      <p>当前样本零错误不等于理论零错误。图执行确定性仅限固定工具契约、有效参数及可用环境。来源学习成本在导出经验元数据中另列。</p>
      <h2>逐次证据</h2>
      <div className="reliability-table"><table><thead><tr><th>轮次 / 快照</th><th>策略</th><th>工具错误</th><th>业务状态</th><th>LLM</th><th>轨迹</th></tr></thead><tbody>{item.rows.map(r => <tr key={r.runId}><td>{r.round} · {r.snapshot}</td><td>{names[r.arm]}</td><td>{r.metrics.toolErrors}</td><td>{r.statePassed ? '通过' : '未通过 / 未完成'}</td><td>{r.metrics.modelRequests}</td><td><a href={`/api/runs/${r.runId}/export/json`}>{r.runId.slice(0, 8)}</a>{(r.errors.length > 0 || r.terminalError) && <details><summary>错误明细</summary>{r.terminalError && <p>{r.terminalError}</p>}{r.errors.map(e => <p key={e.eventSeq}>{e.tool} · {e.error}</p>)}</details>}</td></tr>)}</tbody></table></div>
    </>}
  </div>;
}
