# 36 任务在线 RSI 对照协议

日期：2026-09-10。实验 ID 为 `online-e2e-train-v1`。这是一次新的、隔离的正常训练流实验；它不改写既有 validation/test 结果，也不读取或写入 `artifacts/online-graphs.json`。

## 固定设计

- 36 个 `train` 任务，六轮交错。每轮依次为 `finance-cancelled_payments`、`finance-installments`、`support-channels`、`support-timeliness`、`tickets-unassigned`、`tickets-labels` 的一个未见实例（后缀 `01` 至 `06`）。启动时将任务 ID、记录 ID、时间和摘要写入 `manifest.json`；其后拒绝变更。
- 基线为 `plan_react`：固定 Plan + ReAct，共用现有观察复用、防重复和批量读取提示，不进行跨任务学习。
- RSI 为 `motif_first`：使用 Fast/Composition/Fallback、Workflow/Motif/TinyEdge 和保守 AutoTool；每个 RSI 任务完成后才更新独立经验，再开始下一个 RSI 任务。
- 两臂各自看到相同的 36 个任务顺序；每个任务对交替先后执行，但每次只运行一个 Agent。没有影子 rollout、预学习或从 validation/test 更新经验。
- RSI 经验在 `artifacts/online-e2e/online-e2e-train-v1/rsi/experience.json`，基线经验在同目录 `baseline/experience.json` 且 `learning_enabled=False`。两侧原始 run 文件也分目录保存。

## 计量与恢复

每次任务开始前持久化实验 checkpoint；启动 run 后立即持久化 run ID。进程中断后，恢复器将未完成 run 标记为 `interrupted`，该次尝试保留为失败而不会自动重跑或重复增加支持度。

每臂记录模型输入/输出 token、请求、工具调用/错误、端到端耗时、结构化评分和失败。RSI 额外记录 Fast/Composition/Fallback、图与 TinyEdge 来源、图检索/组合/维护耗时、TIG 查询/更新/持久化、惯性接受/拒绝/错误及恢复模型请求。`durationMs` 含当前任务的在线学习维护；Judge 不计入 Agent 成本。

所有 Agent 任务结束后，对每对报告作匿名 A/B 与 B/A 两次 Judge。事实、覆盖、可读性均为 0–10，reward 为 `(0.5*事实 + 0.3*覆盖 + 0.2*可读性)/10`。Judge 输入和输出分别保存；格式最多修正一次，引用不存在证据、网络/格式失败和顺序分歧均保留，不因结果重试。

首轮预检后仅修复了汇总器读取 RSI `evolution.toolInertia` 维护字段的问题；不影响已执行任务、选择、学习、计量原始 run 或协议。原始首轮记录保留，后续运行继续同一实验。

## 启动前核查

`npm run taskbank:validate` 已确认任务库 300 项/10,400 次契约工具调用通过；固定 manifest 有 36 个唯一 `train` ID。执行、规划与 Judge 均已配置，但当前 Judge 与执行模型相同，因此不能称为独立模型验证。隔离实验目录在启动前不存在。

近期真实 run 约 20–35 秒/Agent；72 次 Agent 及 72 次 Judge 请求预计约 55–95 分钟，实际网络、限流和格式失败会计入记录。第一轮以 `--through-round 1` 作为同一正式实验的预检；协议正确时以默认命令继续后五轮，不重跑首轮。系统性网络、限流或计量故障将暂停后续任务并保留已产生的 checkpoint。

## 展示入口

运行器生成 `artifacts/online-e2e/online-e2e-train-v1/index.html`，后端提供 `/api/online-e2e/online-e2e-train-v1/report` 和 JSON 入口。页面展示累计与逐轮成本/成功、经验来源到后续复用链、失败和原始审计索引；没有观察到收益时只呈现事实结果。
