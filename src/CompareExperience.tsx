import { useArchiveExperiment } from './archiveContext';
import { ArrowUpRight, Check, ChevronDown, ChevronLeft, ChevronRight, ExternalLink, Minus, Pause, Play, RotateCcw } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { PairDetail, ScenarioGroup, Showcase, ShowcasePair, TimelineEvent, duration, number, percent, total } from './showcase';
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

function eventAt(timeline: TimelineEvent[], step: number) {
  if (!timeline.length) return undefined;
  return timeline[Math.min(timeline.length - 1, Math.max(0, step))];
}

function channelLabel(event?: TimelineEvent) {
  return event?.channel === 'model' ? 'M / 模型请求或输出' : event?.channel === 'structured' ? 'S / 图绑定、筛选或执行' : 'C / 校验与恢复控制';
}

function LiveMetrics({ event }: { event?: TimelineEvent }) {
  const metrics = event?.metrics;
  return <div className="live-metrics"><span><b>{metrics?.modelRequests || 0}</b>LLM</span><span><b>{number(total(metrics))}</b>token</span><span><b>{metrics?.toolCalls || 0}</b>工具</span><span><b>{duration(Number(metrics?.durationMs || event?.elapsedMs))}</b>时间</span></div>;
}

function MiniRail({ timeline, step, onStep }: { timeline: TimelineEvent[]; step: number; onStep: (step: number) => void }) {
  return <div className="mini-event-rail" aria-label="已保存事件索引">{timeline.map((event, index) => <button key={event.position} className={`${event.channel} ${index === step ? 'active' : ''} ${index < step ? 'done' : ''}`} onClick={() => onStep(index)} aria-label={`${index + 1}. ${event.title}`} title={`${index + 1}. ${event.title}`}>{event.channel === 'model' ? 'M' : event.channel === 'structured' ? 'S' : 'C'}</button>)}</div>;
}

function DomainReplay({ category, detail, step, onStep }: { category: ScenarioGroup; detail?: PairDetail; step: number; onStep: (step: number) => void }) {
  if (!detail) return <article className="domain-replay loading"><small>{category.label}</small><p>正在载入已保存轨迹…</p></article>;
  const baseline = eventAt(detail.runs.baseline.timeline, step);
  const rsi = eventAt(detail.runs.rsi.timeline, step);
  return <article className="domain-replay"><header><div><small>{category.label}</small><strong>{detail.taskId}</strong></div><a href={`#replay?task=${encodeURIComponent(detail.taskId)}`} aria-label={`打开 ${detail.taskId} 完整回放`} title="打开完整回放"><ArrowUpRight size={16} /></a></header><div className="live-lanes"><div><span>BASELINE · {channelLabel(baseline)}</span><b>{baseline?.title || '等待开始'}</b><LiveMetrics event={baseline} /><MiniRail timeline={detail.runs.baseline.timeline} step={Math.min(step, detail.runs.baseline.timeline.length - 1)} onStep={onStep} /></div><div className="rsi-live"><span>RSI · {channelLabel(rsi)}</span><b>{rsi?.title || '等待开始'}</b><LiveMetrics event={rsi} /><MiniRail timeline={detail.runs.rsi.timeline} step={Math.min(step, detail.runs.rsi.timeline.length - 1)} onStep={onStep} /></div></div></article>;
}

