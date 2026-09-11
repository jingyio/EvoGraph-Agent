import { ArrowRight, ArrowUpRight, BadgeCheck, BriefcaseBusiness, ChartNoAxesCombined, ClipboardCheck, FileText, Headphones, Landmark, ShieldAlert, Wrench } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { PairDetail, ScenarioGroup, SHOWCASE_EXPERIMENT, Showcase, duration, number, percent, shorterTool, total } from './showcase';
import './employee-experience.css';

type Role = {
  scenario: 'finance' | 'support' | 'tickets';
  name: string;
  englishName: string;
  deliverable: string;
  intent: string;
  icon: typeof Landmark;
};

const roles: Role[] = [
  { scenario: 'finance', name: '财务运营助手', englishName: 'Finance Operations', deliverable: '订单异常与支付风险简报', intent: '核对取消订单、支付金额与分期风险', icon: Landmark },
  { scenario: 'support', name: '客服运营分析师', englishName: 'Customer Operations', deliverable: '投诉渠道与响应健康简报', intent: '分析投诉来源与响应状态', icon: Headphones },
  { scenario: 'tickets', name: '技术研发管理助手', englishName: 'Engineering Operations', deliverable: 'Issue 健康与待办简报', intent: '整理工单标签、分配状态与待办', icon: Wrench },
];

function metricValue(key: string, value: unknown): string {
  if (typeof value === 'number') return key.endsWith('_cents') ? `${number(value)} BRL cents` : number(value);
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return `${value.length} 项`;
  if (value && typeof value === 'object') return Object.values(value as Record<string, unknown>).every(item => typeof item === 'number')
    ? number(Object.values(value as Record<string, number>).reduce((sum, item) => sum + item, 0))
    : '已生成';
  return '—';
}

function metricLabel(key: string): string {
  const labels: Record<string, string> = {
    order_count: '符合条件的订单', paid_cents: '关联支付额', cancelledCount: '取消订单', cancelledPaymentCents: '取消支付额', installmentCount: '分期订单',
    channels: '投诉渠道', complaintCount: '投诉记录', timely_count: '按时响应', late_count: '超时响应', unknown_count: '未知状态',
    labels: '工单标签', issueCount: 'Issue 数', unassignedCount: '未分配',
  };
  return labels[key] || key.replace(/([A-Z])/g, ' $1').trim();
}

function RoleIcon({ role, size = 20 }: { role: Role; size?: number }) {
  const Icon = role.icon;
  return <Icon size={size} />;
}

