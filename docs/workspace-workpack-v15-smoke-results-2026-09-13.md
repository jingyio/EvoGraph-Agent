# Workpack V15 Smoke 结果

工件：`a83b9db0-3cea-446c-9286-0f75d14f9665`。固定三场景 smoke、串行
`run=model=read=1`，Baseline 与 RSI 均 3/3 通过私有结构化事实和证据校验。

Agent token 为 99,192→74,096（-25.300%），模型逻辑请求为 14→13，工具调用为
22→20。该样本只包含首到达任务：RSI 3 次 Fallback、3 个初始 Workflow、0 Fast、0
Composition，不能用它主张在线复用收益或全量约 30% 结论。客服单点为 RSI 负收益，保留。

财务两臂均实际调用 `workspace_reconcile_keyed_sums`：订单行 anchor 为 10 个唯一
`order_id`、12 行原始资料，comparison 返回 6 个命中键及 `matchingTotals`。两臂报告均
通过，证明多对一 anchor、明确 group count 和命中金额确定性汇总可协同完成；没有真实
transport retry，retry 机制仍只有单元测试证据。

RSI 有两次被保存的工具拒绝：一次 `group_count` 漏少 `groupBy`，一次图执行后模型请求了
当前阶段未开放的读工具。两次均未改变结果、未触发报告恢复、重复读取或维护错误；保留在
原始 trace 中，不能宣称零工具错误。由于 Smoke quality gate 通过、当前 fingerprint 一致，
允许启动 V15 12-task precheck。
