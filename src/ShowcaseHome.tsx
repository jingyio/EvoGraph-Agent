import { ArrowUpRight, BadgeCheck, BrainCircuit, Clock3, Cpu, Route, Sparkles } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from './api';
import { SHOWCASE_EXPERIMENT, Showcase, duration, number, percent } from './showcase';
import './showcase.css';

export default function ShowcaseHome() {
  const [data, setData] = useState<Showcase | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { api<Showcase>(`/api/showcase/${SHOWCASE_EXPERIMENT}`).then(setData).catch(error => setError(error.message)); }, []);
  if (error) return <main className="showcase-page"><p className="showcase-error">读取最终实验失败：{error}</p></main>;
  if (!data) return <main className="showcase-page showcase-loading">正在加载保存的实验结果…</main>;
  const { baseline, rsi } = data.overview;
  const example = data.pairs.find(pair => pair.taskId === 'finance-cancelled_payments-02') || data.pairs[0];
  return <main className="showcase-page showcase-home">
    <section className="hero-stage">
      <div className="hero-copy"><p className="showcase-kicker">RSI AGENT LAB / SERIAL ONLINE EXPERIMENT</p><h1>同样完成业务任务。<br /><span>更少的模型开销。</span></h1><p className="hero-deck">将已验证的读取结构留在运行时，把重复规划从每个任务中拿掉。不是更少做事，而是少问一次模型。</p><div className="hero-actions"><a href="#compare" className="showcase-button dark">进入对比测试 <ArrowUpRight size={16} /></a><a href="#insights" className="showcase-button quiet">查看 RSI 效果</a></div></div>
      <div className="hero-number"><span>Agent token</span><strong>{percent(data.overview.tokenSavingRate)}</strong><p>539,468 <i>→</i> 347,368</p><small>固定 36 条 train 任务 · 串行 `1 / 1 / 1`</small></div>
    </section>
    <section className="hero-proof"><div><span>任务通过</span><strong>{rsi.passed}/{rsi.attempts}</strong><small>Baseline {baseline.passed}/{baseline.attempts}</small></div><div><span>LLM 请求</span><strong>{percent(data.overview.modelRequestSavingRate)}</strong><small>{baseline.modelRequests} <i>→</i> {rsi.modelRequests}</small></div><div><span>观察延迟</span><strong>{duration(rsi.durationMs)}</strong><small>交替串行观测，非 provider 因果结论</small></div><div><span>真实工具调用</span><strong>{number(rsi.toolCalls)}</strong><small>Baseline {number(baseline.toolCalls)} · 未靠少读工具取胜</small></div></section>
    <section className="showcase-section entrance-grid">
      <a href="#compare" className="entrance entrance-comparison"><div><Route size={22} /><p>对比测试</p><h2>同一任务<br />两条执行流</h2></div><span>36 个配对任务 <ArrowUpRight size={19} /></span></a>
      <a href="#insights" className="entrance entrance-insights"><div><BrainCircuit size={22} /><p>RSI 效果分析</p><h2>调用、token<br />与观察延迟</h2></div><span>经验形成与实际使用 <ArrowUpRight size={19} /></span></a>
    </section>
    <section className="showcase-section task-signal">
      <div className="section-intro"><p className="showcase-kicker">一个真实保存的任务对</p><h2>先看 Agent 做了什么。</h2><p>这里不是模拟动画。每一步均来自 `online-rsi-serial-final-v4` 的已保存轨迹。</p></div>
      <div className="task-signal-body"><div className="task-brief"><span>任务 {example.taskId}</span><h3>{example.familyLabel}</h3><p>{example.recordCount} 条公开历史记录。两臂面对同一任务、工具与预算。</p><a href={`#replay?task=${encodeURIComponent(example.taskId)}`}>打开逐步回放 <ArrowUpRight size={15} /></a></div><div className="signal-flow"><div><small>BASELINE</small><strong>{example.runs.baseline.metrics.modelRequests} 次模型</strong><p>Plan 后由模型继续决定每次读取。</p></div><i>→</i><div className="rsi-flow"><small>RSI</small><strong>{example.runs.rsi.metrics.modelRequests} 次模型</strong><p>当前任务数据绑定到已选读取图。</p></div></div></div>
    </section>
    <section className="showcase-section boundary-line"><div><BadgeCheck size={19} /><p><b>结构化质量没有回归。</b>两臂均 36/36 精确通过 metrics、入选 ID 与实际观察到的证据集合。</p></div><div><Cpu size={19} /><p><b>经济性来自真实对照。</b>工具调用 RSI 为 {rsi.toolCalls}，Baseline 为 {baseline.toolCalls}；没有把参数绑定直接换算成省一次 LLM。</p></div><div><Clock3 size={19} /><p><b>延迟单独保留边界。</b>{data.limitations.latency}</p></div></section>
    <section className="showcase-section final-call"><Sparkles size={20} /><div><p className="showcase-kicker">RSI 的当前可证明范围</p><h2>G0 Workflow 形成后，<br />24 次后续任务实际 Fast 复用。</h2></div><a href="#insights" className="showcase-button dark">查看经验链 <ArrowUpRight size={16} /></a></section>
  </main>;
}
