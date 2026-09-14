import { useEffect, useState } from "react";
import { api } from "./api";
import {
  arms,
  armLabel,
  n,
  tokens,
  rate,
  statusLabel,
  verifyRelease,
  measure,
} from "./releaseEvidence";
import type {
  Release,
  Evidence,
  PairDetail,
  Measure,
  Pair,
} from "./releaseEvidence";

const measureLabels: Record<Measure, string> = {
  tokens: "token 用量",
  modelRequests: "LLM 请求",
  durationMs: "串行延迟（秒）",
  success: "累计成功率",
};
function Chart({
  pairs,
  kind,
  onSelect,
}: {
  pairs: Pair[];
  kind: Measure;
  onSelect: (id: string) => void;
}) {
  const rows = pairs.filter(
    (p) => p.status === "completed" && p.runs.baseline && p.runs.rsi,
  );
  const series = arms.map((arm) => {
    let passed = 0;
    return rows.map((p, i) => {
      const v = measure(p.runs[arm], kind);
      if (kind === "success") {
        passed += v || 0;
        return passed / (i + 1);
      }
      return v == null ? null : kind === "durationMs" ? v / 1000 : v;
    });
  });
  const max = Math.max(
    kind === "success" ? 1 : 0,
    ...series.flat().filter((v): v is number => v != null),
    1,
  );
  const x = (i: number) => 50 + (i * 590) / Math.max(1, rows.length - 1),
    y = (v: number) => 164 - (130 * v) / max;
  return (
    <div className="evidence-chart">
      <svg viewBox="0 0 690 205" role="img" aria-label={measureLabels[kind]}>
        <line x1="50" x2="645" y1="164" y2="164" stroke="#bdcec7" />
        <text x="8" y="38">
          {kind === "success" ? "100%" : n(Math.ceil(max))}
        </text>
        <text x="24" y="169">
          0
        </text>
        {series.map((values, a) => (
          <g key={a} className={arms[a]}>
            <polyline
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              points={values
                .flatMap((v, i) => (v == null ? [] : [`${x(i)},${y(v)}`]))
                .join(" ")}
            />
            {values.map(
              (v, i) =>
                v != null && (
                  <g
                    key={rows[i].pairId}
                    role="button"
                    tabIndex={0}
                    aria-label={`${rows[i].title} ${armLabel[arms[a]]} ${kind === "success" ? rate(v) : n(v)}`}
                    onClick={() => onSelect(rows[i].pairId)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") onSelect(rows[i].pairId);
                    }}
                  >
                    <circle cx={x(i)} cy={y(v)} r="5" fill="currentColor" />
                    <title>
                      {rows[i].title}: {kind === "success" ? rate(v) : n(v)}
                    </title>
                  </g>
                ),
            )}
          </g>
        ))}
        {rows.map((p, i) => (
          <text key={p.pairId} x={x(i)} y="192" textAnchor="middle">
            任务{i + 1}
          </text>
        ))}
      </svg>
      <div className="chart-legend">
        <span className="baseline">● 基线</span>
        <span className="rsi">● RSI</span>
        <small>点击点查看同一任务；仅绘制已完成配对，失败保留。</small>
      </div>
    </div>
  );
}
function Copy({ text }: { text: string }) {
  return (
    <div className="business-copy">
      {text
        .split("\n")
        .map((line, i) =>
          line.startsWith("#") ? (
            <h4 key={i}>{line.replace(/^#+\s*/, "")}</h4>
          ) : line ? (
            <p key={i}>{line.replace(/\*\*/g, "")}</p>
          ) : null,
        )}
    </div>
  );
}
export default function CurrentEvidence() {
  const [release, setRelease] = useState<Release | null>(null),
    [data, setData] = useState<Evidence | null>(null),
    [pairId, setPairId] = useState(""),
    [detail, setDetail] = useState<PairDetail | null>(null),
    [arm, setArm] = useState<"baseline" | "rsi">("rsi"),
    [kind, setKind] = useState<Measure>("tokens"),
    [error, setError] = useState(""),
    [step, setStep] = useState(0);
  useEffect(() => {
    let live = true;
    void api<Release>("/api/releases/current")
      .then(async (r) => {
        if (!live) return;
        setRelease(r);
        const d = await api<Evidence>(
          `/api/releases/${encodeURIComponent(r.releaseId)}/evidence`,
        );
        verifyRelease(r, d.release);
        if (live) {
          setData(d);
          setPairId(d.pairs[0]?.pairId || "");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    setDetail(null);
    setError("");
    setStep(0);
    if (!release || !pairId) return;
    let live = true;
    void api<PairDetail>(
      `/api/releases/${encodeURIComponent(release.releaseId)}/pairs/${encodeURIComponent(pairId)}`,
    )
      .then((d) => {
        if (
          d.releaseId !== release.releaseId ||
          d.experimentId !== release.experimentId ||
          d.pairId !== pairId
        )
          throw new Error("任务与发布不一致");
        if (live) setDetail(d);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [release, pairId]);
  function select(id: string) {
    setPairId(id);
    document
      .getElementById("evidence-business")
      ?.scrollIntoView({ block: "start", behavior: "smooth" });
  }
  const run = detail?.runs[arm],
    events = run?.events || [],
    event = events[step],
    base = release
      ? `/api/releases/${encodeURIComponent(release.releaseId)}/pairs/${encodeURIComponent(pairId)}/runs/${arm}`
      : "";
  const title =
    release?.status === "formal"
      ? "当前正式发布证据"
      : "当前候选版本尚未完成正式对照";
  return (
    <main className="evidence-page">
      <header className="evidence-heading">
        <p className="eyebrow">当前证据</p>
        <h1>{title}</h1>
        <p>每项成果、修订与成本均来自下方指定的同一发布上下文。</p>
      </header>
      {release && (
        <section className="release-context" aria-label="发布清单">
          <div className="release-name">
            <h2>{release.displayName}</h2>
            <span className={`release-status ${release.status}`}>
              {release.status === "candidate"
                ? "候选 candidate"
                : release.status === "formal"
                  ? "正式 formal"
                  : "历史 historical"}
            </span>
          </div>
          <dl>
            <div>
              <dt>发布版本</dt>
              <dd>{release.releaseId}</dd>
            </div>
            <div>
              <dt>Git / runtime revision</dt>
              <dd>{release.runtimeRevision}</dd>
            </div>
            <div>
              <dt>实验 ID</dt>
              <dd>{release.experimentId}</dd>
            </div>
            <div>
              <dt>任务资产</dt>
              <dd>{release.assetVersion}</dd>
            </div>
            <div>
              <dt>运行协议</dt>
              <dd>
                {String(
                  release.protocol.runtimeProtocol ||
                    release.protocol.id ||
                    "清单内冻结协议",
                )}{" "}
                · 任务 / 模型 / 读取严格串行
              </dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>{release.createdAt}</dd>
            </div>
          </dl>
          <div className="claim-columns">
            <div>
              <h3>可主张结论</h3>
              <ul>
                {release.claims.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3>限制</h3>
              <ul>
                {release.limitations.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </div>
          </div>
          <details>
            <summary>技术审计 · 完整发布清单与协议</summary>
            <pre>{JSON.stringify(release, null, 2)}</pre>
          </details>
        </section>
      )}
      {error && (
        <p className="evidence-error" role="alert">
          {error}。当前证据不可用，不加载历史数据补足。
        </p>
      )}
      {!data && !error && <p>正在读取指定发布的保存证据…</p>}
      {data && (
        <>
          <section id="evidence-business" className="evidence-section">
            <header>
              <p className="eyebrow">01 · 任务与业务成果</p>
              <h2>先看实际完成了什么</h2>
              <p>
                计划 {data.plannedPairs} 对，已启动 {data.pairs.length}{" "}
                对。未启动的业务场景没有结果。
              </p>
            </header>
            <div className="evidence-business-layout">
              <aside aria-label="同发布任务">
                <div className="evidence-task-list">
                  {data.pairs.map((p, i) => (
                    <button
                      key={p.pairId}
                      className={pairId === p.pairId ? "selected" : ""}
                      onClick={() => setPairId(p.pairId)}
                    >
                      <small>任务 {i + 1}</small>
                      <strong>{p.title}</strong>
                      <span>
                        基线 {statusLabel(p.runs.baseline)} / RSI{" "}
                        {statusLabel(p.runs.rsi)}
                      </span>
                    </button>
                  ))}
                </div>
              </aside>
              <article className="evidence-result">
                {detail ? (
                  <>
                    <h3>{detail.task.title}</h3>
                    <details className="business-request" open>
                      <summary>业务问题与输入资料</summary>
                      <p>{detail.task.task}</p>
                      <div className="input-links">
                        {detail.inputs.map((s) => (
                          <a key={s.id} href={s.download} download>
                            {s.name} · {(s.sizeBytes / 1024).toFixed(1)} KB ↓
                          </a>
                        ))}
                      </div>
                      <p>
                        {detail.tables
                          .map((t) => `${t.sheet} ${t.rowCount} 行`)
                          .join(" · ")}
                      </p>
                    </details>
                    <div
                      className="arm-tabs"
                      role="group"
                      aria-label="查看对照成果"
                    >
                      {arms.map((a) => (
                        <button
                          key={a}
                          className={a === arm ? "selected" : ""}
                          onClick={() => {
                            setArm(a);
                            setStep(0);
                          }}
                        >
                          {armLabel[a]}
                        </button>
                      ))}
                    </div>
                    <p
                      className={
                        statusLabel(run) === "校验通过"
                          ? "result-pass"
                          : "result-fail"
                      }
                    >
                      {statusLabel(run)} · {run?.evaluation.issues?.join("、")}
                    </p>
                    {run?.submission ? (
                      <>
                        <Copy text={run.submission.summary} />
                        <div className="finding-grid">
                          {run.submission.groups?.map((g) => (
                            <article key={g.name}>
                              <h4>
                                {g.reason} <b>{g.count} 项</b>
                              </h4>
                              <small>{g.condition}</small>
                              <p className="business-ids">
                                {g.selectedIds.length
                                  ? g.selectedIds.join("、")
                                  : "0 项 · 无满足条件的对象"}
                              </p>
                              <details>
                                <summary>本组证据</summary>
                                <pre>{g.evidenceIds.join("\n")}</pre>
                              </details>
                            </article>
                          ))}
                        </div>
                        <div className="download-row">
                          <a href={base + "/report"} download>
                            下载业务报告 ↓
                          </a>
                          <a href={base + "/selection"} download>
                            下载结构化清单 ↓
                          </a>
                        </div>
                      </>
                    ) : (
                      <p>没有已保存的业务报告。</p>
                    )}
                  </>
                ) : (
                  <p>加载本次任务…</p>
                )}
              </article>
            </div>
          </section>
          <section className="evidence-section">
            <p className="eyebrow">02 · 为什么结果可信</p>
            <h2>
              {data.summary.qualityGate
                ? "结构化质量门槛通过"
                : "质量门槛尚未通过，保留每一次失败"}
            </h2>
            <p>
              相同任务、附件和通用工具，逐对交替串行执行。结果核对指标、业务
              ID、原因分组和实际观察证据；结构化通过不等于报告全文已独立审核。
            </p>
            <div className="evidence-facts">
              {arms.map((a) => {
                const m = data.summary.arms[a];
                return (
                  <a
                    key={a}
                    href="#evidence?view=replay"
                    onClick={() =>
                      document
                        .getElementById("evidence-replay")
                        ?.scrollIntoView()
                    }
                  >
                    <small>{armLabel[a]}</small>
                    <strong>
                      {m.passed}/{m.attempts}
                    </strong>
                    <span>
                      已启动任务通过 · {m.failedReportAttempts || 0} 次失败报告
                      · {m.toolErrors} 次工具错误/拒绝
                    </span>
                    <span>
                      恢复工具 {m.recoveryToolCalls || 0} 次 · 传输重试{" "}
                      {m.modelTransportRetries || 0} 次
                    </span>
                    <span>usage {m.usageComplete ? "完整" : "不完整"}</span>
                  </a>
                );
              })}
            </div>
          </section>
          <section className="evidence-section">
            <p className="eyebrow">03 · 图与匹配逻辑如何进化</p>
            <h2>修订必须经后续任务实际使用</h2>
            <div className="evolution-verdict">
              <p>
                图结构修订与后续使用：
                <strong>
                  {data.evolutionEvidence.graph
                    ? "已有同发布证据"
                    : "尚未获得证据"}
                </strong>
              </p>
              <p>
                匹配规则修订与后续行为：
                <strong>
                  {data.evolutionEvidence.matching
                    ? "已有同发布证据"
                    : "尚未获得证据"}
                </strong>
              </p>
            </div>
            <p>
              初次建图、支持度增长和经验命中不会计作进化。下列仅展示保存的实际修订。
            </p>
            <ol className="revision-list">
              {data.revisions.map((r) => (
                <li key={r.graphId}>
                  <button onClick={() => select(r.sourcePairId)}>
                    查看修订来源任务
                  </button>
                  <p>
                    {r.graphChanged ? "执行结构发生变化" : "执行结构未变化"}；
                    {r.matchingChanged
                      ? "匹配覆盖描述发生变化"
                      : "匹配描述未变化"}
                    。
                  </p>
                  {r.subsequentUses.length ? (
                    r.subsequentUses.map((u) => (
                      <button key={u.runId} onClick={() => select(u.pairId)}>
                        查看修订后实际使用
                      </button>
                    ))
                  ) : (
                    <strong>后续使用：尚未获得证据</strong>
                  )}
                  <details>
                    <summary>技术审计 · 图与匹配描述差异</summary>
                    <pre>{JSON.stringify(r, null, 2)}</pre>
                  </details>
                </li>
              ))}
            </ol>
            {!data.revisions.length && <p>尚未获得真实修订证据。</p>}
          </section>
          <section className="evidence-section">
            <p className="eyebrow">04 · 成本与可靠性</p>
            <h2>
              {data.summary.qualityGate
                ? "同一任务流的全量成本"
                : "当前成本记录，暂不作同质量收益结论"}
            </h2>
            <p>
              包括冷启动、匹配、学习、失败和恢复。每条曲线使用上述同一组任务；串行延迟为保存观察值。
            </p>
            <div
              className="measure-tabs"
              role="group"
              aria-label="选择成本或可靠性曲线"
            >
              {(Object.keys(measureLabels) as Measure[]).map((k) => (
                <button
                  key={k}
                  className={kind === k ? "selected" : ""}
                  onClick={() => setKind(k)}
                >
                  {measureLabels[k]}
                </button>
              ))}
            </div>
            <div className="evidence-facts">
              {arms.map((a) => {
                const m = data.summary.arms[a];
                return (
                  <button
                    key={a}
                    onClick={() => {
                      setArm(a);
                      document
                        .getElementById("evidence-replay")
                        ?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    <small>{armLabel[a]}</small>
                    <strong>
                      {kind === "tokens"
                        ? n(tokens(m))
                        : kind === "durationMs"
                          ? (m.durationMs / 1000).toFixed(1)
                          : kind === "success"
                            ? rate(
                                (m.passed || 0) / Math.max(1, m.attempts || 0),
                              )
                            : n(m.modelRequests)}
                    </strong>
                    <span>{measureLabels[kind]} · 点击查看逐任务来源</span>
                  </button>
                );
              })}
            </div>
            <Chart pairs={data.pairs} kind={kind} onSelect={select} />
            <p>
              累计净 token 差：{rate(data.summary.netTokenSaving)}。
              {!data.summary.qualityGate && "质量门槛失败，此数仅为诊断。"}
              全部已启动尝试计入上方总量。
            </p>
          </section>
          <section id="evidence-replay" className="evidence-section">
            <p className="eyebrow">05 · 逐任务真实轨迹与报告回放</p>
            <h2>每个数字都能回到同一次工作</h2>
            <div className="evidence-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>任务 / 方法</th>
                    <th>结果</th>
                    <th>token</th>
                    <th>LLM</th>
                    <th>工具</th>
                    <th>串行秒</th>
                    <th>来源</th>
                  </tr>
                </thead>
                <tbody>
                  {data.pairs.flatMap((p) =>
                    arms.map((a) => {
                      const r = p.runs[a];
                      return (
                        <tr key={p.pairId + a}>
                          <th>
                            {p.title}
                            <small>{armLabel[a]}</small>
                          </th>
                          <td>{statusLabel(r)}</td>
                          <td>{r ? n(tokens(r.metrics)) : "—"}</td>
                          <td>{r?.metrics.modelRequests ?? "—"}</td>
                          <td>{r?.metrics.toolCalls ?? "—"}</td>
                          <td>
                            {r ? (r.metrics.durationMs / 1000).toFixed(1) : "—"}
                          </td>
                          <td>
                            <button
                              onClick={() => {
                                setPairId(p.pairId);
                                setArm(a);
                                setStep(0);
                              }}
                            >
                              回放
                            </button>{" "}
                            <a
                              href={`/api/releases/${release?.releaseId}/pairs/${p.pairId}/runs/${a}/report`}
                              download
                            >
                              报告
                            </a>
                          </td>
                        </tr>
                      );
                    }),
                  )}
                </tbody>
              </table>
            </div>
            <h3>
              {detail?.task.title} · {armLabel[arm]}
            </h3>
            <p>
              保存轨迹回放，不是实时执行。运行 ID：<code>{run?.id || "—"}</code>
            </p>
            {events.length > 0 && (
              <>
                <div className="saved-step-controls">
                  <button
                    disabled={step === 0}
                    onClick={() => setStep((s) => s - 1)}
                  >
                    上一步
                  </button>
                  <input
                    aria-label="保存轨迹时间步"
                    type="range"
                    min={0}
                    max={events.length - 1}
                    value={step}
                    onChange={(e) => setStep(Number(e.target.value))}
                  />
                  <button
                    disabled={step >= events.length - 1}
                    onClick={() => setStep((s) => s + 1)}
                  >
                    下一步
                  </button>
                </div>
                <p>
                  步骤 {step + 1}/{events.length} ·{" "}
                  {(event?.elapsedMs / 1000).toFixed(1)} 秒 ·{" "}
                  {event?.type === "model"
                    ? "模型返回"
                    : event?.type === "action"
                      ? "执行工具"
                      : event?.type === "observation"
                        ? "获取结果"
                        : event?.type === "binding"
                          ? "绑定本次资料"
                          : event?.title}
                </p>
              </>
            )}
            <details>
              <summary>
                技术审计 · 当前事件、工具参数、完整轨迹与版本对象
              </summary>
              <pre>
                {JSON.stringify(
                  {
                    releaseId: release?.releaseId,
                    experimentId: release?.experimentId,
                    pairId,
                    event,
                    run,
                  },
                  null,
                  2,
                )}
              </pre>
              <a href={base}>读取同发布原始运行 JSON</a>
            </details>
          </section>
        </>
      )}
    </main>
  );
}
