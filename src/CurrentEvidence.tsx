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
  CurvePoint,
  SavingMeasure,
  Revision,
} from "./releaseEvidence";

const measureLabels: Record<Measure, string> = {
  tokens: "token 用量",
  modelRequests: "LLM 请求",
  durationMs: "串行延迟（秒）",
  success: "累计成功率",
};
const savingLabels: Record<SavingMeasure, string> = {
  tokenSaving: "单任务 token 节省率",
  latencySaving: "单任务串行延迟节省率",
  cumulativeTokenSaving: "累计净 token 节省率",
  cumulativeLatencySaving: "累计净串行延迟节省率",
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
  if (!rows.length)
    return <p className="no-evidence">尚未运行严格对照，因此没有可绘制的绝对用量曲线。</p>;
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
function SavingsChart({
  rows,
  kind,
  revisions,
  onSelect,
}: {
  rows: CurvePoint[];
  kind: SavingMeasure;
  revisions: Revision[];
  onSelect: (id: string) => void;
}) {
  if (!rows.length)
    return <p className="no-evidence">尚未运行严格对照，因此没有可绘制的节省率曲线。</p>;
  const values = rows.map((row) => row[kind]);
  const numeric = values.filter((value): value is number => value != null);
  const low = Math.min(0, ...numeric),
    high = Math.max(0, ...numeric),
    span = Math.max(0.1, high - low);
  const x = (i: number) => 54 + (i * 580) / Math.max(1, rows.length - 1),
    y = (value: number) => 164 - ((value - low) * 130) / span;
  const changed = new Map(
    revisions.map((revision) => [
      revision.sourcePairId,
      [revision.graphChanged ? "G" : "", revision.matchingChanged ? "M" : ""]
        .filter(Boolean)
        .join("+"),
    ]),
  );
  return (
    <div className="evidence-chart savings-chart">
      <svg viewBox="0 0 690 210" role="img" aria-label={savingLabels[kind]}>
        <line x1="50" x2="645" y1={y(0)} y2={y(0)} stroke="#9eaaa2" />
        <text x="8" y="38">{rate(high)}</text>
        <text x="8" y="169">{rate(low)}</text>
        <polyline
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          points={values
            .flatMap((value, i) =>
              value == null ? [] : [`${x(i)},${y(value)}`],
            )
            .join(" ")}
        />
        {values.map((value, i) =>
          value == null ? (
            <g key={rows[i].task}>
              <line
                x1={x(i) - 4}
                x2={x(i) + 4}
                y1="100"
                y2="108"
                stroke="#a15d4a"
              />
              <line
                x1={x(i) + 4}
                x2={x(i) - 4}
                y1="100"
                y2="108"
                stroke="#a15d4a"
              />
              <title>{rows[i].task}: usage 不完整，未计算</title>
            </g>
          ) : (
            <g
              key={rows[i].task}
              role="button"
              tabIndex={0}
              aria-label={`${rows[i].task} ${savingLabels[kind]} ${rate(value)}`}
              onClick={() => onSelect(rows[i].task)}
              onKeyDown={(event) => {
                if (event.key === "Enter") onSelect(rows[i].task);
              }}
            >
              <circle cx={x(i)} cy={y(value)} r="5" fill="currentColor" />
              <title>
                {rows[i].task}: {rate(value)}；基线/RSI通过：
                {rows[i].baselinePassed ? "是" : "否"}/
                {rows[i].rsiPassed ? "是" : "否"}
              </title>
            </g>
          ),
        )}
        {rows.map((row, i) => (
          <g key={row.task + "-label"}>
            {changed.get(row.task) && (
              <text x={x(i)} y="22" textAnchor="middle" className="revision-marker">
                {changed.get(row.task)}修订
              </text>
            )}
            <text x={x(i)} y="194" textAnchor="middle">
              任务{i + 1}
            </text>
          </g>
        ))}
      </svg>
      <div className="chart-legend">
        <span className="rsi">● 正值表示 RSI 节省</span>
        <span className="negative-saving">● 负值表示 RSI 开销更高</span>
        <small>× 表示 usage 不完整；G/M 只标真实修订来源任务。</small>
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
    [savingKind, setSavingKind] = useState<SavingMeasure>("tokenSaving"),
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
  const hasRuns = Boolean(data?.pairs.length),
    candidateNotStarted =
      release?.status === "candidate" && data?.experimentStatus === "not_started",
    candidateStopped =
      release?.status === "candidate" && data?.experimentStatus === "quality_stopped",
    run = detail?.runs[arm],
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
        <p className="eyebrow">当前候选审阅</p>
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
          {error}。候选审阅不可用，不加载历史数据补足。
        </p>
      )}
      {!data && !error && <p>正在读取指定发布的保存证据…</p>}
      {data && (
        <>
          {candidateNotStarted && (
            <section className="candidate-readiness" aria-label="候选版本启动状态">
              <div>
                <p className="eyebrow">候选状态</p>
                <h2>任务已冻结，等待首轮严格预检</h2>
                <p>
                  这里暂时没有效果、成本或可靠性结论。空白曲线和空回放表示尚未产生运行，
                  不是用历史数据补出的占位结果。
                </p>
              </div>
              <dl>
                <div>
                  <dt>已冻结范围</dt>
                  <dd>{data.plannedPairs} 项 train 任务 · 6 个业务契约</dd>
                </div>
                <div>
                  <dt>下一项执行</dt>
                  <dd>{String(release.protocol.precheckPairs || "—")} 对严格串行预检</dd>
                </div>
                <div>
                  <dt>通过后</dt>
                  <dd>再启动 {String(release.protocol.fullPairs || data.plannedPairs)} 对正式对照</dd>
                </div>
                <div>
                  <dt>候选门槛</dt>
                  <dd>质量、usage 与实际 Fast 复用率均需通过；Fast ≥ 50%</dd>
                </div>
              </dl>
              <button
                type="button"
                onClick={() =>
                  document
                    .getElementById("evidence-business")
                    ?.scrollIntoView({ block: "start", behavior: "smooth" })
                }
              >
                审阅已冻结任务与资料范围 ↓
              </button>
            </section>
          )}
          {candidateStopped && (
            <section className="candidate-readiness candidate-stopped" aria-label="候选版本预检结果">
              <div>
                <p className="eyebrow">候选预检已停止</p>
                <h2>首对真实执行未通过质量门槛</h2>
                <p>
                  F01 的 Baseline 与 RSI 都保留为失败回放。后续 11 对没有启动，当前页只展示这次真实失败与开销，不绘制收益曲线。
                </p>
              </div>
              <dl>
                <div><dt>已执行</dt><dd>1 / {data.plannedPairs} 对严格预检</dd></div>
                <div><dt>质量结果</dt><dd>Baseline 0/1 · RSI 0/1</dd></div>
                <div><dt>Fast 复用</dt><dd>0 / 1，未达到 50% 门槛</dd></div>
                <div><dt>下一步</dt><dd>修复报告交付契约后，以新的空经验库重新预检</dd></div>
              </dl>
            </section>
          )}
          <section id="evidence-business" className="evidence-section">
            <header>
              <p className="eyebrow">01 · 任务与业务成果</p>
              <h2>先看实际完成了什么</h2>
              <p>
                计划 {data.plannedPairs} 对，已启动 {data.pairs.length}{" "}
                对。未启动的业务场景没有结果。
              </p>
            </header>
            {data.taskReview?.length ? (
              <details className="task-review">
                <summary className="task-review-intro">
                  <strong>正式运行前审阅 · 6 个业务契约</strong>
                  <span>展开查看冻结题面、资料字段与预检位置</span>
                </summary>
                <p className="task-review-note">
                  48 train · 6 validation · 6 test；本轮正式对照只运行 train，validation/test 保持冻结。
                </p>
                <div className="task-review-grid">
                  {data.taskReview.map((contract) => (
                    <article key={`${contract.scenario}-${contract.group}`}>
                      <small>{contract.scenarioLabel}运营</small>
                      <h3>{contract.title}</h3>
                      <p>
                        train {contract.counts.train} · validation {contract.counts.validation} · test {contract.counts.test}
                        {contract.precheckPositions.length
                          ? ` · 预检位置 ${contract.precheckPositions.join("、")}`
                          : " · 不进入首轮预检"}
                      </p>
                      <dl>
                        {Object.entries(contract.inputTables).map(([table, fields]) => (
                          <div key={table}>
                            <dt>{table}</dt>
                            <dd>{fields.join("、")}</dd>
                          </div>
                        ))}
                      </dl>
                      <details>
                        <summary>审阅 8 个 train 业务题面</summary>
                        <ol>
                          {contract.variants.map((variant) => (
                            <li key={variant.position}>
                              <details>
                                <summary>实例 {variant.position} · hash {variant.requestHash.slice(0, 12)}</summary>
                                <pre>{variant.request}</pre>
                              </details>
                            </li>
                          ))}
                        </ol>
                      </details>
                      <p className="task-source">
                        来源：{contract.source.provider || "冻结公开资料"}。{contract.source.note}
                      </p>
                    </article>
                  ))}
                </div>
              </details>
            ) : null}
            {!data.pairs.length ? (
              <div className="no-evidence no-evidence-primary">
                <strong>当前没有可展示的业务成果</strong>
                <p>
                  问题、附件、任务顺序和评分边界已冻结。Baseline 与 RSI 都尚未启动，
                  因此没有报告、执行轨迹、token、LLM 请求、工具调用或串行延迟记录。
                </p>
                <p>运行产生后，每项记录会在本页按同一发布上下文出现，并可回到输入资料、报告和运行回放。</p>
              </div>
            ) : (
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
                {!data.pairs.length ? (
                  <p className="no-evidence">任务问题与附件已经冻结，尚未产生任何 Baseline/RSI 保存运行。当前页面不会载入旧实验补数。</p>
                ) : detail ? (
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
            )}
          </section>
          <section className="evidence-section">
            <p className="eyebrow">02 · 为什么结果可信</p>
            <h2>
              {!hasRuns
                ? "严格串行对照尚未运行"
                : data.summary.qualityGate
                  ? "结构化质量门槛通过"
                  : "质量门槛尚未通过，保留每一次失败"}
            </h2>
            <p>
              相同任务、附件和通用工具，逐对交替串行执行。结果核对指标、业务
              ID、原因分组和实际观察证据；结构化通过不等于报告全文已独立审核。
            </p>
            {hasRuns ? (
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
            ) : (
              <p className="no-evidence">
                当前只有冻结后的问题、附件和协议；没有运行可用于质量、失败或恢复统计。
              </p>
            )}
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
              {!hasRuns
                ? "严格对照尚未运行，暂无成本曲线"
                : data.summary.qualityGate
                  ? "同一任务流的全量成本"
                  : "当前成本记录，暂不作同质量收益结论"}
            </h2>
            <p>
              包括冷启动、匹配、学习、失败和恢复。每条曲线使用上述同一组任务；串行延迟为保存观察值。
            </p>
            {data.summary.qualityGate ? (
              <>
                <h3>离线保存工件的相对与累计变化</h3>
                <p>这是对已保存成对运行的离线复核，不会调用模型，也不是实时评测。</p>
                <div className="measure-tabs" role="group" aria-label="选择离线节省率曲线">
                  {(Object.keys(savingLabels) as SavingMeasure[]).map((key) => (
                    <button key={key} className={savingKind === key ? "selected" : ""} onClick={() => setSavingKind(key)}>
                      {savingLabels[key]}
                    </button>
                  ))}
                </div>
                <SavingsChart rows={data.summary.curves} kind={savingKind} revisions={data.revisions} onSelect={select} />
                <p>当前累计净 token 节省率：{rate(data.summary.netTokenSaving)}。</p>
              </>
            ) : (
              <div className="no-evidence no-evidence-primary">
                <strong>质量门槛未通过，不展示节省率或累计收益曲线</strong>
                <p>下方保留两臂真实 token、LLM 请求、工具调用和串行延迟，供定位失败与开销；这些数字不构成效率结论。</p>
              </div>
            )}
            <details className="absolute-curves">
              <summary>查看两臂绝对用量与成功率</summary>
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
            </details>
          </section>
          <section id="evidence-replay" className="evidence-section">
            <p className="eyebrow">05 · 逐任务真实轨迹与报告回放</p>
            <h2>每个数字都能回到同一次工作</h2>
            {data.pairs.length ? (
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
            ) : (
              <p className="no-evidence">尚无保存运行，因此没有可追溯的报告、指标或执行轨迹。</p>
            )}
            <h3>
              {detail ? `${detail.task.title} · ${armLabel[arm]}` : "尚无可回放的保存运行"}
            </h3>
            <p>
              {run ? (
                <>
                  保存轨迹回放，不是实时执行。运行 ID：<code>{run.id}</code>
                </>
              ) : (
                "严格对照尚未运行，因此没有轨迹、报告或运行 ID。"
              )}
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
