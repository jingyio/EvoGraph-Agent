# RSI 最终串行在线对照结果

日期：2026-09-11。正式工件为本地未入 Git 的
`artifacts/online-e2e/online-rsi-serial-final-v4/`；协议见
[online-rsi-serial-final-protocol-v4-2026-09-10.md](online-rsi-serial-final-protocol-v4-2026-09-10.md)。本文件只汇总已经落盘的真实运行，不拼接历史分时结果。

## 协议与可比性

- 固定 36 个不同的 `train` 任务：财务、客服、技术工单各两个 family；每 family 六个不同记录实例，按六轮交错到达。
- Baseline 是强 `Plan + ReAct`，不学习；RSI 从独立空经验库开始，每个正常 `train` 任务结束后才更新，下一任务只能读取此前经验。
- 两臂使用相同的 `qwen/qwen3.5-27b` 执行、规划与 composition 配置，最大 24 步、180 秒任务上限、同一工具契约和共享有界报告恢复。
- 每次只执行一个 Agent：`run_limit=model_limit=read_limit=1`。任务对在同一 session 中交替启动；token、调用和工具计量可比。服务端负载和缓存仍可能影响延迟，因此不将延迟差异表述为稳定 provider 性能结论。
- 无影子 rollout；AutoTool/TIG 惯性执行保持关闭。Judge 在全部 Agent 完成后运行，成本不混入 Agent 成本。

## 全量结果

| 指标 | Baseline | RSI | RSI 相对 Baseline |
|---|---:|---:|---:|
| 确定性结构化通过 | 36 / 36 | 36 / 36 | 无质量回归 |
| 输入 / 输出 / 总 token | 505,623 / 33,845 / 539,468 | 320,789 / 26,579 / 347,368 | **-192,100 / -35.6%** |
| 模型请求 | 203 | 114 | -89 / -43.8% |
| 工具调用 | 274 | 277 | +3 |
| 平均工具调用 / 任务 | 7.61 | 7.69 | +0.08 |
| Agent 累计端到端时长 | 1,386.93s | 806.19s | -580.74s / -41.9% 观测值 |
| 平均 / P95 / 最大单任务延迟 | 38.53 / 104.16 / 172.73s | 22.39 / 39.34 / 107.80s | 分时服务因素仍存在 |
| 最大单任务 token | 24,213 | 22,560 | RSI 较低 |
| 每成功任务 token | 14,985 | 9,649 | -35.6% |
| 工具错误 / 经验维护错误 | 0 / 0 | 0 / 0 | — |
| 报告提交 / 失败提交 | 41 / 5 | 43 / 7 | 所有未通过提交均计入；本次均在首提，全部有界恢复完成 |

全量 Agent token 下降 **35.6%**，达到“约 30%”目标。模型请求降低 43.8%，但不能将全部差异都归因于图复用：RSI 少 24 个完整 Plan 请求，剩余差异还包括真实执行与恢复轮数变化。工具调用并未减少，RSI 反而多 3 次，因此收益不是以虚构的“每次参数绑定等于少一次 LLM”计算得出。

没有可靠的价格配置，未报告美元。两臂 Agent 已记录 token 合计为 886,836。Judge 已记录至少 255,621 token，因此已记录的 Agent 加 Judge token 下限为 1,142,457；10 个 Judge 超时没有返回 usage，这个总数不能当作完整 Judge 账单。

## Family 与在线经验

| Family | Baseline token | RSI token | RSI token 降幅 | Baseline / RSI 通过 | RSI 实际历史使用 |
|---|---:|---:|---:|---:|---:|
| finance/cancelled_payments | 99,350 | 55,614 | 44.0% | 6/6 vs 6/6 | Fast 5 |
| finance/installments | 128,300 | 99,171 | 22.7% | 6/6 vs 6/6 | Fast 4 |
| support/channels | 83,801 | 47,948 | 42.8% | 6/6 vs 6/6 | Fast 5 |
| support/timeliness | 77,343 | 43,505 | 43.8% | 6/6 vs 6/6 | Fast 5 |
| tickets/labels | 82,558 | 37,630 | 54.4% | 6/6 vs 6/6 | Fast 5 |
| tickets/unassigned | 68,116 | 63,500 | 6.8% | 6/6 vs 6/6 | 无后续复用 |

