# Workpack V13 Smoke 诊断

工件：`5dbcb2fc-6fee-431e-9286-f508b00f8439`。V13 的三场景 smoke 未通过质量门槛：
Baseline 2/3，RSI 3/3，token 121,746→71,031。该差值不是同质量收益结论。

财务 `finance-freight-contribution-01` 两臂均通过，验证了 V13 的一对多对账锚点修复：
订单行按 `order_id` 的多行资料不再被误拒绝，带 `rightTerms` 的对账实际执行。六个运行均无
传输重试，因此有界 retry 只由单元测试验证，未制造 provider 故障。

失败是客服 Baseline 的通用工具语义缺陷：`workspace_aggregate_rows` 接受
`operation=count` 与 `groupBy`，却静默返回总行数。模型将总行数当作不同渠道/产品数量；
报告的 `metrics` 被结构化校验拒绝，随后恢复正确限制读取但重复相同错误而有界终止。
这不是证据格式或 RSI 机制收益。V14 改为拒绝该含糊调用，并要求 `group_count`；V13 不与
V14 混接。
