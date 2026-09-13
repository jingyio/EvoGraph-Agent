import { Activity, ArrowRight, CheckCircle2, Circle, ClipboardList, FlaskConical, Gauge, Layers3, LoaderCircle, ShieldCheck, Square, Waypoints } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import './workpack-experiment.css';
import './workpack-judgement.css';

type Mode = 'smoke_v12' | 'precheck_v12' | 'full_train_v10';
type StoredMode = Mode | 'smoke_v11' | 'precheck_v11' | 'full_train_v9' | 'smoke_v10' | 'precheck_v10' | 'full_train_v8' | 'smoke_v9' | 'precheck_v9' | 'full_train_v7' | 'smoke_v8' | 'precheck_v8' | 'full_train_v6' | 'smoke_v6' | 'precheck_v6' | 'full_train_v4' | 'smoke_v5' | 'precheck_v5' | 'full_train_v3' | 'smoke_v4' | 'precheck_v4' | 'full_train_v2' | 'precheck_v3' | 'full_train_v1';
type Scenario = 'finance' | 'support' | 'tickets';
type ArmRun = { id: string; status: string; metrics: { inputTokens?: number; outputTokens?: number; modelRequests?: number; toolCalls?: number; durationMs?: number }; evaluation?: { status?: string }; evolution?: { planningPath?: string; usedVersionId?: string; generatedVersionIds?: string[] } };
type Snapshot = { kind: 'before' | 'after'; arm: 'baseline' | 'rsi'; versions: { id: string; sourceTaskId?: string; generation?: number }[] };
type Pair = { index: number; workpackId: string; scenario: Scenario; workflowType: string; recordCount: number; difficulty: string; round: number; status: string; armOrder?: string[]; runs: { baseline?: ArmRun; rsi?: ArmRun }; snapshots?: Snapshot[] };
type CurvePoint = { index: number; workpackId: string; workflowType: string; round: number; baselineTokens: number; rsiTokens: number; baselineCumulativeTokens: number; rsiCumulativeTokens: number; tokenSavingRate: number | null; rsiPlanningPath?: string; usedVersionId?: string | null; baselinePassed: boolean; rsiPassed: boolean };
type Group = { key: string; taskCount: number; baseline: { attempts: number; passed: number; totalTokens: number; modelRequests: number; toolCalls: number; durationMs: number }; rsi: { attempts: number; passed: number; totalTokens: number; modelRequests: number; toolCalls: number; durationMs: number }; tokenSavingRate: number | null; fastReuse: number; workflowCreated: number };
type ReliabilityArm = { attempts: number; passed: number; totalTokens: number; maxTokens: number; tokensPerPassed: number | null; modelRequests: number; toolCalls: number; toolErrors: number; controlErrors: number; durationMs: number; p50DurationMs: number | null; p95DurationMs: number | null; maxDurationMs: number; usageIncomplete: number; maintenanceErrors: number; reportAttempts: number; failedReportAttempts: number; runsWithReportRecovery: number; runsWithRepeatedReportFailures: number; reportEvidenceCoverageGaps: number; reportEvidenceFormatFailures: number; reportRecoveryBlockedReads: number; duplicateReadGuardRejects: number; duplicateComputeGuardRejects: number; observedScopeCompletions: number; contextEvidenceReferenceCompactions: number; contextCompactedCharacters: number; deterministicScopeRecoveryReads: number; deterministicReportResubmits: number; missingReports: number; failureCategories: Record<string, number> };
type Saturation = { windowSize: number; windows: { startIndex: number; endIndex: number; taskCount: number; tokenSavingRate: number | null; fastCoverage: number; baselinePassRate: number; rsiPassRate: number }[]; comparisons: { previousEndIndex: number; currentEndIndex: number; tokenSavingRateDelta: number; fastCoverageDelta: number; rsiPassRateDelta: number; matchesRule: boolean }[]; possiblePlateau: boolean; familyAssessment: string; note: string };
type Summary = { baseline: ReliabilityArm; rsi: ReliabilityArm; pairedCompleted: number; tokenSavingRate: number | null; curve: CurvePoint[]; byScenario?: Group[]; byWorkflow?: Group[]; byRound?: Group[]; learning: { workflowCreated: number; fastReuse: number; composition: number; fallback: number }; reliability?: { allUsageComplete: boolean; note: string }; saturation?: Saturation; qualityGate?: { status: 'passed' | 'failed' | 'incomplete'; reason: string; sameQualityCostClaim: boolean; baselinePassed: number; baselineAttempts: number; rsiPassed: number; rsiAttempts: number } };
type Protocol = { id: string; mode: Mode; taskCountPerArm: number; agentRuns: number; estimatedAgentModelRequests: number; estimatedAgentTokens: number; estimatedSerialDurationMs?: number; estimateBasis?: string; order: string; limits: { run: number; model: number; read: number }; manifest: Omit<Pair, 'status' | 'runs'>[]; saturationRule: { window: number; requires: string; tokenSavingRateDelta: string; fastCoverageDelta: string; successRateDelta: string; interpretation: string } };
type Experiment = { id: string; mode?: StoredMode; status: string; createdAt: string; startedAt?: string; finishedAt?: string; error?: string; protocol: Protocol; pairs: Pair[]; summary: Summary };
type JudgeProtocol = { eligiblePairs: number; notScoredMissingReport: number; normalModelRequests: number; maximumModelRequestsWithOneFormatRepairPerOrder: number; judgeCost: string; inputEvidence: string };
type JudgeBatch = { id: string; status: string; model: string | null; sameAsExecutor: boolean; metrics: { modelRequests: number; inputTokens: number; outputTokens: number; usageComplete: boolean; durationMs: number; normalRequestBudget: number; maximumRequestBudget: number }; summary: { completedPairs: number; failedPairs: number; notScoredPairs: number; orderDisagreements: number; reports: { baseline: { dimensions: Record<string, number>; reward: number } | null; rsi: { dimensions: Record<string, number>; reward: number } | null } } };
type JudgeResponse = { items: JudgeBatch[]; protocol: JudgeProtocol; model: string | null };

