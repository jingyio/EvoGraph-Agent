import { useEffect, useState } from "react";
import { Layers3 } from "lucide-react";
import WorkspaceWorkbench from "./WorkspaceWorkbench";
import DataAnalysis from "./DataAnalysis";
import Archive from "./Archive";
import { canonicalHash } from "./navigation";
import "./release.css";
function locationHash() {
  const hash = canonicalHash(window.location.hash);
  if (hash !== window.location.hash)
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search + hash,
    );
  return hash;
}
export default function App() {
  const [hash, setHash] = useState(locationHash);
  useEffect(() => {
    const changed = () => setHash(locationHash());
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  const page = hash.slice(1).split("?")[0];
  return (
    <div className="release-shell">
      <header className="release-nav">
        <a className="release-brand" href="#home">
          <Layers3 size={22} />
          <span>
            数字员工<span>企业运营工作台</span>
          </span>
        </a>
        <nav aria-label="主导航">
          <a href="#home" aria-current={page === "home" ? "page" : undefined}>
            实测对比
          </a>
          <a
            href="#analysis"
            aria-current={page === "analysis" ? "page" : undefined}
          >
            数据分析
          </a>
        </nav>
      </header>
      {page === "home" ? (
        <WorkspaceWorkbench />
      ) : page === "analysis" ? (
        <DataAnalysis />
      ) : (
        <Archive key={hash} />
      )}
      <footer className="release-footer">
        <span>业务成果与每次实际执行关联保存</span>
        <details>
          <summary>开发与历史</summary>
          <a href="#archive">打开历史实验与技术审计 →</a>
        </details>
      </footer>
    </div>
  );
}
