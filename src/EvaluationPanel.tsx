import { useEffect, useState } from 'react';
import { BarChart3, Play, Square } from 'lucide-react';
import { api } from './api';
import './evaluation.css';

type Arm = { attempts: number; passed: number; successRate: number | null; totalTokens: number; inputTokens: number; outputTokens: number; usageComplete: boolean; tokensPerSuccess: number | null; modelRequests: number; toolCalls: number; toolErrors: number; meanLatencyMs: number | null; p50Ms: number | null; p95Ms: number | null; limited: number; graphFallbacks: number; warmRuns: number; coldRuns: number };
type Summary = { arms: Record<string, Arm>; bothPassed: number; qualityRegressions: number; qualityImprovements: number; allOutcomeTokenReduction: number | null; bothPassedTokenDifference: number; note: string };
type Run = { id: string; status: string; evaluation: { status: string; issues?: string[] }; metrics: { inputTokens: number; outputTokens: number; modelRequests: number; toolCalls: number; durationMs: number; toolErrors: number; usageComplete: boolean }; evolution?: { usedVersionId?: string }; fallback?: string; error?: string };
type Pair = { index: number; taskId: string; scenario: string; family: string; repeat: number; status: string; runs: Record<string, Run>; runIds: Record<string, string> };
type Experiment = { id: string; status: string; split: string; createdAt: string; historicalSetupTokens: number; protocol: { repeats: number; observedGraphCoverage: number; planner: string; executor: string; sourceHash: string; graphHash: string }; summary: Summary; byScenario: Record<string, Summary>; pairs?: Pair[] };
const fmt = (n?: number | null) => n == null ? '—' : Math.round(n).toLocaleString();
const seconds = (n?: number | null) => n == null ? '—' : (n / 1000).toFixed(1) + ' s';
const names: Record<string, string> = { finance: '财务', support: '客服', tickets: '技术工单' };
const status: Record<string, string> = { running: '评测进行中', completed: '评测结束', failed: '评测失败', cancelled: '已取消', interrupted: '已中断' };
function Aggregate({ summary }: { summary: Summary }) {
  const a = summary.arms.strong_react, b = summary.arms.graph_rsi;
  return <div className="eval-overflow"><table className="eval-table"><thead><tr><th>指标 · 包含失败成本</th><th>Strong ReAct</th><th>Graph RSI</th></tr></thead><tbody>
    <tr><td>成功 / 已结束任务</td><td>{a.passed} / {a.attempts}</td><td>{b.passed} / {b.attempts}</td></tr>
    <tr><td>总 token</td><td>{fmt(a.totalTokens)}{!a.usageComplete && '（不完整）'}</td><td>{fmt(b.totalTokens)}{!b.usageComplete && '（不完整）'}</td></tr>
    <tr><td>输入 / 输出 token</td><td>{fmt(a.inputTokens)} / {fmt(a.outputTokens)}</td><td>{fmt(b.inputTokens)} / {fmt(b.outputTokens)}</td></tr>
    <tr><td>每成功任务分摊 token</td><td>{fmt(a.tokensPerSuccess)}</td><td>{fmt(b.tokensPerSuccess)}</td></tr>
    <tr><td>模型 / 工具调用</td><td>{a.modelRequests} / {a.toolCalls}</td><td>{b.modelRequests} / {b.toolCalls}</td></tr>
    <tr><td>平均执行延迟</td><td>{seconds(a.meanLatencyMs)}</td><td>{seconds(b.meanLatencyMs)}</td></tr>
    <tr><td>P50 / P95 延迟</td><td>{seconds(a.p50Ms)} / {seconds(a.p95Ms)}</td><td>{seconds(b.p50Ms)} / {seconds(b.p95Ms)}</td></tr>
    <tr><td>工具错误 / 超预算任务</td><td>{a.toolErrors} / {a.limited}</td><td>{b.toolErrors} / {b.limited}</td></tr>
    <tr><td>图命中 / 冷启动 / 回退</td><td>—</td><td>{b.warmRuns} / {b.coldRuns} / {b.graphFallbacks}</td></tr>
  </tbody></table></div>;
}
function Review({ runId }: { runId: string }) {
  const [scores, setScores] = useState(['', '', '']);
  const [note, setNote] = useState('');
  const [message, setMessage] = useState('');
  async function save() {
    try { await api(`/api/taskbank/runs/${runId}/review`, { method: 'POST', body: JSON.stringify({ factualConsistency: Number(scores[0]), requirementCoverage: Number(scores[1]), readability: Number(scores[2]), note }) }); setMessage('人工复核已保存；不覆盖原结构化评分。'); }
    catch (e) { setMessage((e as Error).message); }
  }
  return <details className="eval-review"><summary>人工复核报告文字</summary><p>先打开业务报告。0=不满足，1=部分满足，2=满足；此表不是自动评分。</p>{['事实一致性', '需求覆盖', '可读性'].map((title, i) => <label key={title}>{title}<select value={scores[i]} onChange={e => setScores(old => old.map((v, k) => k === i ? e.target.value : v))}><option value="">未评</option>{[0, 1, 2].map(n => <option key={n} value={n}>{n}</option>)}</select></label>)}<textarea aria-label="人工复核依据" value={note} onChange={e => setNote(e.target.value)} placeholder="记录错误或评分依据" /><button className="button secondary" disabled={scores.includes('')} onClick={() => void save()}>保存复核</button><p>{message}</p></details>;
}
export default function EvaluationPanel() {
  const [items, setItems] = useState<Experiment[]>([]);
  const [selected, setSelected] = useState('');
  const [item, setItem] = useState<Experiment | null>(null);
  const [split, setSplit] = useState('validation');
  const [repeats, setRepeats] = useState(1);
  const [filter, setFilter] = useState('all');
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [pending, setPending] = useState(false);
  useEffect(() => {
    let closed = false; let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const list = await api<Experiment[]>('/api/evaluations');
        const key = selected || list[0]?.id;
        const detail = key ? await api<Experiment>('/api/evaluations/' + key) : null;
        if (!closed) { setItems(list); setItem(detail); setLoadError(''); }
      } catch (e) { if (!closed) setLoadError((e as Error).message); }
      if (!closed) timer = setTimeout(poll, 2000);
    }
    void poll(); return () => { closed = true; clearTimeout(timer); };
  }, [selected]);
  const busy = pending || items.some(x => x.status === 'running');
  async function start() {
    setPending(true); setError('');
    try { const r = await api<{ id: string }>('/api/evaluations', { method: 'POST', body: JSON.stringify({ split, repeats }) }); setSelected(r.id); }
    catch (e) { setError((e as Error).message); } finally { setPending(false); }
  }
  const summary = item ? filter === 'all' ? item.summary : item.byScenario[filter] : null;
  const pairs = item?.pairs?.filter(p => filter === 'all' || p.scenario === filter) || [];
  const completed = item?.pairs?.filter(p => p.status === 'completed').length || 0;
  return <div className="evaluation-page">
    <div className="page-heading"><div><div className="eyebrow">导师目标 / 质量 · 效率 · 可靠性</div><h1>成对评测与业务成果</h1><p>先固定任务和图版本，再比较相同质量下的实际消耗。</p></div><BarChart3 size={26} /></div>
    <div className="eval-controls"><label>数据划分<select value={split} disabled={busy} onChange={e => setSplit(e.target.value)}><option value="validation">验证集 · 30 个任务</option><option value="test">测试集 · 30 个任务</option></select></label><label>重复次数<select value={repeats} disabled={busy} onChange={e => setRepeats(Number(e.target.value))}>{[1, 2, 3].map(n => <option key={n} value={n}>{n} 次</option>)}</select></label><button className="button primary" disabled={busy} onClick={() => void start()}><Play size={15} />开始冻结评测</button>{item?.status === 'running' && <button className="button secondary" onClick={() => void api('/api/evaluations/' + item.id + '/cancel', { method: 'POST', body: '{}' }).catch(e => setError(e.message))}><Square size={14} />停止评测</button>}</div>
    <p>Strong ReAct 与 RSI 共用防重复、观察复用、批量调用提示。每场景覆盖 10 种任务类型；评测期间不更新图，不根据结果替换任务。</p>
    {(error || loadError) && <p role="alert" className="eval-error">{error || loadError}</p>}
    <label>评测记录<select value={item?.id || ''} onChange={e => setSelected(e.target.value)}><option value="" disabled>暂无评测</option>{items.map(x => <option key={x.id} value={x.id}>{x.id.slice(0, 8)} · {x.split} · {status[x.status]}</option>)}</select></label>
    {item && summary && <>
      <div className="eval-progress"><strong>{status[item.status]} · {completed} / {item.pairs?.length || 0} 对</strong><progress value={completed} max={item.pairs?.length || 1} /><span>模型 {item.protocol.executor}</span></div>
      <div className="eval-cards"><article><small>冻结时的图覆盖</small><strong>{item.protocol.observedGraphCoverage} / 30</strong><p>未命中按冷启动执行</p></article><article><small>RSI 成功 / 已结束任务</small><strong>{summary.arms.graph_rsi.passed} / {summary.arms.graph_rsi.attempts}</strong><p>对照成功而 RSI 失败 {summary.qualityRegressions} 对</p></article><article><small>全部尝试 token 差异</small><strong>{summary.allOutcomeTokenReduction == null ? '—' : `${summary.allOutcomeTokenReduction >= 0 ? '减少' : '增加'} ${Math.abs(summary.allOutcomeTokenReduction * 100).toFixed(1)}%`}</strong><p>{item.status === 'running' ? '当前累计，不是最终结论' : '需结合成功率判断'}</p></article></div>
      <div className="eval-controls"><label>场景<select value={filter} onChange={e => setFilter(e.target.value)}><option value="all">全部场景</option>{Object.entries(names).map(([k, n]) => <option key={k} value={k}>{n}</option>)}</select></label><a href={`/api/evaluations/${item.id}`} target="_blank" rel="noreferrer">完整协议与结果 JSON ↗</a></div>
      <Aggregate summary={summary} />
      <p className="eval-boundary">{summary.note} 已追溯的历史图来源任务另耗 {fmt(item.historicalSetupTokens)} token，此处不冒充完整研发成本。当前只读分析任务不代表已经完成企业写入流程。</p>
      <details><summary>冻结协议与审计指纹</summary><pre>{JSON.stringify(item.protocol, null, 2)}</pre></details>
      <h2>逐任务证据 · 包含未通过结果</h2>
      <div className="eval-pairs">{pairs.map(p => <section key={p.index}><header><strong>{p.taskId}</strong><span>第 {p.repeat} 次 · {p.status}</span></header><div className="eval-pair-arms">{['strong_react', 'graph_rsi'].map(arm => { const r = p.runs[arm], id = p.runIds[arm]; return <div key={arm}><b>{arm === 'strong_react' ? 'Strong ReAct' : 'Graph RSI'}</b>{r ? <><span className={r.evaluation.status === 'passed' ? 'eval-pass' : 'eval-fail'}>{r.status} · {r.evaluation.status}</span><p>{fmt(r.metrics.inputTokens + r.metrics.outputTokens)} token · {r.metrics.modelRequests} LLM · {seconds(r.metrics.durationMs)}</p>{r.evaluation.issues?.length ? <p className="eval-fail">{r.evaluation.issues.join(' · ')}</p> : null}{r.fallback && <p>图回退：{r.fallback}</p>}{r.error && <p className="eval-fail">{r.error}</p>}<a href={`/api/taskbank/runs/${id}/report`} target="_blank" rel="noreferrer">打开业务报告与逐条证据 ↗</a><Review runId={id} /></> : <p>{id ? '执行中，可查看实时轨迹' : '等待调度'}</p>}</div>; })}</div>{p.runIds.strong_react && p.runIds.graph_rsi && <a className="eval-replay" href={`/?taskId=${p.taskId}&a=strong_react&b=graph_rsi&left=${p.runIds.strong_react}&right=${p.runIds.graph_rsi}#demo`} target="_blank" rel="noreferrer">并排查看这组执行轨迹 →</a>}</section>)}</div>
    </>}
  </div>;
}
