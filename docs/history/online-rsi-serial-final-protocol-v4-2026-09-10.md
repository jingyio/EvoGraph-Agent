# RSI 最终串行在线实验协议 V4

日期：2026-09-10。此版本替代 V3 的执行版本；V1–V3 工件保留为失败定位或受限证据，不与 V4 主结果拼接。

## V4 修订：分页序列是数据依赖

V3 的 60 条 Baseline 预检虽然识别出缺实际观察，但模型在同一响应中把 `pageSize=50` 的第一页与 `pageSize=10` 的第二页混用，读取范围重叠。随后第一次报告同时有 `selectedIds` 和 `evidence_coverage` 错误，V3 未把混合错误优先归为缺观察，导致恢复继续读取错误页号。

V4 的共享 runtime：

- 将所有 `{page,pageSize}` 读取视为顺序依赖，不与普通独立读取并批；首次必须 `page=1`，后续必须页面连续、沿用相同 `pageSize`，并在 `mayHaveMore=false` 后拒绝额外分页。
- 只要报告错误包含 `evidence_coverage` 且当前仍缺任务范围观察，就优先分类为 `missing_evidence`，即使同时有 `selectedIds` 或 metric 问题；读取完整后才允许最终修正并提交。
- 记录 `paginationGuardRejects`、缺观察次数和格式引用次数。无效分页计为受控工具错误，不会被当成成功读取或经验。

该修复同时适用于 Baseline 与 RSI；V4 重新运行 10/30/60 串行规模工件后，才可决定是否启动 36 条正式 Agent 流。

## 其余冻结协议

继承 V3：36 个固定 train 任务与六轮顺序、`run_limit=model_limit=read_limit=1`、相同模型/提示/预算/工具/事实评分、Baseline 无跨任务学习、RSI 从独立空经验库开始、Judge 在 Agent 完成后单列。没有本轮并发矩阵或 AutoTool 惯性执行。
