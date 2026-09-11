import { useEffect, useState } from 'react';
import { BarChart3, Database, GitBranch, Layers3, Play, PlugZap, ShieldCheck } from 'lucide-react';
import CompareExperience from './CompareExperience';
import EmployeeExperience from './EmployeeExperience';
import ExecutionDemo from './ExecutionDemo';
import EvaluationPanel from './EvaluationPanel';
import OnlineEvolutionPanel from './OnlineEvolutionPanel';
import TaskBankPanel from './TaskBankPanel';
import PlatformPanel from './PlatformPanel';
import RsiInsights from './RsiInsights';
import ShowcaseHome from './ShowcaseHome';
import TaskReplay from './TaskReplay';
import LiveComparison from './LiveComparison';

const pages = { home: '概览', employees: '数字员工', compare: '对比测试', live: '在线对照', insights: 'RSI 效果分析', replay: '任务回放', demo: '历史执行工作台', evaluation: '成对评测与成果', evolution: '随任务进化', taskbank: '真实数据任务库', platforms: '平台只读工作台' };
type Page = keyof typeof pages;
const primaryPages = ['home', 'employees', 'compare', 'live', 'insights', 'replay'] as const;
const legacyPages = ['demo', 'evaluation', 'evolution', 'taskbank', 'platforms'] as const;
function fromHash(): Page { const key = window.location.hash.slice(1).split('?')[0]; return key in pages ? key as Page : 'home'; }
export default function App() {
  const [page, setPage] = useState<Page>(fromHash);
  useEffect(() => { const change = () => setPage(fromHash()); window.addEventListener('hashchange', change); return () => window.removeEventListener('hashchange', change); }, []);
  const navigate = (next: Page) => { window.location.hash = next; };
  if ((primaryPages as readonly Page[]).includes(page)) return <div className="showcase-shell"><header className="showcase-nav"><a href="#home" className="showcase-brand"><Layers3 size={18} /><span>RSI</span><small>AGENT LAB</small></a><nav>{primaryPages.map(key => <a key={key} href={`#${key}`} className={page === key ? 'active' : ''}>{pages[key]}</a>)}</nav><a href="#demo" className="nav-lab">实验工作台 <BarChart3 size={14} /></a></header>{page === 'home' && <ShowcaseHome />}{page === 'employees' && <EmployeeExperience />}{page === 'compare' && <CompareExperience />}{page === 'live' && <LiveComparison />}{page === 'insights' && <RsiInsights />}{page === 'replay' && <TaskReplay />}</div>;
  const icons: Record<(typeof legacyPages)[number], typeof Play> = { demo: Play, evaluation: ShieldCheck, evolution: GitBranch, taskbank: Database, platforms: PlugZap };
  return <div className="app-shell legacy-shell"><aside className="sidebar"><a className="brand" href="#home"><span className="brand-icon"><Layers3 size={22} /></span><span>数字员工<span className="brand-sub">OPERATIONS LAB</span></span></a><div className="workspace-label">工作空间 <span>GRAPH RSI</span></div><div className="nav-label">实验工作台</div>{legacyPages.map(key => { const Icon = icons[key]; return <button key={key} className={`nav-item ${page === key ? 'active' : ''}`} onClick={() => navigate(key)}><Icon size={18} />{pages[key]}</button>; })}<div className="sidebar-bottom"><div className="small-logo">R</div><div>Python 执行器<small>真实数据 · 可追溯执行</small></div></div></aside><div className="main-shell"><header className="topbar"><div>工作空间 / {pages[page]}</div><a href="#home">返回主展示</a></header><main>{page === 'demo' && <ExecutionDemo />}{page === 'evaluation' && <EvaluationPanel />}{page === 'evolution' && <OnlineEvolutionPanel />}{page === 'taskbank' && <TaskBankPanel />}{page === 'platforms' && <PlatformPanel />}</main></div></div>;
}
