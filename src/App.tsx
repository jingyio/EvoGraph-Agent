import { useEffect, useState } from 'react';
import { Database, GitBranch, Layers3, Play, PlugZap, ShieldCheck } from 'lucide-react';
import ExecutionDemo from './ExecutionDemo';
import EvaluationPanel from './EvaluationPanel';
import OnlineEvolutionPanel from './OnlineEvolutionPanel';
import TaskBankPanel from './TaskBankPanel';
import PlatformPanel from './PlatformPanel';
const pages = { demo: 'Agent 执行演示', evaluation: '成对评测与成果', evolution: '随任务进化', taskbank: '真实数据任务库', platforms: '平台只读工作台' };
type Page = keyof typeof pages;
function fromHash(): Page { const key = window.location.hash.slice(1); return key in pages ? key as Page : 'demo'; }
export default function App() {
  const [page, setPage] = useState<Page>(fromHash);
  useEffect(() => { const change = () => setPage(fromHash()); window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change); }, []);
  useEffect(() => { window.history.replaceState(null, '', '#' + page); }, [page]);
  const icons = { demo: Play, evaluation: ShieldCheck, evolution: GitBranch, taskbank: Database, platforms: PlugZap };
  return <div className="app-shell"><aside className="sidebar"><a className="brand" href="#demo"><span className="brand-icon"><Layers3 size={22} /></span><span>数字员工<span className="brand-sub">OPERATIONS LAB</span></span></a><div className="workspace-label">工作空间 <span>GRAPH RSI</span></div><div className="nav-label">项目入口</div>{(Object.keys(pages) as Page[]).map(key => { const Icon = icons[key]; return <button key={key} className={`nav-item ${page === key ? 'active' : ''}`} onClick={() => setPage(key)}><Icon size={18} />{pages[key]}</button>; })}<div className="sidebar-bottom"><div className="small-logo">R</div><div>Python 执行器<small>真实数据 · 可追溯执行</small></div></div></aside><div className="main-shell"><header className="topbar"><div>工作空间 / {pages[page]}</div><span>本地实验环境</span></header><main>{page === 'demo' && <ExecutionDemo />}{page === 'evaluation' && <EvaluationPanel />}{page === 'evolution' && <OnlineEvolutionPanel />}{page === 'taskbank' && <TaskBankPanel />}{page === 'platforms' && <PlatformPanel />}</main></div></div>;
}
