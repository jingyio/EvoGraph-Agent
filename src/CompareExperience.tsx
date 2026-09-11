import { ArrowUpRight, Check, ChevronDown, ExternalLink, Minus, Pause, Play, RotateCcw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { PairDetail, ScenarioGroup, SHOWCASE_EXPERIMENT, Showcase, ShowcasePair, TimelineEvent, duration, number, percent, total } from './showcase';
import './showcase.css';

function Curve({ points }: { points: { baselineCumulativeTokens: number; rsiCumulativeTokens: number; position: number }[] }) {
  const width = 680, height = 210, left = 20, right = 660, top = 20, bottom = 176;
  const max = Math.max(1, ...points.flatMap(point => [point.baselineCumulativeTokens, point.rsiCumulativeTokens]));
  const x = (index: number) => left + (right - left) * index / Math.max(1, points.length - 1);
  const y = (value: number) => bottom - (bottom - top) * value / max;
  const path = (key: 'baselineCumulativeTokens' | 'rsiCumulativeTokens') => points.map((point, index) => `${index ? 'L' : 'M'}${x(index)},${y(point[key])}`).join(' ');
  const area = `${points.map((point, index) => `${x(index)},${y(point.baselineCumulativeTokens)}`).join(' ')} ${[...points].reverse().map((point, index) => `${x(points.length - 1 - index)},${y(point.rsiCumulativeTokens)}`).join(' ')}`;
  return <svg className="token-curve" viewBox={`0 0 ${width} ${height}`} aria-label="固定任务集合的累计 token 对比"><line x1={left} x2={right} y1={bottom} y2={bottom} /><line x1={left} x2={right} y1={(top + bottom) / 2} y2={(top + bottom) / 2} /><polygon points={area} /><path d={path('baselineCumulativeTokens')} className="base" /><path d={path('rsiCumulativeTokens')} className="rsi" />{points.map((point, index) => <g key={point.position}><circle cx={x(index)} cy={y(point.baselineCumulativeTokens)} r="4" className="base" /><circle cx={x(index)} cy={y(point.rsiCumulativeTokens)} r="4" className="rsi" /><text x={x(index)} y="198">{point.position}</text></g>)}</svg>;
}

function Delta({ baseline, rsi, kind }: { baseline: number; rsi: number; kind: string }) {
  const delta = baseline - rsi;
  return <span className={`delta ${delta > 0 ? 'positive' : delta < 0 ? 'negative' : ''}`}>{delta > 0 ? <Check size={13} /> : <Minus size={13} />}{kind === 'token' ? `${number(Math.abs(delta))} token` : `${Math.abs(delta).toFixed(kind === 'latency' ? 1 : 0)}${kind === 'latency' ? 's' : ' 次'}`}</span>;
}

function eventAt(timeline: TimelineEvent[], step: number, maxStep: number) {
  if (!timeline.length) return undefined;
  const index = Math.min(timeline.length - 1, Math.round(step * (timeline.length - 1) / Math.max(1, maxStep)));
  return timeline[index];
}

function LiveMetrics({ event }: { event?: TimelineEvent }) {
  const metrics = event?.metrics;
  return <div className="live-metrics"><span><b>{metrics?.modelRequests || 0}</b>LLM</span><span><b>{number(total(metrics))}</b>token</span><span><b>{metrics?.toolCalls || 0}</b>工具</span><span><b>{duration(Number(metrics?.durationMs || event?.elapsedMs))}</b>时间</span></div>;
}

function DomainReplay({ category, detail, step, maxStep }: { category: ScenarioGroup; detail?: PairDetail; step: number; maxStep: number }) {
  if (!detail) return <article className="domain-replay loading"><small>{category.label}</small><p>正在载入已保存轨迹…</p></article>;
  const baseline = eventAt(detail.runs.baseline.timeline, step, maxStep);
  const rsi = eventAt(detail.runs.rsi.timeline, step, maxStep);
  return <article className="domain-replay"><header><div><small>{category.label}</small><strong>{detail.taskId}</strong></div><a href={`#replay?task=${encodeURIComponent(detail.taskId)}`} aria-label={`打开 ${detail.taskId} 完整回放`} title="打开完整回放"><ArrowUpRight size={16} /></a></header><div className="live-lanes"><div><span>BASELINE</span><b>{baseline?.title || '等待开始'}</b><LiveMetrics event={baseline} /></div><div className="rsi-live"><span>RSI</span><b>{rsi?.title || '等待开始'}</b><LiveMetrics event={rsi} /></div></div></article>;
}

function ReplayStrip({ categories, details }: { categories: ScenarioGroup[]; details: Record<string, PairDetail> }) {
  const [step, setStep] = useState(0); const [playing, setPlaying] = useState(false);
  const maxStep = Math.max(1, ...Object.values(details).flatMap(detail => [detail.runs.baseline.timeline.length, detail.runs.rsi.timeline.length]).map(length => Math.max(0, length - 1)));
  useEffect(() => { if (!playing) return; const timer = window.setInterval(() => setStep(current => current >= maxStep ? 0 : current + 1), 900); return () => window.clearInterval(timer); }, [playing, maxStep]);
  return <section className="live-replay"><header><div><p className="showcase-kicker">THREE DOMAIN REPLAYS / SAVED TRACE, NOT SYNTHETIC ANIMATION</p><h2>同一时间步，三类 Agent 同步向前。</h2></div><div className="replay-controls"><button onClick={() => setPlaying(value => !value)} aria-label={playing ? '暂停回放' : '播放回放'} title={playing ? '暂停' : '播放'}>{playing ? <Pause size={16} /> : <Play size={16} />}</button><button onClick={() => { setPlaying(false); setStep(0); }} aria-label="重置回放" title="重置"><RotateCcw size={16} /></button><span>{step + 1} / {maxStep + 1}</span></div></header><input className="replay-scrubber" type="range" min="0" max={maxStep} value={step} onChange={event => { setPlaying(false); setStep(Number(event.target.value)); }} aria-label="回放时间步" /><div className="domain-replay-grid">{categories.map(category => <DomainReplay key={category.scenario} category={category} detail={details[category.featuredTaskId]} step={step} maxStep={maxStep} />)}</div><p className="replay-hint">每一帧是保存 trace 的真实累计状态。技术代表任务选用 labels；未分配工单仍保留在技术领域的全量 12 项计算中，但不作为主讲案例。</p></section>;
}

export default function CompareExperience() {
  const [data, setData] = useState<Showcase | null>(null); const [groupId, setGroupId] = useState('all'); const [error, setError] = useState(''); const [details, setDetails] = useState<Record<string, PairDetail>>({});
  useEffect(() => { api<Showcase>(`/api/showcase/${SHOWCASE_EXPERIMENT}`).then(setData).catch(error => setError(error.message)); }, []);
  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    Promise.all(data.categories.map(category => api<PairDetail>(`/api/showcase/${SHOWCASE_EXPERIMENT}/pairs/${encodeURIComponent(category.featuredTaskId)}`))).then(values => {
      if (!cancelled) setDetails(Object.fromEntries(values.map(value => [value.taskId, value])));
    }).catch(error => { if (!cancelled) setError(error.message); });
    return () => { cancelled = true; };
  }, [data]);
  const groups = data ? [data.allTasks, ...data.categories] : [];
  const selected = groups.find(group => group.id === groupId) || groups[0];
  const pairs = useMemo(() => !data || !selected ? [] : data.pairs.filter(pair => selected.pairs.includes(pair.taskId)), [data, selected]);
  if (error) return <main className="showcase-page"><p className="showcase-error">读取对照失败：{error}</p></main>;
  if (!data || !selected) return <main className="showcase-page showcase-loading">正在读取 36 个已保存任务对…</main>;
  const metrics = selected.metrics;
  return <main className="showcase-page compare-page">
    <section className="showcase-title"><p className="showcase-kicker">COMPARISON / SAME TASK, SAME MODEL, SERIAL EXECUTION</p><h1>Agent 的经济舱。</h1><p>主结论覆盖固定协议内的全部 36 个任务对，并按财务、客服、技术工单三大领域组织。300 个公开历史任务中，只有这 36 个固定 train 任务进入本次严格串行对照。</p></section>
    <section className="compare-summary"><div><span>严格串行</span><strong>1 / 1 / 1</strong><small>run · model · read</small></div><div><span>Agent token</span><strong>{percent(data.overview.tokenSavingRate)}</strong><small>{number(data.overview.baseline.totalTokens)} → {number(data.overview.rsi.totalTokens)}</small></div><div><span>模型调用</span><strong>{percent(data.overview.modelRequestSavingRate)}</strong><small>{data.overview.baseline.modelRequests} → {data.overview.rsi.modelRequests}</small></div><div><span>固定任务覆盖</span><strong>{data.coverage.experimentTaskCount}</strong><small>来自 {data.coverage.taskbankTaskCount} 条任务库</small></div></section>
    <ReplayStrip categories={data.categories} details={details} />
    <section className="family-switch category-switch"><div>{groups.map(group => <button key={group.id} onClick={() => setGroupId(group.id)} className={group.id === selected.id ? 'selected' : ''}>{group.label}<small>{group.taskCount} 任务 · {percent(group.finalSavingRate)}</small></button>)}</div><p>{data.coverage.experimentDescription} “全部”保留每个任务；领域视图只是聚合，不移除技术未分配工单等低收益样本。</p></section>
    <section className="family-curve"><div><p className="showcase-kicker">{selected.label.toUpperCase()} / FIXED TASK MANIFEST</p><h2>冷启动与复用，放在同一条累计曲线上。</h2><div className="curve-legend"><span className="baseline-dot" />Baseline <span className="rsi-dot" />RSI <b>{percent(selected.finalSavingRate)} 累计 token</b></div></div><Curve points={selected.points} /></section>
    <section className="group-statline"><div><span>任务通过</span><b>{metrics.baseline.passed}/{metrics.baseline.attempts} → {metrics.rsi.passed}/{metrics.rsi.attempts}</b></div><div><span>LLM 请求</span><b>{metrics.baseline.modelRequests} → {metrics.rsi.modelRequests}</b></div><div><span>工具调用</span><b>{metrics.baseline.toolCalls} → {metrics.rsi.toolCalls}</b></div><div><span>累计时长</span><b>{duration(metrics.baseline.durationMs)} → {duration(metrics.rsi.durationMs)}</b></div></section>
    <section className="pair-table" aria-label="任务逐项对比"><header><span>任务</span><span>Baseline</span><span>RSI</span><span>差值</span><span>执行 / 回放</span></header>{pairs.map((pair, index) => <PairRow key={pair.taskId} pair={pair} position={index + 1} totalTasks={pairs.length} />)}</section>
    <section className="compare-note"><ChevronDown size={16} /><p><b>如何读这张表：</b>Token 与模型调用来自同一固定任务的实际差值。时长来自交替串行运行，保留为观测值；它不是供应商性能的严格因果对比。</p></section>
  </main>;
}

