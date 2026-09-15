# 在线展示与饱和实验最小设计

日期：2026-09-11。本文新增的两个入口不替代或改写严格串行
`online-rsi-serial-final-v4`；前者服务录制，后者验证有限公开 train
池内的经验复用是否在更多 family 中保持收益。

## 1. 实时在线对照

`POST /api/live-showcase` 接受一个 train `taskId` 和 `steps=1|2`。
它创建一次 UUID 会话并在
`artifacts/live-showcase/<id>/` 保存完全隔离的 Baseline/RSI run、经验和
会话索引：

- Baseline：`plan_react`，无跨任务学习。
- RSI：`graph_rsi`，从空经验开始；两任务模式选择同 family 的两个不同
  train 实例，第一条正常完成后才允许第二条读取经验。
- 每次仅有一个 Agent、模型请求和读取工具运行，三个限流均为 1；顺序为
  Baseline 后 RSI。因此页面可以实时显示已完成的一臂和正在运行的一臂，
  但不能将分时 wall-clock 差异说成稳定供应商性能优势。
- 没有 Judge、影子 rollout、validation/test 学习或对正式 V4 经验的读写。
  会话仅标记为录制演示，不能并入正式总结果。

前端只读取会话和原始 run 事件。模型可见计划、工具调用、观察和最终业务
报告可以回放；不显示隐藏推理链。

## 2. 本地 overhead 账本

每个 run 结尾写入 `runtimeOverhead`，并同步
`metrics.runtimeOverheadMs`。它包含不消耗 LLM token 的、互不重复的本地阶段：

1. 历史图查找；
2. 冷启动工具检索、能力选择和图编译（合为一个 phase，避免重复加总）；
3. Composition 的确定性本地选择（不包括 composition 模型请求等待）；
4. 确定性参数绑定；
5. 在线经验维护；
6. 经验持久化。

该账本是端到端延迟的组成部分，但单独显示为 `0 token` 本地开销；不把绑定
次数换算成省掉一次模型调用，也不从 Agent token 中扣除它。Composition 模型
调用的 token、请求和 wall time 必须留在 `phaseMetrics.composition` 和 Agent
端到端时长中，不能计入本地账本。

## 3. 扩展饱和协议

`scripts/run_online_e2e.py --manifest-profile all_train` 冻结一个新的
180-task manifest：三个场景的全部 30 个 family、每 family 六个不同 train
实例，按实例序号 1–6 交错到达。两臂各 180 次，均为 1/1/1 串行运行；RSI
从新的空经验库开始，仅在此前完成的 train 任务后更新。

它回答的是有限任务库的经验曲线：每 family 的第 1–6 个实例、首次 Fast
复用位置、累计/边际 token 与模型请求差值、以及本地 overhead。它不能证明
无限任务流的渐近上界：每 family 只有六个不同 train 实例，且不同 family
不应跨契约强行复用。若 six-instance 曲线趋于稳定，只能称为本池内观测到的
饱和迹象。

扩展实验不使用 validation/test 生成经验，不调用 Judge 干扰 Agent 测量，
失败完整保留。启动前先跑第一轮 30 对作为正式可续预检；配置、提示、预算或
runtime 若改变，将停止并创建新实验 ID，不会拼接不同版本结果。

## 4. 验收

- 实时页面显示真实模型/图执行/工具/运行时账本，并能打开保存的逐事件轨迹；
- 录制对照目录与正式实验目录隔离，RSI 的首次与后续任务经验使用可追溯；
- 扩展 manifest 的 180 个 task ID、数据摘要和启动时配置冻结；
- 汇总将 token、模型调用、工具调用、端到端时长和本地 overhead 分开；
- 只在整个新增协议结束后，才基于保存结果讨论收益是否稳定或出现边际饱和。

## 5. V3 冷启动诊断的受限复用

`online-rsi-all-train-saturation-v3` 已执行 30 对任务：每个公开 train
family 的第一个实例各一条，因此它按设计没有 Fast 热启动。保存的 Agent
输出、token、模型请求、工具调用和端到端时长仍可审计：Baseline 为 29 / 30
通过、613,523 token、181 次模型请求、311 次工具调用；RSI 为 30 / 30
通过、500,157 token、129 次模型请求、358 次工具调用。对应的 token 差为
`-18.48%`，模型请求差为 `-28.73%`。这是一份冷启动诊断，不是最终 36-task
严格串行主结论，也不能与 V4 拼接。

V3 有一个明确的账本错误：三次 Composition 尝试中约 14.3 秒模型等待被写入
`compositionLocalMs`，从而污染了 `runtimeOverhead` 的金额和归因。该错误不改变
模型 usage、请求数、工具调用、任务输出、结构化评分或端到端时长；但 V3 **不得**
用于证明本地 overhead，页面必须显示此限制，不能把它称为零 token 本地开销收益。
Baseline 的一次 provider timeout 和 RSI 的五次错误工具调用后恢复均保留。

## 6. 费用保护与录制会话

在线入口现在要求显式 `confirmCost=true`，并拒绝第二个同时运行的 live session。
单任务模式会顺序执行 Baseline/RSI 两次 Agent；两任务模式会执行同族形成与复用的
四次 Agent。没有可靠美元价格配置时，页面只显示保存的 token/请求，不估算美元。
已完成的演示会话可以只读回放，不产生新模型请求，也永远不并入正式实验。