const groupName: Record<Scenario, string> = { finance: '财务运营', support: '客服运营', tickets: '技术工单' };
const modeCopy: Record<Mode, { title: string; detail: string; action: string }> = {
  smoke_v12: { title: '3 项三场景 Smoke', detail: '财务、客服、技术工单各一项完整 train 工作包。比例任务要求两臂实际调用加权对账，并验证重复确定性计算有界。', action: '开始 Smoke' },
  precheck_v12: { title: '12 项机制预检', detail: '六类连续 train 工作包。仅在当前 runtime 的 Smoke 质量与比例工具轨迹通过后可启动。', action: '开始预检' },
  full_train_v10: { title: '48 项正式 train 流', detail: '三场景 12 类工作流，每类 4 个冻结 train 实例；仅在 V12 预检质量通过后可启动。', action: '开始正式流' },
};
const storedModeTitle: Record<StoredMode, string> = {
  smoke_v12: 'V12 Smoke', precheck_v12: 'V12 预检', full_train_v10: 'V12 正式 train',
  smoke_v11: 'V11 Smoke', precheck_v11: 'V11 预检', full_train_v9: 'V11 正式 train',
  smoke_v10: 'V10 Smoke', precheck_v10: 'V10 预检', full_train_v8: 'V10 正式 train',
  smoke_v9: 'V9 Smoke', precheck_v9: 'V9 预检', full_train_v7: 'V9 正式 train',
  smoke_v8: 'V8 Smoke', precheck_v8: 'V8 预检', full_train_v6: 'V8 正式 train',
  smoke_v6: '历史 V6 Smoke', precheck_v6: '历史 V6 预检', full_train_v4: '历史 V6 正式 train',
  smoke_v5: '历史 V5 Smoke', precheck_v5: '历史 V5 预检', full_train_v3: '历史 V3 正式 train',
  smoke_v4: '历史 V4 Smoke', precheck_v4: '历史 V4 预检', full_train_v2: '历史 V2 正式 train',
  precheck_v3: '历史 V3 预检', full_train_v1: '历史 V1 正式 train',
};
const number = (value?: number) => new Intl.NumberFormat('zh-CN').format(value || 0);
const token = (run?: ArmRun) => (run?.metrics.inputTokens || 0) + (run?.metrics.outputTokens || 0);
const percent = (value?: number | null) => value == null ? '—' : `${(value * 100).toFixed(1)}%`;
const seconds = (value?: number) => value == null ? '—' : `${(value / 1000).toFixed(1)}s`;

