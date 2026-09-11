import { ArrowRight, ArrowUpRight, Bot, CheckCircle2, ChevronLeft, ChevronRight, CirclePlay, FileText, Headphones, Landmark, Pause, Play, ShieldCheck, Sparkles, Wrench } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { PairDetail, SHOWCASE_EXPERIMENT, Showcase, TimelineEvent, number, percent, total } from './showcase';
import './showcase.css';
import './employee-console.css';

type Scenario = 'finance' | 'support' | 'tickets';
type Capability = { scenario: Scenario; label: string; role: string; request: string; deliverable: string; icon: typeof Landmark };

const capabilities: Capability[] = [
  { scenario: 'finance', label: '财务分析', role: '财务运营', request: '请基于当前订单工作台，生成订单异常风险简报。', deliverable: '订单异常风险简报', icon: Landmark },
  { scenario: 'support', label: '客服分析', role: '客服运营', request: '请基于当前投诉工作台，生成投诉渠道与响应健康简报。', deliverable: '投诉渠道与响应健康简报', icon: Headphones },
  { scenario: 'tickets', label: '研发运营', role: '技术研发管理', request: '请基于当前 Issue 工作台，生成研发健康与待办简报。', deliverable: '研发健康与待办简报', icon: Wrench },
];

const toolLabels: Record<string, string> = {
  finance_list_orders: '查询订单状态', finance_get_order_payments: '核对支付记录', finance_get_order: '读取订单详情', finance_get_task_scope: '加载当前工作范围', finance_publish_report: '提交风险简报',
  support_list_complaints: '读取投诉记录', support_get_complaint: '核对投诉详情', support_count_values: '汇总投诉渠道', support_publish_report: '提交运营简报',
  tickets_list_issues: '读取 Issue 列表', tickets_get_labels: '核对 Issue 标签', tickets_get_task_scope: '加载当前工作范围', tickets_count_values: '汇总标签与待办', tickets_publish_report: '提交研发简报',
};

const metricLabels: Record<string, string> = {
  order_count: '异常订单', paid_cents: '风险金额', counts: '渠道统计', timely_count: '按时响应', late_count: '超时响应', unknown_count: '待确认', label_counts: '标签统计', unassigned_count: '未分配 Issue',
};

function readableMetric(key: string, value: unknown): string {
  if (typeof value === 'number') {
    if (key.endsWith('_cents')) {
      return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value / 100);
    }
    return number(value);
  }
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    const numeric = entries.every(([, item]) => typeof item === 'number');
    return numeric ? `${entries.length} 类 / ${number(entries.reduce((sum, [, item]) => sum + Number(item), 0))} 条` : `${entries.length} 项`;
  }
  return Array.isArray(value) ? `${value.length} 项` : String(value ?? '—');
}

function eventCopy(event: TimelineEvent, fast: boolean): { title: string; detail: string } {
  const tool = event.title.replace(/^调用工具：/, '').replace(/^获得观察：/, '');
  if (event.kind === 'graph_created') return { title: fast ? '已匹配历史分析流程' : '已建立当前分析流程', detail: '业务范围与读取依赖已进入可执行结构。' };
  if (event.kind === 'binding') return { title: '绑定本次业务记录', detail: '参数来自当前工作台观察，不复用旧业务值。' };
  if (event.kind === 'motif') return { title: '先筛选，再补查必要信息', detail: '没有进入结果集的记录不会触发无关详情读取。' };
  if (event.kind === 'action') return { title: toolLabels[tool] || tool, detail: event.executor === 'graph' ? 'RSI 运行时根据已确认结构调度。' : '模型决定下一步业务动作。' };
  if (event.kind === 'observation') return { title: `已获得${toolLabels[tool] || '业务数据'}`, detail: '当前观察已写入本次任务上下文。' };
  if (event.kind === 'plan') return fast
    ? { title: '载入历史分析流程', detail: '已保存的读取结构正在绑定本次业务范围。' }
    : { title: '理解业务需求与数据范围', detail: '确定需要读取的字段和依赖关系。' };
  if (event.kind === 'model_start') return { title: '模型正在整理业务结论', detail: '仅在需要业务判断或报告表达时请求模型。' };
  if (event.kind === 'model') return { title: '生成业务结论', detail: '把已验证的数据整理为简报。' };
  if (event.kind === 'evaluation') return { title: '核对简报与证据', detail: '检查指标、筛选结果和本次读取证据。' };
  if (event.kind === 'finished') return { title: '简报已交付', detail: '本次业务任务完成。' };
  return { title: event.title, detail: '已保存的实际执行事件。' };
}

