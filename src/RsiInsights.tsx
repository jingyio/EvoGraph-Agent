import { AlertTriangle, ArrowDown, CheckCircle2, Clock3, DatabaseZap, Gauge, GitBranch, MessageSquareText, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from './api';
import { SHOWCASE_EXPERIMENT, Showcase, duration, number, percent } from './showcase';
import './showcase.css';

function Measure({ icon, label, baseline, rsi, unit, footnote }: { icon: React.ReactNode; label: string; baseline: number; rsi: number; unit: string; footnote: string }) {
  const saving = 1 - rsi / baseline;
  return <article className="measure"><div>{icon}<span>{label}</span></div><strong>{percent(saving)}</strong><p>{number(baseline)} <ArrowDown size={14} /> {number(rsi)} {unit}</p><small>{footnote}</small></article>;
}
export default function RsiInsights() {
  const [data, setData] = useState<Showcase | null>(null); const [error, setError] = useState('');
  useEffect(() => { api<Showcase>(`/api/showcase/${SHOWCASE_EXPERIMENT}`).then(setData).catch(error => setError(error.message)); }, []);
  if (error) return <main className="showcase-page"><p className="showcase-error">读取 RSI 分析失败：{error}</p></main>;
  if (!data) return <main className="showcase-page showcase-loading">正在读取 RSI 运行时证据…</main>;
  const b = data.overview.baseline, r = data.overview.rsi, audit = data.audit.arms;
  const rsiReportFailures = `${r.diagnostics.failedReportAttempts}/${r.diagnostics.reportAttempts}`;
  const baselineReportFailures = `${b.diagnostics.failedReportAttempts}/${b.diagnostics.reportAttempts}`;
  return <main className="showcase-page insight-page">
    <section className="showcase-title"><p className="showcase-kicker">RSI EFFECT ANALYSIS / RECORDED SERIAL EXPERIMENT</p><h1>把节省拆开看。</h1><p>Token 和调用数是严格可比的主指标。延迟是同一 session 交替串行的观测值，避免把分时服务差异说成系统吞吐优势。</p></section>
    <section className="measure-grid"><Measure icon={<Gauge size={18} />} label="Agent token" baseline={b.totalTokens} rsi={r.totalTokens} unit="token" footnote="包含冷启动、规划、执行、恢复与学习相关模型请求。" /><Measure icon={<MessageSquareText size={18} />} label="LLM 请求" baseline={b.modelRequests} rsi={r.modelRequests} unit="次" footnote="RSI 少 24 次完整 Plan；其他差异来自实际执行和恢复轮数。" /><Measure icon={<Clock3 size={18} />} label="累计时长" baseline={b.durationMs} rsi={r.durationMs} unit="ms" footnote="交替串行观察值；供应商负载与缓存仍可能影响。" /></section>
    <section className="insight-split"><div className="insight-copy"><p className="showcase-kicker">ONLINE EXPERIENCE</p><h2>经验不是提示词参考。<br />它改变了后续执行路径。</h2><p>第一批同族任务保存 G0 Workflow；后续同族任务直接选择同一历史工作流并将当前任务参数绑定进去。Fast 命中后，完整 Plan 请求为零。</p><div className="experience-stats"><div><strong>{r.diagnostics.initialWorkflowVersions}</strong><span>G0 初始 Workflow</span></div><div><strong>{r.diagnostics.fastSucceeded}/{r.diagnostics.fastRuns}</strong><span>Fast 实际完成</span></div><div><strong>{r.diagnostics.maintenanceRecorded}/{r.diagnostics.maintenanceAttempts}</strong><span>经验写入 recorded</span></div></div></div><div className="experience-rail"><div className="rail-origin"><GitBranch size={18} /><span>来源任务<br /><b>形成 G0</b></span></div><i /><div className="rail-use"><DatabaseZap size={18} /><span>后续新记录任务<br /><b>当前参数绑定</b></span></div><i /><div className="rail-result"><CheckCircle2 size={18} /><span>Fast 执行<br /><b>24 次完成</b></span></div><small>未观察到 G1/G2，也没有 Composition 实际执行。</small></div></section>
    <section className="strict-audit"><header><div><p className="showcase-kicker">STRICT RESULT AUDIT</p><h2>准确率不只看“通过”。</h2></div><span><ShieldCheck size={17} />只读派生评估</span></header><div className="audit-grid"><AuditColumn label="Baseline" value={audit.baseline} /><AuditColumn label="RSI" value={audit.rsi} /></div><p className="audit-caption">结构化验收严格比对 metrics、入选记录、证据集合和“证据确实来自本次观察”。报告摘要再额外检查已知 ID、可追溯数字与金额单位表述。后者是覆盖有限的确定性审计，不冒充全面语义判定。</p></section>
    <section className="reliability-grid"><article><p className="showcase-kicker">TASK COMPLETION</p><strong>{r.passed}/{r.attempts}</strong><span>RSI 任务通过 · Baseline {b.passed}/{b.attempts}</span><small>两臂均没有工具错误、维护错误或分页拒绝。</small></article><article><p className="showcase-kicker">REPORT RECOVERY</p><strong>{rsiReportFailures}</strong><span>RSI 失败提交 / 总提交</span><small>Baseline {baselineReportFailures}。所有未通过提交均被记录并有界恢复；本样本不能称 RSI 在报告恢复上更可靠。</small></article><article><p className="showcase-kicker">LEARNING HEALTH</p><strong>{r.diagnostics.maintenanceErrors}</strong><span>RSI 经验维护错误</span><small>图查询 {r.diagnostics.graphLookupMs.toFixed(1)}ms · 本地选择 {r.diagnostics.compositionLocalMs.toFixed(1)}ms · 维护 {r.diagnostics.evolutionMaintenanceMs.toFixed(1)}ms。</small></article></section>
    <section className="limits"><AlertTriangle size={18} /><div><b>当前边界</b><p>{data.limitations.evolution} {data.limitations.judge}</p></div></section>
  </main>;
}

function AuditColumn({ label, value }: { label: string; value: Record<string, any> }) {
  const tests = [['结构化精确通过', 'strictStructuredPass'], ['指标精确', 'metricExact'], ['证据集合精确', 'evidenceExact'], ['本次观察证据', 'evidenceObserved'], ['严格报告审计', 'strictReportAuditPass'], ['数字主张可追溯', 'summaryNumbersGrounded'], ['金额单位明确', 'currencyNotationClear']];
  return <article><header><span>{label}</span><strong>{value.strictReportAuditPass}/{value.runs}</strong></header>{tests.map(([name, key]) => <div key={key}><span>{name}</span><b className={value[key] === value.runs ? 'pass' : 'warn'}>{value[key]}/{value.runs}</b></div>)}</article>;
}