function defaultExperiment(items: Experiment[]) {
  return [...items].sort((left, right) => {
    const leftActive = ['queued', 'running'].includes(left.status) ? 1 : 0;
    const rightActive = ['queued', 'running'].includes(right.status) ? 1 : 0;
    if (leftActive !== rightActive) return rightActive - leftActive;
    return String(right.createdAt || '').localeCompare(String(left.createdAt || ''));
  })[0] || null;
}

function evolutionText(pair: Pair) {
  const evolution = pair.runs.rsi?.evolution;
  if (!evolution) return '未形成可复用结构';
  if (evolution.usedVersionId) {
    const before = pair.snapshots?.find(snapshot => snapshot.kind === 'before' && snapshot.arm === 'rsi');
    const source = before?.versions.find(version => version.id === evolution.usedVersionId);
    return source?.sourceTaskId ? `Fast 复用 ${source.sourceTaskId}` : `Fast 复用 ${evolution.usedVersionId.slice(0, 8)}`;
  }
  if (evolution.generatedVersionIds?.length) return `形成 ${evolution.generatedVersionIds.length} 个 G0`;
  return evolution.planningPath === 'fallback' ? 'Fallback：本次完整规划' : '未形成可复用结构';
}

function Curve({ points }: { points: CurvePoint[] }) {
  if (!points.length) return <div className="workpack-empty-chart"><Activity size={19} /><span>等待第一组实际成对运行。曲线只会从保存的两臂计量生成。</span></div>;
  const max = Math.max(...points.flatMap(point => [point.baselineCumulativeTokens, point.rsiCumulativeTokens]), 1);
  return <div className="workpack-curve" aria-label="累计 token 曲线">
    <div className="workpack-curve-legend"><span><i className="baseline" />Baseline 累计 token</span><span><i className="rsi" />RSI 累计 token</span></div>
    <div className="workpack-bars">{points.map(point => <div className="workpack-bar-set" key={point.index} title={`${point.workpackId}: Baseline ${point.baselineCumulativeTokens}, RSI ${point.rsiCumulativeTokens}`}><div className="workpack-bar baseline" style={{ height: `${Math.max(3, point.baselineCumulativeTokens / max * 100)}%` }} /><div className="workpack-bar rsi" style={{ height: `${Math.max(3, point.rsiCumulativeTokens / max * 100)}%` }} /><small>{point.index}</small></div>)}</div>
  </div>;
}

function Breakdown({ groups }: { groups: Group[] }) {
  if (!groups.length) return null;
  return <section className="workpack-breakdown"><header><small>SCENARIO BREAKDOWN</small><h2>按场景的同任务差值</h2></header><div className="workpack-breakdown-grid">{groups.map(row => <article key={row.key}><small>{groupName[row.key as Scenario] || row.key}</small><strong>{number(row.baseline.totalTokens)} <span>→</span> {number(row.rsi.totalTokens)}</strong><em>{percent(row.tokenSavingRate)}</em><p>{row.baseline.passed}/{row.taskCount} · {row.rsi.passed}/{row.taskCount} 通过<br />Fast {row.fastReuse} · G0 {row.workflowCreated}</p></article>)}</div></section>;
}