function PairRow({ pair, position, totalTasks }: { pair: ShowcasePair; position: number; totalTasks: number }) {
  const baseline = pair.runs.baseline, rsi = pair.runs.rsi;
  return <article className="pair-row"><div className="pair-task"><small>{position} / {totalTasks} · {pair.recordCount} 条记录 · {pair.familyLabel}</small><strong>{pair.taskId}</strong><span>{rsi.evolution?.planningPath === 'fast' ? 'Fast 复用' : '冷启动 / Fallback'}</span></div><div className="pair-metrics"><strong>{number(total(baseline.metrics))}</strong><span>{baseline.metrics.modelRequests} LLM · {baseline.metrics.toolCalls} 工具</span><small>{duration(Number(baseline.metrics.durationMs))}</small></div><div className="pair-metrics rsi"><strong>{number(total(rsi.metrics))}</strong><span>{rsi.metrics.modelRequests} LLM · {rsi.metrics.toolCalls} 工具</span><small>{duration(Number(rsi.metrics.durationMs))}</small></div><div className="pair-deltas"><Delta baseline={total(baseline.metrics)} rsi={total(rsi.metrics)} kind="token" /><Delta baseline={Number(baseline.metrics.modelRequests)} rsi={Number(rsi.metrics.modelRequests)} kind="request" /><Delta baseline={Number(baseline.metrics.durationMs) / 1000} rsi={Number(rsi.metrics.durationMs) / 1000} kind="latency" /></div><div className="pair-links"><a href={`#replay?task=${encodeURIComponent(pair.taskId)}`}>回放 <ArrowUpRight size={14} /></a><a href={pair.links.rsi.report} target="_blank" rel="noreferrer">报告 <ExternalLink size={13} /></a></div></article>;
}
