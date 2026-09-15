# Workpack V8 对账修复与 Smoke 协议

日期：2026-09-12。状态：**V8 Smoke 与 12 项预检均已通过；正式 train 运行中**。

## 背景

V7 的 `59892bb0-66ab-4d7f-93b9-0ee7dc8e95e4` 运行了三场景
Smoke。Baseline 三项均通过；RSI 仅一项通过，因此 V7 的质量门槛失败，
不能用于同质量成本结论。

- `finance-reconciliation-01`：RSI 已实际读取订单、支付和商品明细，
  但模型对已返回的逐订单汇总再次手工求和，提交了错误的
  `paid_cents` 和 `line_cents`，两次有界报告尝试后失败。
- `support-health-rollup-01`：两臂通过。
- `tickets-triage-01`：RSI 在人工停止 smoke 时被取消，零 usage；
  该项不能归为 RSI 机制失败。

V7 成本和失败 artifact 保留原样。它不与 V8 拼接，也不用于收益主张。

## 最小共享修复

新增工作区只读/本地计算工具 `workspace_reconcile_keyed_sums`。调用者必须
显式给出当前工作区中的锚表、键字段、每个来源表/键/数值字段、派生别名和
阈值比较。它返回：

- 当前键集合的各来源汇总、派生总额和有界逐键结果；
- 每个来源别名的缺失键、缺失并集数量；
- 明确比较算子的命中数量和键；
- 实际使用的当前锚表及来源表行的 evidence。

它不读取 `privateValidation`、`gold.json` 或任何实例期望值，不生成报告，
不选择业务规则，也不静默修正模型的 `metrics` 或 `selectedIds`。

`STRONG_REACT_GUIDANCE` 对 Baseline 与 RSI 同时提示：跨表同键求和、派生
总额和阈值差异优先使用该工具，而不是逐行心算。这是共享正确性能力，不能
归因为 RSI 学习收益。

## V8 边界与验收

V8 的 runtime 指纹包含 `workspace.py` 与提示/runtime 源码；因此使用新的
`smoke_v8`、`precheck_v8`、`full_train_v6` 存储线。

1. `smoke_v8`：冻结财务、客服、技术工单各一条 train workpack，两臂共
   6 次串行 Agent。实际 6/6 通过：Baseline `130,262` token、RSI
   `62,004` token。财务 RSI 实际调用一次键控对账工具；这是三项 smoke，
   不能外推为正式收益。
2. `precheck_v8`：冻结六类工作流前两条 train，共 24 次串行 Agent。实际
   24/24 通过：Baseline `381,654` token、RSI `419,808` token（RSI +10.0%）。
   RSI 形成 5 个 G0，第二轮实际 Fast 复用 4 次；没有 Composition。负收益、
   工具错误和恢复都保留，不把硬校验通过包装成效率收益。
3. 预检的 3 个控制错误是规划结构首次不合格后的一次重试或 fallback；3 个工具
   错误是日期字段误用于数值对账、以及空筛选数组，均由现有 schema 拒绝；4 次
   RSI 报告失败均为一次公开范围补齐后成功重提，没有重复签名循环或维护错误。
4. 仅当 6 次均通过私有结构化事实与证据校验，且 runtime fingerprint 相同，
   才允许 `precheck_v8`；预检通过后才允许一次 `full_train_v6`。
5. smoke 需验证财务任务实际调用确定性对账工具或给出未调用原因；无论调用
   与否，错误的模型手算结果不得通过。
6. 记录输入/输出 token、模型/工具调用、局部 compute 开销、报告尝试与恢复。
   Judge 不在 smoke 中运行，费用独立。

这不是任务答案内置、不是新的 RSI 图模块，也不保证模型一定选用该能力；
它只消除已观察数值仍被语言模型手工算错这一可复现的共享失败面。