export default function WorkpackExperimentPanel() {
  const [mode, setMode] = useState<Mode>('smoke_v12');
  const [protocol, setProtocol] = useState<Protocol | null>(null);
  const [items, setItems] = useState<Experiment[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [scenario, setScenario] = useState<'all' | Scenario>('all');
  const [costConfirmed, setCostConfirmed] = useState(false);
  const [judgeCostConfirmed, setJudgeCostConfirmed] = useState(false);
  const [judgeData, setJudgeData] = useState<JudgeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const selected = useMemo(() => items.find(item => item.id === selectedId) || defaultExperiment(items), [items, selectedId]);
  const running = selected?.status === 'queued' || selected?.status === 'running';
  const latestJudge = judgeData?.items.at(-1) || null;
  const judgeRunning = latestJudge?.status === 'queued' || latestJudge?.status === 'running';
  const refresh = async () => {
    const next = await api<Experiment[]>('/api/workpack-experiments');
    setItems(next);
    setSelectedId(current => current && next.some(item => item.id === current) ? current : defaultExperiment(next)?.id || '');
  };
  const refreshJudge = async (experimentId: string) => {
    const next = await api<JudgeResponse>(`/api/workpack-experiments/${experimentId}/judgements`);
    setJudgeData(next);
  };
  useEffect(() => { void refresh().catch(reason => setError(reason.message)); }, []);
  useEffect(() => { api<Protocol>(`/api/workpack-experiments/protocol?mode=${mode}`).then(setProtocol).catch(reason => setError(reason.message)); setCostConfirmed(false); }, [mode]);
  useEffect(() => {
    setJudgeCostConfirmed(false);
    if (!selected?.id) { setJudgeData(null); return; }
    void refreshJudge(selected.id).catch(reason => setError(reason.message));
  }, [selected?.id]);
  useEffect(() => {
    if (!running && !judgeRunning) return;
    const timer = window.setInterval(() => {
      void refresh().catch(reason => setError(reason.message));
      if (selected?.id) void refreshJudge(selected.id).catch(reason => setError(reason.message));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [running, judgeRunning, selected?.id]);
  async function start() {
    if (!costConfirmed || busy) return;
    setBusy(true); setError('');
    try {
      const result = await api<Experiment>('/api/workpack-experiments', { method: 'POST', body: JSON.stringify({ mode, confirmCost: true }) });
      setItems(current => [result, ...current]); setSelectedId(result.id); setCostConfirmed(false);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }
  async function cancel() {
    if (!selected) return;
    await api(`/api/workpack-experiments/${selected.id}/cancel`, { method: 'POST', body: '{}' });
    await refresh();
  }
  async function startJudge() {
    if (!selected || !judgeCostConfirmed || busy) return;
    setBusy(true); setError('');
    try {
      await api(`/api/workpack-experiments/${selected.id}/judgements`, { method: 'POST', body: JSON.stringify({ confirmCost: true }) });
      await refreshJudge(selected.id);
      setJudgeCostConfirmed(false);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }
  const curve = selected?.summary.curve || [];
  const visibleManifest = (protocol?.manifest || []).filter(item => scenario === 'all' || item.scenario === scenario);
  const visiblePairs = (selected?.pairs || []).filter(pair => scenario === 'all' || pair.scenario === scenario);
  const selectedMode = (selected?.protocol.mode || selected?.mode || 'smoke_v12') as StoredMode;
  const qualityGate = selected?.summary.qualityGate;
  return <main className="workpack-experiment-shell">
    <header className="workpack-experiment-head"><div><p>EXPERIMENT CENTER / ISOLATED WORKPACKS</p><h1>在线经验积累与复用</h1><span>固定工作包经相同的文件解析、工作请求与 Agent runtime 执行。新工作区实验与历史 V4 任务库结果相互独立。</span></div><a href="#home">返回工作台 <ArrowRight size={14} /></a></header>
    {error && <p className="workpack-error">{error}</p>}
    <section className="workpack-mode-picker" aria-label="实验范围">{(Object.keys(modeCopy) as Mode[]).map(item => <button key={item} className={mode === item ? 'selected' : ''} onClick={() => setMode(item)} disabled={busy || running}><small>{item === 'smoke_v12' ? 'SMOKE' : item === 'precheck_v12' ? 'STAGED' : 'FORMAL'}</small><strong>{modeCopy[item].title}</strong><span>{modeCopy[item].detail}</span></button>)}</section>
    {protocol && <section className="workpack-protocol"><div><ClipboardList size={18} /><small>冻结范围</small><strong>{protocol.taskCountPerArm} 项 / 臂</strong><span>{protocol.agentRuns} 次真实 Agent</span></div><div><Gauge size={18} /><small>串行限制</small><strong>{protocol.limits.run} / {protocol.limits.model} / {protocol.limits.read}</strong><span>run / model / read</span></div><div><Layers3 size={18} /><small>预估 Agent token</small><strong>{number(protocol.estimatedAgentTokens)}</strong><span>{protocol.estimateBasis || '执行前估算'}</span></div><div><Waypoints size={18} /><small>Judge</small><strong>不运行</strong><span>性能稳定后另行确认</span></div></section>}
    <section className="workpack-controls"><div><p>冻结任务清单</p><span>{protocol?.order}。Baseline 不跨任务学习；RSI 从新的空经验库起步，train 才更新经验。</span></div><label><input type="checkbox" checked={costConfirmed} disabled={busy || running} onChange={event => setCostConfirmed(event.target.checked)} />我确认启动 {protocol?.agentRuns || 0} 次真实 Agent 运行</label><button disabled={!costConfirmed || busy || running} onClick={() => void start()}>{busy ? <LoaderCircle size={15} /> : <FlaskConical size={15} />}{modeCopy[mode].action}</button>{running && <button className="stop" onClick={() => void cancel()}><Square size={14} />停止</button>}</section>
    <section className="workpack-filter"><label>展示场景<select aria-label="筛选场景" value={scenario} onChange={event => setScenario(event.target.value as 'all' | Scenario)}><option value="all">全部场景</option>{(Object.keys(groupName) as Scenario[]).map(key => <option key={key} value={key}>{groupName[key]}</option>)}</select></label><span>{visibleManifest.length} 个冻结任务 · 图表只来自保存的实际运行</span></section>
    <section className="workpack-manifest">{visibleManifest.map(item => <div key={item.workpackId}><small>{groupName[item.scenario]} · R{item.round}</small><strong>{item.workflowType.replaceAll('-', ' ')}</strong><span>{item.workpackId} · {item.recordCount} 条 · {item.difficulty}</span></div>)}</section>
    <section className="workpack-result-head"><div><p>已保存实验</p><h2>{selected ? `${selected.id.slice(0, 8)} · ${storedModeTitle[selectedMode]} · ${selected.status}` : '尚未启动新的工作包在线实验'}</h2></div>{items.length > 1 && <select aria-label="选择已保存实验" value={selected?.id || ''} onChange={event => setSelectedId(event.target.value)}>{items.map(item => <option key={item.id} value={item.id}>{item.id.slice(0, 8)} · {item.protocol.taskCountPerArm} 项/臂 · {item.status}</option>)}</select>}</section>
    {selected ? <>
      <section className="workpack-kpis"><div><small>结构化通过</small><strong>{selected.summary.baseline.passed}/{selected.summary.baseline.attempts} · {selected.summary.rsi.passed}/{selected.summary.rsi.attempts}</strong><span>Baseline · RSI</span></div><div><small>累计 token</small><strong>{number(selected.summary.baseline.totalTokens)} → {number(selected.summary.rsi.totalTokens)}</strong><span>完成配对 {selected.summary.pairedCompleted}</span></div><div><small>累计节省率</small><strong>{percent(selected.summary.tokenSavingRate)}</strong><span>{qualityGate?.sameQualityCostClaim ? '质量门槛通过' : '不作为同质量经济性结论'}</span></div><div><small>RSI Fast</small><strong>{selected.summary.learning.fastReuse}</strong><span>G0 创建 {selected.summary.learning.workflowCreated}</span></div></section>
      {qualityGate && <section className={`workpack-quality-gate ${qualityGate.status}`}><ShieldCheck size={17} /><div><small>QUALITY GATE / FULL ATTEMPT ACCOUNTING</small><strong>{qualityGate.status === 'passed' ? '两臂均完成且每项通过' : qualityGate.status === 'incomplete' ? '冻结范围未完成' : '存在结构化质量回归'}</strong><span>{qualityGate.reason}</span></div></section>}
      <Breakdown groups={selected.summary.byScenario || []} />
      <section className="workpack-results"><article><header><small>CUMULATIVE COST</small><h2>同任务累计 token</h2></header><Curve points={curve.filter(point => scenario === 'all' || point.workpackId.startsWith(scenario === 'tickets' ? 'tickets-' : `${scenario}-`))} /></article><article><header><small>LEARNING HEALTH</small><h2>实际机制与状态</h2></header><div className="workpack-health"><span><CheckCircle2 size={15} />G0 Workflow 创建 <b>{selected.summary.learning.workflowCreated}</b></span><span><Activity size={15} />Fast 实际使用 <b>{selected.summary.learning.fastReuse}</b></span><span><Circle size={14} />Fallback <b>{selected.summary.learning.fallback}</b></span><span><Circle size={14} />Composition <b>{selected.summary.learning.composition}</b></span><p>没有 Composition 或 G1/G2 时，结果页不会虚构结构修订链。Fast 仅表示复用了已保存 Workflow，节省以真实成对 token 为准。</p></div></article></section>
      <section className="workpack-pairs"><header><p>逐任务执行与经验快照</p><span>点击报告打开对应 arm 的实际业务成果；每个任务前后经验快照在隔离 artifact 中保存。</span></header>{visiblePairs.map(pair => <article key={pair.index}><div className="workpack-pair-id"><small>{groupName[pair.scenario]} · 第 {pair.index} 项 · R{pair.round}</small><strong>{pair.workflowType}</strong><span>{pair.workpackId} · {pair.recordCount} 条 · {pair.status}</span></div>{(['baseline', 'rsi'] as const).map(arm => { const run = pair.runs[arm]; return <div className={`workpack-arm ${arm}`} key={arm}><small>{arm === 'baseline' ? 'PLAN + REACT' : 'GRAPH RSI'}</small><strong>{run ? number(token(run)) : '等待'}</strong><span>{run ? `${run.metrics.modelRequests || 0} LLM · ${run.metrics.toolCalls || 0} 工具 · ${seconds(run.metrics.durationMs)}` : '尚未开始'}</span>{run && <><em>{run.evaluation?.status === 'passed' ? '硬校验通过' : run.evaluation?.status || run.status}</em><a href={`/api/workpack-experiments/${selected.id}/runs/${arm}/${run.id}/report`} target="_blank" rel="noreferrer">报告 <ArrowRight size={13} /></a></>}</div>; })}<div className="workpack-evolution"><small>RSI 经验</small><strong>{pair.runs.rsi?.evolution?.planningPath || '—'}</strong><span>{evolutionText(pair)}</span></div></article>)}</section>
      <section className="workpack-reliability"><header><small>RELIABILITY / FULL ATTEMPT ACCOUNTING</small><h2>恢复、长尾与用量完整性</h2><p>{selected.summary.reliability?.note}</p></header><div className="workpack-reliability-grid">{(['baseline', 'rsi'] as const).map(arm => { const row = selected.summary[arm]; return <article key={arm}><small>{arm === 'baseline' ? 'PLAN + REACT' : 'GRAPH RSI'}</small><dl><div><dt>P50 / P95 / Max</dt><dd>{seconds(row.p50DurationMs ?? undefined)} / {seconds(row.p95DurationMs ?? undefined)} / {seconds(row.maxDurationMs)}</dd></div><div><dt>最大单任务 token</dt><dd>{number(row.maxTokens)}</dd></div><div><dt>报告尝试 / 失败尝试</dt><dd>{row.reportAttempts} / {row.failedReportAttempts}</dd></div><div><dt>重提任务 / 重复失败任务</dt><dd>{row.runsWithReportRecovery} / {row.runsWithRepeatedReportFailures}</dd></div><div><dt>公开范围补齐 / 原报告重提</dt><dd>{row.deterministicScopeRecoveryReads} / {row.deterministicReportResubmits}</dd></div><div><dt>完整资料范围 / 重复读拒绝</dt><dd>{row.observedScopeCompletions} / {row.duplicateReadGuardRejects}</dd></div><div><dt>重复计算拒绝</dt><dd>{row.duplicateComputeGuardRejects}</dd></div><div><dt>证据引用压缩</dt><dd>{number(row.contextEvidenceReferenceCompactions)} 项 / {number(row.contextCompactedCharacters)} 字符</dd></div><div><dt>最终缺报告 / 用量不完整</dt><dd>{row.missingReports} / {row.usageIncomplete}</dd></div><div><dt>工具 / 控制错误</dt><dd>{row.toolErrors} / {row.controlErrors}</dd></div></dl><p>{Object.entries(row.failureCategories).map(([key, value]) => `${key} ${value}`).join(' · ') || '无最终失败类别'}</p></article>; })}</div></section>
      <section className="workpack-judge"><header><div><small>BLINDED REPORT JUDGE / SEPARATE COST</small><h2>匿名双顺序报告质量</h2><p>仅使用两臂 trace 已观察到的证据行；不读取私有验收答案，不影响 Agent 成本或经验。</p></div>{latestJudge ? <span className={`workpack-judge-status ${latestJudge.status}`}>{latestJudge.status}</span> : null}</header>{latestJudge ? <div className="workpack-judge-result"><div><small>Judge token</small><strong>{number(latestJudge.metrics.inputTokens + latestJudge.metrics.outputTokens)}</strong><span>{latestJudge.metrics.modelRequests} 次请求 · {seconds(latestJudge.metrics.durationMs)}</span></div><div><small>评分覆盖</small><strong>{latestJudge.summary.completedPairs} / {judgeData?.protocol.eligiblePairs || 0}</strong><span>缺报告未评分 {latestJudge.summary.notScoredPairs} · 评分失败 {latestJudge.summary.failedPairs}</span></div><div><small>顺序分歧</small><strong>{latestJudge.summary.orderDisagreements}</strong><span>{latestJudge.sameAsExecutor ? '同模型 Judge，非独立评测' : '不同模型 Judge'}</span></div>{(['baseline', 'rsi'] as const).map(arm => <div key={arm}><small>{arm === 'baseline' ? 'BASELINE reward' : 'RSI reward'}</small><strong>{latestJudge.summary.reports[arm] ? latestJudge.summary.reports[arm]!.reward.toFixed(3) : '—'}</strong><span>{latestJudge.summary.reports[arm] ? `F ${latestJudge.summary.reports[arm]!.dimensions.factuality} · C ${latestJudge.summary.reports[arm]!.dimensions.coverage} · R ${latestJudge.summary.reports[arm]!.dimensions.readability}` : '无完成双顺序评分'}</span></div>)}</div> : <div className="workpack-judge-start"><p>该批次有 {judgeData?.protocol.eligiblePairs || 0} 对报告可评分；正常需 {judgeData?.protocol.normalModelRequests || 0} 次 Judge 请求，单次格式修复的上限为 {judgeData?.protocol.maximumModelRequestsWithOneFormatRepairPerOrder || 0}。费用与 Agent 指标分开保存。</p><label><input type="checkbox" checked={judgeCostConfirmed} disabled={busy || running || judgeRunning} onChange={event => setJudgeCostConfirmed(event.target.checked)} />我确认启动独立 Judge 费用</label><button disabled={!judgeCostConfirmed || busy || running || judgeRunning || selected.status !== 'completed'} onClick={() => void startJudge()}><ShieldCheck size={15} />开始匿名双顺序 Judge</button></div>}</section>
      <section className="workpack-saturation"><small>SATURATION CHECK</small><h2>固定四任务窗口</h2><p>{selected.summary.saturation?.note}</p><div>{(selected.summary.saturation?.windows || []).map(row => <span key={row.endIndex}>#{row.startIndex}–{row.endIndex} · 节省 {percent(row.tokenSavingRate)} · Fast {percent(row.fastCoverage)} · RSI 通过 {percent(row.rsiPassRate)}</span>)}</div><strong>{selected.summary.saturation?.possiblePlateau ? '存在满足描述性规则的相邻全局窗口' : '未观察到满足描述性规则的相邻全局窗口'}</strong><p>{selected.summary.saturation?.familyAssessment}</p></section>
      <section className="workpack-boundary"><small>平台期检查</small><strong>固定窗口 {selected.protocol.saturationRule.window} 项</strong><p>{selected.protocol.saturationRule.requires}；需要累计 token 节省率变化 {selected.protocol.saturationRule.tokenSavingRateDelta}、Fast 覆盖变化 {selected.protocol.saturationRule.fastCoverageDelta} 且成功率变化 {selected.protocol.saturationRule.successRateDelta} 才只标注“可能进入平台期”。{selected.protocol.saturationRule.interpretation}</p></section>
    </> : <section className="workpack-no-result"><FlaskConical size={22} /><h2>在线预检尚未开始</h2><p>可先在工作台加载任一三场景工作包完成单次交互式工作；所有在线流在确认费用后才会启动，并使用独立经验存储和不可变快照。</p></section>}
  </main>;
}
