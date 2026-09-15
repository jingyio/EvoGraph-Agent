# 在线 RSI 端到端对照结果

实验：`online-e2e-train-v1`。执行于 2026-09-10，运行区间 12:01:28Z–12:36:54Z。完整 manifest、原始运行、隔离经验、Judge 输入输出和可录制 HTML 均在未纳入 Git 的 `artifacts/online-e2e/online-e2e-train-v1/`；入口为 `/api/online-e2e/online-e2e-train-v1/report`。

## 协议与有效性

固定 36 个不同 `train` 任务：财务、客服、技术工单各两种 family，每种六个不同记录实例；六轮中每轮按相同 family 顺序运行。基线 `plan_react` 不学习；RSI `motif_first` 从空、独立经验库按任务串行更新。两流各运行 36 次，任务对交替先后但各自任务序列相同。没有 validation/test 经验、影子 rollout、重试结果或改动用户模型配置。

第一轮是正式预检且保留在同一实验内：12/12 通过，基线经验存储未创建，RSI 从空库产生路径/参数契约和后续图。预检后仅修正结果汇总读取 RSI TIG 维护字段；它不影响运行、选择、token 或学习。之后发现恢复命令会覆盖旧 `experienceAfter` 展示快照；原字段保留，并由最终隔离存储的追加 source-run IDs 重建 `experienceTimeline`。该修复不新增模型/工具调用，也不改变任务结果；报告中明确使用派生时间线，不能把旧字段作为逐任务时间证据。

## Agent 成本与可靠性

| 指标 | Plan + ReAct 基线 | RSI `motif_first` | RSI 相对基线 |
|---|---:|---:|---:|
| 结构化通过 | 36/36 | 35/36 | -1 任务 |
| 输入 / 输出 token | 563,651 / 37,784 | 716,908 / 49,168 | +153,257 / +11,384 |
| 总 token | 601,435 | 766,076 | +164,641（+27.4%） |
| 模型请求 | 215 | 184 | -31 |
| 工具调用 | 279 | 367 | +88 |
| Agent 端到端累计 | 737.62s | 890.26s | +152.64s（+20.7%） |
| 每成功任务 token | 16,707 | 21,888 | +31.0% |

两臂用量统计完整。没有可靠、可审计的价格配置，因此不报告虚构美元金额。两臂 Agent 合计为 1,367,511 token；唯一 RSI 失败为 `finance-installments-06`，因“Record binding requires one unambiguous upstream list”进入恢复后达到模型请求上限，未通过 `order_count`、`paid_cents`、`selectedIds` 校验。基线对应任务通过。这是一次质量回归，保留在全量成本中。

## 实际经验使用与诊断

- RSI 共走 Fast 5 次、Fallback 31 次、Composition 0 次；Persistent TinyEdge 仍为 0，不能声称局部组合收益。
- 唯一历史 Workflow 图来自 `support-channels-01`（图 `f3ea2343-2953-4d33-b64b-2eea2958965b`），后续实际用于 `support-channels-02` 至 `-06`。这五次均跳过完整 Plan：每次 3 次模型请求，对应基线均为 6 次；五对均通过。它证明历史经验改变了后续执行，但不足以抵消全实验成本。
- RSI 最终有 1 个 family-supported Workflow 图、26 个 Workflow 轨迹、0 个 TinyEdge、18 条工具路径和 2 条参数关系；TIG 更新 58 次、参数关系更新 7 次。图查询 8.368ms、进化维护 25.083ms、TIG 更新 4.955ms、持久化 86.122ms，均已计入/单列。
- AutoTool 惯性实际尝试 0、接受 0、执行 0；没有把未触发写成收益。10 次图 fallback 及其恢复成本保留。

## 报告质量与 Report/Judge 成本

全部 36 对均完成匿名 A/B 与 B/A 双顺序 Judge。Judge 独立于 Agent 成本：72 次请求，314,192 输入 token、25,746 输出 token、共 339,938 token，447.275s，统计完整。执行器和 Judge 都是 `qwen/qwen3.5-27b`，因此这不是独立模型验证。

平均文字 reward 两臂同为 `0.9714`。19 对顺序一致（13 平局、RSI 5 对较高、基线 1 对较高）；17 对顺序不一致，结论为 inconclusive。Judge 没有覆盖确定性评分，也不能抵消 RSI 的一次结构化失败。

将 Agent 与 Judge 全部模型 token 简单相加为 1,707,449；该总量用于实验预算描述，不应被解释为 RSI 相对基线的净成本，因为 Judge 对两报告共同发生。

## 结论与展示

本轮证明了正常 train 流中的历史 Workflow 复用会改变后续执行，且在五个同 family 热启动任务上实际少了规划模型调用。它没有证明整个 RSI 系统以相同质量降低累计成本：全量 RSI token、工具调用和延迟都更高，并有一次确定性失败；Composition 与 AutoTool 没有触发，TinyEdge 也没有 materialize。

演示应展示：固定 manifest、`support-channels-01 → -02...-06` 的真实复用链、完整累计负收益、`finance-installments-06` 的恢复失败以及独立 Judge 成本。不要仅展示五个 Fast 命中或将同模型 Judge 说成独立质量证明。
