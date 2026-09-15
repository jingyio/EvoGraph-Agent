# Workpack V13 修复与验证协议

日期：2026-09-13。V13 是在 V12 之后新建的隔离 runtime，不覆盖或重算任何历史
artifact。

## 修复范围

1. `workspace_reconcile_keyed_sums` 的锚定表现在按业务键去重进行汇总和比较，但保留
   每一条锚定行作为证据。因此订单行按 `order_id` 的正常一对多关系不再被误判为非法；
   返回同时区分 `anchorCount`（唯一业务键数）和 `anchorRowCount`（原始锚定行数）。
2. `model_client.py` 对 timeout、传输错误与 HTTP 408/429/5xx 仅重试一次。重试不适用于
   解析失败、拒绝、业务工具错误、报告校验失败或其他 4xx。每次逻辑模型决策仍记为
   `modelRequests`；实际供应商尝试记为 `modelProviderAttempts`，重试单列为
   `modelTransportRetries`。失败尝试没有可验证 usage 时，整个 run 的 `usageComplete=false`，
   即使第二次返回了 usage 也不把未知成本当作零。

两项均属于 Baseline 与 RSI 共享的正确性/计量修复，不是 RSI 学习收益，也不包含任务、
记录 ID、gold 或答案规则。

## V13 阶段与通过条件

- Smoke：固定三场景 3 个 train workpack、两臂串行 1/1/1；预计 6 次 Agent 运行，模型
  token 估算由既有正式协议计算，低于用户已授权的 5M token 上限。
- Smoke 必须两臂都通过私有结构化事实与证据校验，且财务 `freight_contribution` 两臂都实际
  使用带 `rightTerms` 的键控对账。重点检查一对多锚定不再触发“锚定表键必须唯一”、报告
  不再被比例 guard 循环阻断。
- 仅 Smoke 通过且 runtime fingerprint 一致时，才允许 V13 12-task precheck；任何运行时、
  提示、预算或服务计量变更都另建版本，不能拼接 V12。

传输重试在单元测试用 `httpx.MockTransport` 覆盖；真实 smoke 不会人为制造 provider 故障。
真实发生时保留所有 retry event、未知 usage 和失败成本。
