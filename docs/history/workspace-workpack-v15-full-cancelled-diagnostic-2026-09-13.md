# Workpack V15 Full 取消诊断

日期：2026-09-13。

## 工件与状态

- 工件：`6c56245b-3dc1-4218-ae81-f1e02434a88e`
- 模式：`workspace-workpack-online-full-train-v13`
- 计划范围：48 个冻结 train workpack、每臂 48 次、串行 `run=model=read=1`
- 最终状态：`cancelled`，不是 completed full experiment。

## 已发生的运行

Pair 1 的 Baseline 与 RSI 都完成且通过结构化校验。Pair 2 的 RSI 完成并通过；随后 Baseline
在执行中经历两次实际 transient transport retry，取消请求到达后该 arm 被取消。该 arm 的失败尝试
没有可靠 provider usage，故任务计量正确标记为 `usageComplete=false`。

已启动 arm 的 token、模型请求、provider attempt、工具调用和失败状态仍保存在原 artifact 中，不能删除。
但它们不构成完整、同质量的 48 对成本比较；不报告任何 full token saving、质量或延迟结论。

## 汇总修复

旧 `_summary` 仅根据两个 arm 是否已有终态记录构建 paired curve，因此被取消的 Pair 2 曾错误显示为
`pairedCompleted=2`。修复后只有 `pair.status == "completed"` 才进入：

- `pairedCompleted`；
- 累计 token 与逐 pair 差值曲线；
- 基于同任务配对的节省率。

取消 pair 的 arm 级成本和失败仍保留在 arm 汇总中。为避免改写历史证据，原 artifact 文件不回填；服务读取
时依据修复后的代码重新计算摘要。相应回归覆盖“两个 arm 均有终态记录但 pair 被取消”的情况。

## 当前可用结论

V15 smoke 与 12-task precheck 仍是当前 runtime 下通过质量门槛的 staged 证据。V15 full 已取消，且因未知
failed-attempt usage 不可用于成本结论；在能审计失败 attempt usage 或另行固定新协议前，不自动重启 full。