export default function EmployeeExperience() {
  const [data, setData] = useState<Showcase | null>(null);
  const [details, setDetails] = useState<Record<string, PairDetail>>({});
  const [selectedScenario, setSelectedScenario] = useState<Role['scenario']>('finance');
  const [error, setError] = useState('');

  useEffect(() => {
    api<Showcase>(`/api/showcase/${SHOWCASE_EXPERIMENT}`).then(setData).catch(reason => setError(reason.message));
  }, []);

  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    const requested = data.sources.map(source => source.featuredTaskId);
    Promise.all(requested.map(taskId => api<PairDetail>(`/api/showcase/${SHOWCASE_EXPERIMENT}/pairs/${encodeURIComponent(taskId)}`)))
      .then(items => { if (!cancelled) setDetails(Object.fromEntries(items.map(item => [item.taskId, item]))); })
      .catch(reason => { if (!cancelled) setError(reason.message); });
    return () => { cancelled = true; };
  }, [data]);

  const selectedRole = roles.find(role => role.scenario === selectedScenario) || roles[0];
  const category = useMemo(() => data?.categories.find(item => item.scenario === selectedRole.scenario), [data, selectedRole]);
  const detail = category ? details[category.featuredTaskId] : undefined;
  if (error) return <main className="showcase-page"><p className="showcase-error">读取数字员工展示失败：{error}</p></main>;
  if (!data || !category) return <main className="showcase-page showcase-loading">正在连接已保存的岗位任务与业务简报…</main>;
  const baseline = category.metrics.baseline;
  const rsi = category.metrics.rsi;
  const report = detail?.runs.rsi.report || {};
  const reportMetrics = Object.entries((report.metrics || {}) as Record<string, unknown>).slice(0, 4);
  const graphTools = detail?.runs.rsi.graphNodes.map(node => shorterTool(node.tool)) || [];
  const isFast = detail?.runs.rsi.evolution?.planningPath === 'fast';

  return <main className="showcase-page employee-page">
    <section className="employee-hero">
      <div>
        <p className="showcase-kicker">ENTERPRISE OPERATION ANALYST / PRODUCT LAYER</p>
        <h1>把重复的业务分析，<br /><span>交给一个能复用经验的数字员工。</span></h1>
        <p>三种岗位共享同一条可审计执行底座：读取业务记录、筛选和分析、输出有证据的业务简报。这里展示的是已保存的真实运行，不是另造的演示任务。</p>
      </div>
      <aside>
        <BriefcaseBusiness size={23} />
        <small>STRICT EVIDENCE</small>
        <strong>{data.coverage.experimentTaskCount} 个任务对</strong>
        <span>三大岗位领域 · 串行 1 / 1 / 1</span>
      </aside>
    </section>

    <section className="employee-role-grid" aria-label="三类业务数字员工">
      {roles.map(role => {
        const item = data.categories.find(candidate => candidate.scenario === role.scenario)!;
        const active = role.scenario === selectedRole.scenario;
        return <button key={role.scenario} className={active ? 'active' : ''} onClick={() => setSelectedScenario(role.scenario)}>
          <RoleIcon role={role} />
          <small>{role.englishName.toUpperCase()}</small>
          <strong>{role.name}</strong>
          <span>{role.deliverable}</span>
          <b>{percent(item.finalSavingRate)} token</b>
          <em>{item.taskCount} 个固定任务 · 点击查看</em>
        </button>;
      })}
    </section>

    <section className="employee-workspace">
      <header>
        <div><p className="showcase-kicker">ROLE WORKSPACE / RECORDED BUSINESS CASE</p><h2>{selectedRole.name}<br />正在交付：{selectedRole.deliverable}</h2></div>
        <div className="employee-state"><span>{isFast ? '历史 Workflow 已实际复用' : '首次到达：当前任务临时编译'}</span><small>{detail ? detail.taskId : '读取保存轨迹中'}</small></div>
      </header>
      <div className="employee-workspace-grid">
        <article className="employee-request">
          <small>业务请求</small>
          <strong>{detail?.task.task || selectedRole.intent}</strong>
          <p>{detail?.recordCount || category.taskCount} 条本次任务范围记录；业务 ID 和工具参数只来自当前读取观察。</p>
          <div><span>公开历史数据</span><span>只读工具</span><span>Schema 校验</span></div>
        </article>
        <article className="employee-flow">
          <small>实际执行结构</small>
          <div className="employee-flow-steps"><span>任务范围<br /><b>读取</b></span><ArrowRight size={16} />{graphTools.length ? graphTools.slice(0, 3).map((tool, index) => <span key={`${tool}-${index}`}><b>{tool}</b><br />当前参数绑定</span>) : <span><b>模型</b><br />动态读取</span>}<ArrowRight size={16} /><span>业务<br /><b>简报</b></span></div>
          <p>{isFast ? '该任务直接使用保存的读取结构；完整 Plan 请求为零。' : '该任务保留当前计划生成，尚未使用历史 Workflow。'}</p>
        </article>
        <article className="employee-brief">
          <header><div><FileText size={17} /><small>实际提交的业务简报</small></div>{detail && <a href={detail.links.rsi.report} target="_blank" rel="noreferrer">打开可打印简报 <ArrowUpRight size={14} /></a>}</header>
          <div className="employee-metric-cards">{reportMetrics.length ? reportMetrics.map(([key, value]) => <div key={key}><small>{metricLabel(key)}</small><strong>{metricValue(key, value)}</strong></div>) : <p>正在载入实际提交指标…</p>}</div>
          <p>{typeof report.summary === 'string' ? report.summary : '报告摘要正在载入。'}</p>
        </article>
      </div>
    </section>

    <section className="employee-economy">
      <header><div><p className="showcase-kicker">SAME ROLE TASKS / MATCHED SERIAL COMPARISON</p><h2>岗位成果不变，<br />把模型预算留给真正的业务判断。</h2></div><span>领域汇总 · {category.taskCount} 个固定任务</span></header>
      <div className="employee-economy-grid">
        <MetricPair label="Agent token" baseline={baseline.totalTokens} rsi={rsi.totalTokens} suffix="token" />
        <MetricPair label="LLM 请求" baseline={baseline.modelRequests} rsi={rsi.modelRequests} suffix="次" />
        <MetricPair label="真实工具调用" baseline={baseline.toolCalls} rsi={rsi.toolCalls} suffix="次" />
        <MetricPair label="累计观察时长" baseline={baseline.durationMs / 1000} rsi={rsi.durationMs / 1000} suffix="s" precision={1} />
      </div>
      <div className="employee-economy-foot"><BadgeCheck size={17} /><p>两臂都通过结构化 metrics、入选记录和本次观察到的证据集合。时长是分时交替串行的观测，不当作供应商性能因果结论。</p><a href="#compare">查看 36 个同任务对比 <ArrowUpRight size={15} /></a></div>
    </section>

    <section className="employee-evidence-chain">
      <div><p className="showcase-kicker">WHAT THE BENCHMARK PROVES</p><h2>实验层和产品层，<br />使用同一份真实证据。</h2></div>
      <div className="employee-chain"><span>正常 train 任务<br /><b>形成 G0 Workflow</b></span><ArrowRight size={18} /><span>后续同族新记录<br /><b>当前参数绑定</b></span><ArrowRight size={18} /><span>Fast 路径执行<br /><b>24 次实际完成</b></span></div>
      <p>已证明在线初始 Workflow 积累与复用；未观察到 G1/G2 结构修订或 Composition 实际执行，不将其包装为多代自主进化。</p>
    </section>

    <section className="employee-boundary">
      <ShieldAlert size={19} /><div><b>落地边界</b><p>岗位叙事映射自财务、客服与技术运营的真实工作形态。底层数据为公开历史数据，经任务隔离的本地只读 JSON Schema 工具访问；本展示不等同于生产 ERP、CRM 或工单系统的实时写入部署。</p></div>
      <a href="#replay">打开逐任务执行回放 <ArrowUpRight size={15} /></a>
    </section>
  </main>;
}

function MetricPair({ label, baseline, rsi, suffix, precision = 0 }: { label: string; baseline: number; rsi: number; suffix: string; precision?: number }) {
  const saving = baseline ? 1 - rsi / baseline : null;
  const value = (item: number) => precision ? item.toFixed(precision) : number(item);
  return <article><small>{label}</small><strong>{percent(saving)}</strong><p>{value(baseline)} <ArrowRight size={13} /> {value(rsi)} {suffix}</p><span>Baseline <b>→</b> RSI</span></article>;
}