function ReplayStrip({ categories, details }: { categories: ScenarioGroup[]; details: Record<string, PairDetail> }) {
  const [step, setStep] = useState(0); const [playing, setPlaying] = useState(false); const [focusedScenario, setFocusedScenario] = useState('finance');
  const maxStep = Math.max(1, ...Object.values(details).flatMap(detail => [detail.runs.baseline.timeline.length, detail.runs.rsi.timeline.length]).map(length => Math.max(0, length - 1)));
  const focused = categories.find(category => category.scenario === focusedScenario) || categories[0];
  const focus = focused && details[focused.featuredTaskId];
  const baseline = focus && eventAt(focus.runs.baseline.timeline, step);
  const rsi = focus && eventAt(focus.runs.rsi.timeline, step);
  useEffect(() => { if (!playing) return; const timer = window.setInterval(() => setStep(current => current >= maxStep ? 0 : current + 1), 720); return () => window.clearInterval(timer); }, [playing, maxStep]);
  return <section className="live-replay"><header><div><p className="showcase-kicker">THREE DOMAIN REPLAYS / EXACT SAVED EVENT INDEX</p><h2>每一格，都是一次真实执行事件。</h2></div><div className="replay-controls"><button onClick={() => setStep(value => Math.max(0, value - 1))} aria-label="上一步" title="上一步"><ChevronLeft size={16} /></button><button onClick={() => setPlaying(value => !value)} aria-label={playing ? '暂停回放' : '播放回放'} title={playing ? '暂停' : '播放'}>{playing ? <Pause size={16} /> : <Play size={16} />}</button><button onClick={() => setStep(value => Math.min(maxStep, value + 1))} aria-label="下一步" title="下一步"><ChevronRight size={16} /></button><button onClick={() => { setPlaying(false); setStep(0); }} aria-label="重置回放" title="重置"><RotateCcw size={16} /></button><span>{step + 1} / {maxStep + 1}</span></div></header><input className="replay-scrubber" type="range" min="0" max={maxStep} value={step} onChange={event => { setPlaying(false); setStep(Number(event.target.value)); }} aria-label="真实事件时间步" /><div className="domain-replay-grid">{categories.map(category => <DomainReplay key={category.scenario} category={category} detail={details[category.featuredTaskId]} step={step} onStep={next => { setPlaying(false); setStep(next); setFocusedScenario(category.scenario); }} />)}</div>{focus && <section className="compare-film"><header><div><p className="showcase-kicker">FOCUSED TAKE / {focused.label.toUpperCase()}</p><h3>{focus.task.task}</h3><span>第 {step + 1} 个保存事件；两个轨道按各自事件序列前进，短轨结束后停在最终状态。</span></div><div className="replay-focus-tabs">{categories.map(category => <button key={category.scenario} className={category.scenario === focused.scenario ? 'selected' : ''} onClick={() => { setPlaying(false); setFocusedScenario(category.scenario); }}>{category.label}</button>)}</div></header><div className="compare-film-lanes"><FocusedLane label="BASELINE" event={baseline} timeline={focus.runs.baseline.timeline} step={step} onStep={next => { setPlaying(false); setStep(next); }} /><FocusedLane label="RSI" rsi event={rsi} timeline={focus.runs.rsi.timeline} step={step} onStep={next => { setPlaying(false); setStep(next); }} /></div><a className="compare-film-link" href={`#replay?task=${encodeURIComponent(focus.taskId)}`}>打开该任务的 DAG 与参数绑定回放 <ArrowUpRight size={15} /></a></section>}<p className="replay-hint">M 表示模型请求或可见输出；S 表示图绑定、筛选、依赖驱动工具调用；C 表示校验和有界恢复。这里不按比例抽帧，也不生成虚构事件。技术代表任务选用 labels；未分配工单仍保留在技术领域的全量 12 项计算中。</p></section>;
}

function FocusedLane({ label, event, timeline, step, onStep, rsi = false }: { label: string; event?: TimelineEvent; timeline: TimelineEvent[]; step: number; onStep: (step: number) => void; rsi?: boolean }) {
  const metrics = event?.metrics;
  const boundedStep = Math.min(step, Math.max(0, timeline.length - 1));
  return <article className={`compare-film-lane ${rsi ? 'rsi' : 'baseline'}`}><header><span>{label}</span><small>{channelLabel(event)}</small></header><strong>{event?.title || '等待开始'}</strong><LiveMetrics event={event} /><MiniRail timeline={timeline} step={boundedStep} onStep={onStep} /><footer>{rsi ? 'S：图已选节点、当前观察参数绑定、筛选与图执行。' : 'M：读取后由模型继续选择下一步工具或报告动作。'}</footer></article>;
}

export default function CompareExperience() {
  const experimentId = useArchiveExperiment();
  const [data, setData] = useState<Showcase | null>(null); const [groupId, setGroupId] = useState('all'); const [error, setError] = useState(''); const [details, setDetails] = useState<Record<string, PairDetail>>({});
  useEffect(() => { api<Showcase>(`/api/showcase/${experimentId}`).then(setData).catch(error => setError(error.message)); }, []);
  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    Promise.all(data.categories.map(category => api<PairDetail>(`/api/showcase/${experimentId}/pairs/${encodeURIComponent(category.featuredTaskId)}`))).then(values => {
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
