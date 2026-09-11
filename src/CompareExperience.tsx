import { ArrowUpRight, Check, ChevronDown, ExternalLink, Minus } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { SHOWCASE_EXPERIMENT, Showcase, ShowcasePair, number, percent, total, duration } from './showcase';
import './showcase.css';

function Curve({ points }: { points: { baselineCumulativeTokens: number; rsiCumulativeTokens: number; position: number }[] }) {
  const width = 680, height = 210, left = 20, right = 660, top = 20, bottom = 176;
  const max = Math.max(1, ...points.flatMap(point => [point.baselineCumulativeTokens, point.rsiCumulativeTokens]));
  const x = (index: number) => left + (right - left) * index / Math.max(1, points.length - 1);
  const y = (value: number) => bottom - (bottom - top) * value / max;
  const path = (key: 'baselineCumulativeTokens' | 'rsiCumulativeTokens') => points.map((point, index) => `${index ? 'L' : 'M'}${x(index)},${y(point[key])}`).join(' ');
  const area = `${points.map((point, index) => `${x(index)},${y(point.baselineCumulativeTokens)}`).join(' ')} ${[...points].reverse().map((point, index) => `${x(points.length - 1 - index)},${y(point.rsiCumulativeTokens)}`).join(' ')}`;
  return <svg className="token-curve" viewBox={`0 0 ${width} ${height}`} aria-label="同一任务族的累计 token 对比"><line x1={left} x2={right} y1={bottom} y2={bottom} /><line x1={left} x2={right} y1={(top + bottom) / 2} y2={(top + bottom) / 2} /><polygon points={area} /><path d={path('baselineCumulativeTokens')} className="base" /><path d={path('rsiCumulativeTokens')} className="rsi" />{points.map((point, index) => <g key={point.position}><circle cx={x(index)} cy={y(point.baselineCumulativeTokens)} r="4" className="base" /><circle cx={x(index)} cy={y(point.rsiCumulativeTokens)} r="4" className="rsi" /><text x={x(index)} y="198">{point.position}</text></g>)}</svg>;
}
function Delta({ baseline, rsi, kind }: { baseline: number; rsi: number; kind: string }) {
  const delta = baseline - rsi;
  return <span className={`delta ${delta > 0 ? 'positive' : delta < 0 ? 'negative' : ''}`}>{delta > 0 ? <Check size={13} /> : <Minus size={13} />}{kind === 'token' ? `${number(Math.abs(delta))} token` : `${Math.abs(delta).toFixed(kind === 'latency' ? 1 : 0)}${kind === 'latency' ? 's' : ' 次'}`}</span>;
}

export default function CompareExperience() {
  const [data, setData] = useState<Showcase | null>(null); const [familyId, setFamilyId] = useState('finance-cancelled_payments'); const [error, setError] = useState('');
  useEffect(() => { api<Showcase>(`/api/showcase/${SHOWCASE_EXPERIMENT}`).then(setData).catch(error => setError(error.message)); }, []);
  const family = data?.families.find(item => item.id === familyId) || data?.families[0];
  const pairs = useMemo(() => data?.pairs.filter(pair => pair.scenario === family?.scenario && pair.family === family?.family) || [], [data, family]);
  if (error) return <main className="showcase-page"><p className="showcase-error">读取对照失败：{error}</p></main>;
  if (!data || !family) return <main className="showcase-page showcase-loading">正在读取 36 个已保存任务对…</main>;
  return <main className="showcase-page compare-page">
    <section className="showcase-title"><p className="showcase-kicker">COMPARISON / SAME TASK, SAME MODEL, SERIAL EXECUTION</p><h1>Agent 的经济舱。</h1><p>每一行都是同一个业务任务的两次真实运行。RSI 不是减少任务要求，而是减少重复规划与模型交接。</p></section>
    <section className="compare-summary"><div><span>严格串行</span><strong>1 / 1 / 1</strong><small>run · model · read</small></div><div><span>Agent token</span><strong>{percent(data.overview.tokenSavingRate)}</strong><small>{number(data.overview.baseline.totalTokens)} → {number(data.overview.rsi.totalTokens)}</small></div><div><span>模型调用</span><strong>{percent(data.overview.modelRequestSavingRate)}</strong><small>{data.overview.baseline.modelRequests} → {data.overview.rsi.modelRequests}</small></div><div><span>质量回归</span><strong>{data.overview.qualityRegressions}</strong><small>结构化精确验收</small></div></section>
    <section className="family-switch"><div>{data.families.map(item => <button key={item.id} onClick={() => setFamilyId(item.id)} className={item.id === family.id ? 'selected' : ''}>{item.label}<small>{percent(item.finalSavingRate)}</small></button>)}</div><p>族内 1–6 是到达顺序；不同实例使用不同记录。累计曲线与同任务差值同时展示。</p></section>
    <section className="family-curve"><div><p className="showcase-kicker">{family.label.toUpperCase()} / SIX DISTINCT RECORD SETS</p><h2>冷启动与复用，放在同一条累计曲线上。</h2><div className="curve-legend"><span className="baseline-dot" />Baseline <span className="rsi-dot" />RSI <b>{percent(family.finalSavingRate)} 累计 token</b></div></div><Curve points={family.points} /></section>
    <section className="pair-table" aria-label="任务逐项对比"><header><span>任务</span><span>Baseline</span><span>RSI</span><span>差值</span><span>执行 / 回放</span></header>{pairs.map((pair, index) => <PairRow key={pair.taskId} pair={pair} position={index + 1} />)}</section>
    <section className="compare-note"><ChevronDown size={16} /><p><b>如何读这张表：</b>Token 与模型调用来自同一固定任务的实际差值。时长来自交替串行运行，保留为观测值；它不是供应商性能的严格因果对比。</p></section>
  </main>;
}

function PairRow({ pair, position }: { pair: ShowcasePair; position: number }) {
  const baseline = pair.runs.baseline, rsi = pair.runs.rsi;
  return <article className="pair-row"><div className="pair-task"><small>{position} / 6 · {pair.recordCount} 条记录</small><strong>{pair.taskId}</strong><span>{rsi.evolution?.planningPath === 'fast' ? 'Fast 复用' : '冷启动 / Fallback'}</span></div><div className="pair-metrics"><strong>{number(total(baseline.metrics))}</strong><span>{baseline.metrics.modelRequests} LLM · {baseline.metrics.toolCalls} 工具</span><small>{duration(Number(baseline.metrics.durationMs))}</small></div><div className="pair-metrics rsi"><strong>{number(total(rsi.metrics))}</strong><span>{rsi.metrics.modelRequests} LLM · {rsi.metrics.toolCalls} 工具</span><small>{duration(Number(rsi.metrics.durationMs))}</small></div><div className="pair-deltas"><Delta baseline={total(baseline.metrics)} rsi={total(rsi.metrics)} kind="token" /><Delta baseline={Number(baseline.metrics.modelRequests)} rsi={Number(rsi.metrics.modelRequests)} kind="request" /><Delta baseline={Number(baseline.metrics.durationMs) / 1000} rsi={Number(rsi.metrics.durationMs) / 1000} kind="latency" /></div><div className="pair-links"><a href={`#replay?task=${encodeURIComponent(pair.taskId)}`}>回放 <ArrowUpRight size={14} /></a><a href={pair.links.rsi.report} target="_blank" rel="noreferrer">报告 <ExternalLink size={13} /></a></div></article>;
}
