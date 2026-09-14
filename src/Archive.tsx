import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "./api";
import { ArchiveExperimentContext } from "./archiveContext";
import type { Release } from "./releaseEvidence";
const pages = {
  candidate: lazy(() => import("./CurrentEvidence")),
  experiments: lazy(() => import("./WorkpackExperimentPanel")),
  trajectory: lazy(() => import("./TrajectoryPanel")),
  compare: lazy(() => import("./CompareExperience")),
  insights: lazy(() => import("./RsiInsights")),
  replay: lazy(() => import("./TaskReplay")),
  showcase: lazy(() => import("./ShowcaseHome")),
  live: lazy(() => import("./LiveComparison")),
  demo: lazy(() => import("./ExecutionDemo")),
  evaluation: lazy(() => import("./EvaluationPanel")),
  evolution: lazy(() => import("./OnlineEvolutionPanel")),
  taskbank: lazy(() => import("./TaskBankPanel")),
  platforms: lazy(() => import("./PlatformPanel")),
};
const names: Record<string, string> = {
  candidate: "当前候选审阅",
  experiments: "工作包历史实验",
  trajectory: "轨迹候选与失败预检",
  compare: "36-task 历史对比",
  insights: "36-task 历史指标",
  replay: "36-task 历史回放",
  showcase: "旧展示",
  live: "现场会话开发",
  demo: "旧执行调试",
  evaluation: "历史成对评测",
  evolution: "旧经验库",
  taskbank: "任务库开发",
  platforms: "平台只读开发",
};
const origins: Record<string, string> = {
  candidate: "Release Manifest 当前候选 · 题面、工具与失败证据审阅",
  evaluation: "evaluations + taskbank/runs · 逐项选择的历史评测协议",
  evolution: "taskbank/evolution · 旧任务库经验协议",
  taskbank: "taskbank/manifest + tasks · 原任务库资产与工具契约",
  platforms: "runs + tools · ERPNext/Zammad 平台只读协议",
  demo: "taskbank/runs · query参数指定的任务与run",
  live: "live-showcase · 已保存会话或显式启动的开发流程",
};
type Row = Release & { href: string; experimentStatus?: string };
export default function Archive() {
  const [data, setData] = useState<{
      items: Row[];
      legacyRelease: Release;
      legacyRoutes: Record<string, Release>;
    } | null>(null),
    [error, setError] = useState("");
  const query = new URLSearchParams(window.location.hash.split("?")[1] || ""),
    page = query.get("page") || "",
    experiment = query.get("experiment") || "";
  useEffect(() => {
    let active = true;
    void api<{
      items: Row[];
      legacyRelease: Release;
      legacyRoutes: Record<string, Release>;
    }>("/api/releases/archive")
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    const mapped = data?.legacyRoutes[page];
    if (mapped && !experiment && ["experiments", "trajectory"].includes(page)) {
      const q = new URLSearchParams(window.location.hash.split("?")[1] || "");
      q.set("experiment", mapped.experimentId);
      window.location.hash = "archive?" + q.toString();
    }
  }, [data, page, experiment]);
  const legacy = ["compare", "insights", "replay", "showcase"].includes(page);
  const selected =
    data?.items.find((i) => i.experimentId === experiment) ||
    (legacy ? data?.legacyRelease : undefined);
  const Component = pages[page as keyof typeof pages];
  return (
    <main className="archive-page">
      <header>
        <p className="eyebrow">开发与历史</p>
        <h1>历史保留，数据分析独立</h1>
        <p>
          这里的实验、候选和调试工具不进入所选分析测试组的指标。原始记录不删除、不改写。
        </p>
        <a href="#analysis">返回数据分析 →</a>
      </header>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p>正在读取历史目录…</p>}
      {data && (
        <>
          <details className="archive-catalog">
            <summary>
              展开历史实验目录 · {data.items.length} 个保存上下文
            </summary>
            <div className="archive-records">
              {data.items.map((row) => (
                <article key={row.experimentId}>
                  <h3>{row.displayName}</h3>
                  <span>
                    {row.status} · {row.experimentStatus || "历史记录"}
                  </span>
                  <dl>
                    <dt>实验</dt>
                    <dd>{row.experimentId}</dd>
                    <dt>runtime</dt>
                    <dd>{row.runtimeRevision}</dd>
                    <dt>任务资产</dt>
                    <dd>{row.assetVersion}</dd>
                    <dt>协议</dt>
                    <dd>
                      {String(
                        row.protocol.id ||
                          row.protocol.runtimeProtocol ||
                          "原始保存协议",
                      )}
                    </dd>
                  </dl>
                  <a href={row.href}>打开独立历史记录 →</a>
                </article>
              ))}
            </div>
          </details>
          <details className="archive-catalog">
            <summary>展开开发工具与旧审计深链</summary>
            <div className="archive-tool-links">
              {Object.entries(names).map(([key, label]) => (
                <a
                  key={key}
                  href={`#archive?page=${key}${["compare", "insights", "replay", "showcase"].includes(key) ? "&release=" + data.legacyRelease.releaseId : ""}`}
                >
                  {label}
                </a>
              ))}
              <a
                href="/api/online-e2e/online-rsi-all-train-saturation-v3/report"
                target="_blank"
                rel="noreferrer"
              >
                V3 冷启动诊断 · 单独原始历史报告
              </a>
            </div>
          </details>
          {Component && (
            <section className="archive-context">
              <a href="#archive">← 历史目录</a>
              <h2>{names[page]}</h2>
              <p>
                状态：{selected?.status || "historical / development"} ·{" "}
                {selected && "experimentStatus" in selected
                  ? String(selected.experimentStatus)
                  : "独立历史上下文"}
              </p>
              <dl>
                <dt>版本 / 实验</dt>
                <dd>
                  {selected
                    ? `${selected.displayName} / ${selected.experimentId}`
                    : "开发页：未绑定单一发布，按页内所选记录审计"}
                </dd>
                <dt>runtime</dt>
                <dd>
                  {selected?.runtimeRevision ||
                    "未统一记录；查看所选运行的原始元数据，不代表当前发布runtime"}
                </dd>
                <dt>任务资产</dt>
                <dd>
                  {selected?.assetVersion ||
                    (page === "platforms"
                      ? "平台只读资料"
                      : "旧任务库 / 多协议历史资产")}
                </dd>
                <dt>协议 / 数据来源</dt>
                <dd>
                  {selected
                    ? String(
                        selected.protocol.id ||
                          selected.protocol.runtimeProtocol ||
                          "冻结原始协议",
                      )
                    : origins[page] ||
                      "需在历史目录显式选择实验；未选择时不加载结果"}
                </dd>
              </dl>
              <details className="archive-view" open>
                <summary>历史页面与技术审计 · {names[page]}</summary>
                <ArchiveExperimentContext.Provider
                  value={legacy ? data.legacyRelease.experimentId : ""}
                >
                  <Suspense fallback={<p>加载历史页面…</p>}>
                    {["experiments", "trajectory"].includes(page) &&
                    !experiment ? (
                      <p>正在定位旧链接指定的历史发布…</p>
                    ) : (
                      <Component key={page + experiment} />
                    )}
                  </Suspense>
                </ArchiveExperimentContext.Provider>
              </details>
            </section>
          )}
        </>
      )}
    </main>
  );
}