function channelLabel(event: TimelineEvent | undefined, fast: boolean): string {
  if (fast && event?.kind === 'plan') return 'RSI 运行时';
  return event?.channel === 'model' ? '模型' : event?.channel === 'structured' ? 'RSI 运行时' : '核验';
}

export default function ShowcaseHome() {
  const [data, setData] = useState<Showcase | null>(null);
  const [details, setDetails] = useState<Record<string, PairDetail>>({});
  const [scenario, setScenario] = useState<Scenario>('finance');
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { api<Showcase>(`/api/showcase/${SHOWCASE_EXPERIMENT}`).then(setData).catch(reason => setError(reason.message)); }, []);
  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    Promise.all(data.sources.map(source => api<PairDetail>(`/api/showcase/${SHOWCASE_EXPERIMENT}/pairs/${encodeURIComponent(source.featuredTaskId)}`)))
      .then(items => { if (!cancelled) setDetails(Object.fromEntries(items.map(item => [item.taskId, item]))); })
      .catch(reason => { if (!cancelled) setError(reason.message); });
    return () => { cancelled = true; };
  }, [data]);

  const capability = capabilities.find(item => item.scenario === scenario) || capabilities[0];
  const category = useMemo(() => data?.categories.find(item => item.scenario === scenario), [data, scenario]);
  const detail = category ? details[category.featuredTaskId] : undefined;
  const timeline = detail?.runs.rsi.timeline || [];
  const maxStep = Math.max(0, timeline.length - 1);
  const event = timeline[Math.min(step, maxStep)];
  const isFast = detail?.runs.rsi.evolution?.planningPath === 'fast';
  useEffect(() => { setStep(0); setPlaying(false); }, [scenario]);
  useEffect(() => {
    if (!playing || !maxStep) return;
    const timer = window.setInterval(() => setStep(current => current >= maxStep ? (setPlaying(false), current) : current + 1), 760);
    return () => window.clearInterval(timer);
  }, [playing, maxStep]);

  if (error) return <main className="showcase-page"><p className="showcase-error">读取运营助手失败：{error}</p></main>;
  if (!data || !category || !detail) return <main className="showcase-page showcase-loading">正在准备运营助手的已验证工作记录…</main>;
  const report = detail.runs.rsi.report;
  const reportMetrics = Object.entries((report.metrics || {}) as Record<string, unknown>).slice(0, 4);
  const progress = event?.metrics || {};
  const completedSteps = timeline.slice(0, Math.min(step + 1, timeline.length)).slice(-5).reverse();
  const baselineTokens = total(detail.runs.baseline.metrics);
  const rsiTokens = total(detail.runs.rsi.metrics);
  const tokenSaving = baselineTokens ? 1 - rsiTokens / baselineTokens : null;
  const current = event ? eventCopy(event, Boolean(isFast)) : { title: '等待开始分析', detail: '选择一个业务能力，回放已验证的员工执行过程。' };
  return <main className="showcase-page console-page">
    <section className="console-hero">
      <div className="console-intro"><div className="console-avatar"><Bot size={25} /></div><p>ENTERPRISE OPERATION EMPLOYEE</p><h1>你好，我是企业运营数字员工。</h1><span>我可以在财务、客服和研发运营工作中复用已经验证过的分析流程。</span></div>
      <div className="console-request-card">
        <header><div><small>业务需求</small><strong>{capability.role}</strong></div><span>工作记录回放</span></header>
        <div className="console-capabilities">{capabilities.map(item => { const CapabilityIcon = item.icon; return <button key={item.scenario} className={item.scenario === scenario ? 'selected' : ''} onClick={() => setScenario(item.scenario)}><CapabilityIcon size={15} />{item.label}</button>; })}</div>
        <div className="console-request">{capability.request}</div>
        <footer><button className="console-start" onClick={() => setPlaying(current => !current)}>{playing ? <Pause size={16} /> : <Play size={16} />}{playing ? '暂停分析' : step >= maxStep ? '重新分析' : '开始分析'}</button><a href="#live">运行一次真实任务 <ArrowUpRight size={15} /></a></footer>
      </div>
    </section>

    <section className="console-workbench">
      <article className="console-execution">
        <header><div><p>正在处理</p><h2>{capability.deliverable}</h2></div><div className={`console-flow-state ${isFast ? 'reused' : ''}`}><Sparkles size={15} /><span>{isFast ? '已匹配历史经验' : '首次处理此类需求'}</span></div></header>
        <div className="console-current"><span className={isFast && event?.kind === 'plan' ? 'structured' : event?.channel || 'control'}>{channelLabel(event, Boolean(isFast))}</span><div><strong>{current.title}</strong><p>{current.detail}</p></div><b>{Math.min(step + 1, timeline.length)} / {timeline.length}</b></div>
        <div className="console-progress"><div className="console-progress-bar"><i style={{ width: `${timeline.length ? ((step + 1) / timeline.length) * 100 : 0}%` }} /></div><div className="console-controls"><button onClick={() => setStep(value => Math.max(0, value - 1))} aria-label="上一步" title="上一步"><ChevronLeft size={16} /></button><button onClick={() => setPlaying(value => !value)} aria-label={playing ? '暂停分析' : '开始分析'} title={playing ? '暂停' : '播放'}>{playing ? <Pause size={16} /> : <Play size={16} />}</button><button onClick={() => setStep(value => Math.min(maxStep, value + 1))} aria-label="下一步" title="下一步"><ChevronRight size={16} /></button><span>来自已保存的真实执行记录</span></div></div>
        <div className="console-activity">{completedSteps.map(saved => { const copy = eventCopy(saved, Boolean(isFast)); return <div key={saved.position}><CheckCircle2 size={15} /><span>{copy.title}</span><small>{channelLabel(saved, Boolean(isFast))}</small></div>; })}</div>
      </article>

      <aside className="console-runtime">
        <header><small>RSI RUNTIME</small><strong>本次工作方式</strong></header>
        <div className="console-runtime-status"><CirclePlay size={18} /><span>{isFast ? '历史 Workflow 已复用' : '当前任务流程已编译'}</span><small>{isFast ? '重复规划交给运行时。' : '首次需求形成可执行结构。'}</small></div>
        <div className="console-runtime-metrics"><div><b>{progress.modelRequests || 0}</b><span>LLM 请求</span></div><div><b>{number(total(progress))}</b><span>token</span></div><div><b>{progress.toolCalls || 0}</b><span>业务工具</span></div></div>
        <div className="console-compare"><small>同一业务需求的已验证对照</small><p><b>Baseline</b><span>{detail.runs.baseline.metrics.modelRequests} 次模型 · {number(baselineTokens)} token</span></p><p className="rsi"><b>RSI</b><span>{detail.runs.rsi.metrics.modelRequests} 次模型 · {number(rsiTokens)} token</span></p><strong>{percent(tokenSaving)} token</strong></div>
        <a href={`#replay?task=${encodeURIComponent(detail.taskId)}`}>查看可审计执行记录 <ArrowUpRight size={14} /></a>
      </aside>
    </section>

    <section className="console-output">
      <header><div><FileText size={20} /><div><p>业务产物</p><h2>{capability.deliverable}</h2></div></div><span><ShieldCheck size={15} />数据核验通过</span></header>
      <div className="console-output-grid"><div className="console-output-metrics">{reportMetrics.map(([key, value]) => <article key={key}><small>{metricLabels[key] || key}</small><strong>{readableMetric(key, value)}</strong></article>)}</div><div className="console-output-copy"><strong>简报已生成</strong><p>核心事实、筛选结果和本次读取证据已进入完整业务简报。</p><a href={detail.links.rsi.report} target="_blank" rel="noreferrer">打开完整简报 <ArrowUpRight size={15} /></a></div></div>
    </section>

    <section className="console-proof"><div><span>连续工作中</span><strong>24 次</strong><p>后续相似业务需求实际复用历史 Workflow。</p></div><div><span>模型请求</span><strong>{percent(data.overview.modelRequestSavingRate)}</strong><p>全量业务案例中的实际累计差值。</p></div><div><span>全量效率</span><strong>{percent(data.overview.tokenSavingRate)}</strong><p>固定业务案例下的累计 Agent token 差值。</p></div><a href="#compare"><span>验证与对照</span><strong>查看全部案例 <ArrowRight size={19} /></strong><p>成本、质量、执行记录与限制。</p></a></section>
  </main>;
}
