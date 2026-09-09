import { useEffect, useState } from 'react';
import { GitBranch, RefreshCw, ArrowDownToLine } from 'lucide-react';
import { api } from './api';
import type { AgentRun } from '../shared/types';
type Motif = { id: string; sourceRunId: string; sourceRunStatus: string; failureEventSeq: number; repairEventSeq: number; reflection: string; nodes: { id: string; kind: string; dependencies: string[]; path?: string[]; sourceEventSeqs: number[] }[]; validation: { toolCalls: number; scope: string } };
type Reflection = { motifs: Motif[]; unexplainedFailures: { eventSeq: number; tool: string; error: string }[]; note?: string };

export default function NegativeMotifPanel({ run }: { run: AgentRun | null }) {
  const [motifs, setMotifs] = useState<Motif[]>([]);
  const [selection, setSelection] = useState('');
  const [result, setResult] = useState<Reflection | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { let cancelled = false; api<Motif[]>('/api/negative-motifs').then(v => { if (!cancelled) setMotifs(v); }).catch(e => { if (!cancelled) setError(e.message); }); return () => { cancelled = true; }; }, []);
  async function reflect() {
    if (!run) return;
    setBusy(true); setError('');
    try {
      setResult(await api<Reflection>(`/api/runs/${run.id}/reflect`, { method: 'POST', body: '{}' }));
      setMotifs(await api<Motif[]>('/api/negative-motifs'));
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const motif = motifs.find(m => m.id === selection) || motifs[0];
  const labels = ['本次回款数据', 'bankRef → entityId', '工具拒绝', 'id → entityId', '局部调用成功'];
  return <div className="negative-workspace">
    <div className="page-heading"><h1>负 Motif · 失败反思</h1><button className="button primary" disabled={busy || !run || run.status === 'running' || run.request.mode !== 'live'} onClick={() => void reflect()}><RefreshCw size={16} />分析当前轨迹</button></div>
    <p>当前运行：{run?.id || '未选择'} · 已验证 {motifs.length} 条局部修复经验</p>
    {error && <p role="alert">{error}</p>}
    {result && <p>提取 {result.motifs.length} 条；待分析错误 {result.unexplainedFailures.length} 条。{result.note}</p>}
    {result?.unexplainedFailures.map(f => <p key={f.eventSeq}>事件 {f.eventSeq} · {f.tool} · 待反思：{f.error}</p>)}
    {!motif ? <p>尚无局部验证通过的负 motif。</p> : <>
      <label>经验来源 <select value={motif.id} onChange={e => setSelection(e.target.value)}>{motifs.map(m => <option key={m.id} value={m.id}>{m.sourceRunId.slice(0, 8)} · 失败事件 {m.failureEventSeq}</option>)}</select></label>
      <p>{motif.reflection}</p>
      <div className="graph-canvas"><svg role="img" aria-label="负 motif 数据依赖与修复图" width="100%" style={{ minWidth: 760 }} viewBox="0 0 1060 200">
        <defs><marker id="negative-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10z" fill="#667085" /></marker></defs>
        {motif.nodes.flatMap((n, i) => n.dependencies.map(dep => { const j = motif.nodes.findIndex(m => m.id === dep); return <path key={`${dep}-${n.id}`} d={i - j > 1 ? `M${j * 208 + 110},55 Q${(i + j) * 104 + 110},0 ${i * 208 + 110},55` : `M${j * 208 + 200},85 L${i * 208 + 20},85`} fill="none" stroke="#667085" markerEnd="url(#negative-arrow)" />; }))}
        {motif.nodes.map((n, i) => <g key={n.id} transform={`translate(${i * 208 + 20},55)`}><rect width="180" height="72" rx="6" fill={i === 2 ? '#fff0f0' : '#f5f7fa'} stroke={i === 2 ? '#c83e4d' : '#b8c1cd'} /><text x="10" y="28" fontSize="14">{labels[i]}</text><text x="10" y="53" fontSize="12" fill="#667085">来源事件 {n.sourceEventSeqs.join(', ')}</text></g>)}
      </svg></div>
      <p><GitBranch size={15} /> 原任务状态：{motif.sourceRunStatus} · 隔离重放：{motif.validation.toolCalls} 次工具调用 · 额外 LLM：0</p>
      <p>{motif.validation.scope}</p>
      {run?.negativeMotif && <p>本次加载 {run.negativeMotif.loadedIds.length} 条 · 前置拒绝 {run.negativeMotif.guardHits} 次（仍计入错误与尝试次数）</p>}
      <a href={`/api/runs/${motif.sourceRunId}/export/json`} className="text-button"><ArrowDownToLine size={15} />原始来源轨迹</a>
      <details><summary>图结构与验证证据</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(motif, null, 2)}</pre></details>
    </>}
  </div>;
}