六个 family 都有正向全量 token 差值。`cancelled_payments` 不再是历史负收益 family；这是共享编译器/恢复正确性修复后的新严格实验结果，不能把该改善称为运行时自主图修订。

真实进化/复用链为：第 1 轮形成 `cancelled_payments`、`channels`、`timeliness`、`labels` 四个 G0；第 2 轮形成 `installments` G0；这些图随后在各自后续新记录任务中被 Fast 路径使用。`tickets/unassigned` 的 G0 到第 6 轮才形成，因而没有后续复用。总计 6 个初始 Workflow、24 次 Fast 复用、12 次 Fallback。

没有真实 G1/G2 结构修订；没有 Composition 实际执行。一次 composition 角色调用产生 727 token，但没有组合执行结果，因此不声称 TinyEdge/Composition 收益。初始图形成、支持度增长和编译器代码修复被明确区分。

## 本地开销、恢复和可靠性

RSI 的本地计量为：图查询 42.818ms、组合本地选择 1,908.967ms、在线维护 175.644ms、确定性参数绑定 1.001ms。它们均已计入 RSI Agent 端到端时间；没有将本地维护忽略为零成本。

报告恢复没有再次演化为旧实验中的长尾：两臂均没有工具错误、维护错误、分页越界或恢复期重复读取拒绝；`evidence_coverage` 和引用格式失败计数均为零。失败提交（每次未通过的 `publish_report` 都计数）分别为 5 和 7 次；本次均在首提，且每次恢复有界，最终 72 个 Agent 任务全部完成。这个结论只覆盖本次 36 个 train 任务，不能外推为长期零错误保证。

补充、独立于主实验的真实可靠性工件仍可访问：长尾修复预检 `online-rsi-serial-reliability-precheck-v2`，以及 10/30/60 条记录的严格串行规模补验 `efficiency-scale-serial-v4`。它们不替代本页的全量结论。

## 报告质量与 Judge

确定性事实/证据评分是主要质量门槛，双方均 36/36 通过。随后匿名双顺序 Judge 尝试 36 对：26 对完成、10 对因模型服务超时失败且未自动重试。完成的 26 对中，11 对交换顺序后保持一致，15 对顺序不一致；平均 reward 为 Baseline 0.9708、RSI 0.9752。Judge 使用与执行器相同的模型，因此既不独立，也不支持把这 0.0044 的差异表述为质量优势。高文字 reward 也不覆盖确定性失败。

## 可录制展示

启动后端后直接打开：`http://127.0.0.1:4317/api/online-e2e/online-rsi-serial-final-v4/report`。

3–5 分钟录制顺序：

1. 展示累计表：固定 36 条 train manifest、空经验、三种限流均为 1，以及 35.6% Agent token 降幅。
2. 选择 `finance/cancelled_payments` 或 `tickets/labels`：首任务创建 G0，后续实例使用相同 Workflow ID；打开一对 trace/report 核对业务结果与真实调用。
3. 查看 family 的累计 token 曲线和逐任务差值，指出实例记录不同，因果证据来自实际 Workflow ID 与 Fast 路径，而非曲线形状。
4. 展示串行可靠性表和链接的长尾/规模工件，说明恢复受控、没有并发收益声明。
5. 展示 Judge 覆盖缺口与“未观察到 G1/G2、Composition”的限制。

## 验收结论

1. **进化**：已证明在线形成初始 Workflow 并在 24 个后续同族任务实际 Fast 复用，改变了后续执行；**未证明**正常反馈驱动的多代结构修订。
2. **效果**：两臂确定性质量均为 36/36；Judge 只覆盖 26/36，且同模型、顺序分歧较多，**未证明**独立文字质量优势。
3. **效率**：严格串行主口径的 Agent token 降低 35.6%，达到约 30% 目标；工具调用没有下降。
4. **可靠性**：此前报告恢复、分页与跨场景维护故障在本样本中未重现，且全部任务正确完成；Judge 服务超时仍是外部评估覆盖缺口。
