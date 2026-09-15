# 工作区 Workpack 在线预检 V3

日期：2026-09-12。实验 ID：`82048ef9-6b03-4b1e-bb9e-2015f18b1346`。原始运行、经验快照、工作区资料和报告保存在本地 `artifacts/workpack-experiments/`，不入 Git。

## 协议

- 入口：每个固定工作包均调用 `install_workpack`，经当前 CSV/JSON/TXT 解析器、工作请求、工具、Planner、`TaskRunner` 和私有结构化校验运行；没有 benchmark 专用执行器或冻结读取图前缀。
- 范围：6 个工作流、每类两个连续 `train` 实例，共 12 个任务；Baseline 和 RSI 各 12 次，交替 arm 顺序。
- 限制：`run_limit=model_limit=read_limit=1`。Judge 未运行，费用不会混入 Agent。
- 学习：Baseline 禁止跨任务学习；RSI 从此实验专属空经验库开始，只有通过私有规则的 `train` 任务才更新。第二轮只能使用第一轮已有经验。
- 模型：保存运行记录标注 `qwen/qwen3.5-27b`。模型、工具、通用运行时和预算两臂相同。

## 实际结果

| 指标 | Plan + ReAct | Graph RSI |
|---|---:|---:|
| 结构化通过 | 11/12 | 12/12 |
| Agent token | 519,499 | 466,554 |
| 模型请求 | 71 | 57 |
| 工具调用 | 101 | 85 |
| 执行时长总和 | 572.7s | 686.6s |
| 本地 RSI runtime 开销 | 0ms | 92.839ms |
| 经验维护错误 | 0 | 0 |

同任务累计 token 节省率为 **10.19%**，没有达到 30% 目标。严格计入 `tickets-blocker-summary-01` 的 Baseline `limited` 失败；该失败不重跑、不删除。

按场景的同任务 token 差值为：财务 `285,418 → 224,424`（`-21.37%`），客服 `96,561 → 66,470`（`-31.16%`），技术工单 `137,520 → 175,660`（`+27.73%`）。因此不能将前两个场景的节省包装为三场景普遍收益。

## 进化证据与瓶颈

第一轮创建 5 个 G0 Workflow；第二轮实际 Fast 复用 5 次：财务核对、客服健康汇总、客服升级队列、工单分诊和工单阻塞摘要。每个 Fast 使用均在实验快照和 `usedVersionId` 中可追溯，且没有读取前一个工作区的记录 ID 或业务结果。

`finance-cancel-installments` 没有形成 G0：冷启动的图编译因 `filter_cancelled_paid` 没有能力兼容候选而失败关闭，后续由 ReAct 正确完成。它是覆盖缺口，不是被手工补成命中。该预检没有 Composition、没有 G1/G2，也没有真实反馈触发的结构修订。

技术工单是主要负例：`tickets-triage-01` 为 `26,472 → 59,258` token，`tickets-triage-02` 虽 Fast 仍为 `23,861 → 75,108` token。Fast 确实省掉完整 Plan，但报告生成和模型交接消耗可以超过该节省；Fast 不能直接等价为净省一次模型请求。

## 结论边界

本预检证明：新文件工作区能形成 G0、跨任务隔离、在后续同工作流任务实际 Fast 复用，并且维护没有未解释错误。它不证明 30% token 节省、低延迟、Composition 收益、多代结构进化、独立 Judge 质量或平台期。正式 train 流必须使用新实验 ID 和新的空经验库，不能拼接本预检经验或指标。
