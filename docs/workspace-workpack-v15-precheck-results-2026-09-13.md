# Workpack V15 Precheck 结果

工件：`c64f1bca-88c2-47dc-afb3-dd68fe102a0d`。固定 12 个不同 train workpack、
两臂严格串行 `run=model=read=1`，Baseline/RSI 均 12/12 通过私有结构化事实与证据校验。

| 指标 | Baseline | RSI |
|---|---:|---:|
| Agent token | 419,583 | 271,902 |
| 模型逻辑请求 / provider attempts | 55 / 55 | 40 / 40 |
| 工具调用 | 104 | 78 |
| 串行总时长 | 790.188s | 602.772s |
| P95 单任务时长 | 154.990s | 98.938s |
| 报告失败 / 恢复任务 | 2 / 2 | 0 / 0 |
| 维护错误 / usage 不完整 | 0 / 0 | 0 / 0 |

RSI token 降幅为 **35.197%**。第一轮 6 个任务均为 Fallback，保存 6 个初始
Workflow；第二轮相同 family 的 6 个新实例均实际 Fast 复用，Plan 请求为零。第二轮
token 降幅为 41.149%，但全量口径仍包含首轮冷启动，未用热启动子集替代。

六个 family 中五个为正收益；`support-health-rollup` 为负收益（-17.222%），保留。RSI
出现 5 次工具契约拒绝，均未造成失败或报告恢复；Baseline 有 2 次公开范围
`evidence_coverage` 失败，由共享、确定性范围恢复完成。两臂均没有真实 transport retry，
所以 V13 retry 只具单元机制证据。

这是一份通过质量门槛的预检，允许使用同一 runtime fingerprint 启动 V15 full train。它不是
最终 48-task 结论；Composition 为 0，未观察 G1/G2。
