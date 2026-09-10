# 实验状态与可主张的结论

更新时间：2026-09-10；实验功能基线 `9520ae7`，本文另记录其后的沙箱清理验证。本文件为状态索引，原始数字与协议见链接，执行轨迹保存在本地 artifacts（不随 Git 分发）。

## 已完成的真实验证

| 实验 | 覆盖与 ID | 结果 | 结论边界 |
|---|---|---|---|
| Strong ReAct vs RSI | 30 对 validation；`6d01875c-ceaa-4640-9511-f29c2c6e3fc4` | 双方 30/30；token 628397→439413（-30.1%）；均延迟 33.56→22.98s；工具 324→339 | 27 次冷启动、3 次历史图命中；不是纯 Motif/递归贡献；文字未全量评分 |
| Plan + ReAct vs RSI | 同一批 30 validation 任务；`1535dc8e-a865-4f7c-b00f-69d606f5a4e7` | 29/30 vs 30/30；token 673279→485075；均延迟 34.90→31.39s；工具错误 0→6 | 全量 token -28.0%、延迟 -10.1% 受基线一次失败影响；双方通过的29对为 -15.5%/-4.9% |
| 正常任务在线复用 | 三场景 8 次运行，见在线验证记录 | 8/8 结构化通过；5次后续任务跳过 Plan；维护约3.7–5.0ms | 仅产生三份 G0，没有真实 G1/G2 链；不是对照性能结论 |
| 筛选后补查 Motif | `finance-cancelled_payments` 两条正常 train；`b5abdd11`、`fa813841` | 两次均通过；每次 10 条中入选 1、排除 9，实际只读 1 条支付详情；热启动跳过 Plan | G0 仍为 `probation`，没有人为生成 G1；不是冻结总体性能评测 |
| 复用 Plan 的 ReAct 对照 | 同一 train 任务 `finance-cancelled_payments-03`；`7c32fa3e` vs `fa813841` | 两者通过；Motif 3 vs 7 LLM、10,370 vs 22,135 token、4 vs 6 工具；Motif 延迟 26.04 vs 24.88 s | ReAct 也自行筛选到 1 条详情；本对分离规划/执行成本，不证明详情调用净节省或总体延迟优势 |
| G-Agent 式三路径 / Persistent TinyEdge | 注入协议回归 + 五条正常 train 尝试，见 `g-agent-local-composition-validation` | 回归实际执行两个片段组合；真实 train 未形成 support>=2 的可组合片段，未触发 Composition | 不把注入机制测试说成模型性能结果；真实尝试含编译歧义和模型超时，未观察到成本、延迟或大小模型协同收益 |
| 最小 AutoTool / TIG 惯性预检 | 三条正常 train 模型轨迹 `35234b93`、`e8312d69`、`f24650ef`；`motif_first` `381f3fa5` | 三条 train 均通过，产生模型来源路径/参数契约；预检通过且惯性尝试 1 次，`finance_get_order_payments` 支持 2、CIPS 0.1348 < 0.55，拒绝且回到模型 | 没有实际惯性调用、没有模型/token/工具/延迟净收益；不扩大成对评测、不降低阈值制造命中。较早 `3ae50cb8` 暴露并发上下文误用，已保留并用串行边规则修正，不能作为机制收益证据。 |
| 36-task 在线训练对照 | `online-e2e-train-v1`；36 个固定 train 任务 × `plan_react` / `motif_first`，六轮串行 | 基线 36/36、601,435 token、737.62s；RSI 35/36、766,076 token、890.26s。RSI Fast 5 次，Composition/AutoTool 运行时调用均为 0；双顺序 Judge 平均 reward 两臂同为 0.9714，另耗 339,938 token | 历史 Workflow 在 `support-channels-02...06` 实际复用且跳过 Plan，但全量 RSI token +27.4%、延迟 +20.7%，并有一次确定性失败；不能主张总体净收益。完整协议、审计修复和结果见 `online-e2e-train-results-2026-09-10.md`。 |
| 当前 Judge 协议 | Plan 对照中的四对；固定对象输出、双顺序 | 财务顺序分歧；客服渠道/工单讨论平局；失败的近期投诉样例 RSI reward 更高 | 四对不是全30对；同模型 Judge；失败样例是目的性选择，不是随机总体质量样本 |

`online-e2e-train-v1` 的只读审计确认 25 次跨场景 TinyEdge 维护异常、两条能力/Plan 语义偏移轨迹以及无界重复报告失败。修复设计见 [online-rsi-repair-design-2026-09-10.md](online-rsi-repair-design-2026-09-10.md)。该实验保留为负向结果；共享报告恢复修复也会影响基线，不能把它与修复后的新实验连续累计。

两轮评测重复使用同一批验证任务，不是60个独立任务。测试集尚未用于最终性能测试。旧沙箱执行代码与专用运行记录已按用户要求删除；有日期的旧实验文档仍只代表历史结果，平台记录单独保留，不能混入此表。

来源：

- [Strong 基线结果](paired-evaluation-2026-09-10.md)
- [Plan 基线结果](plan-baseline-validation-2026-09-10.md)
- [在线复用验证](online-evolution-validation-2026-09-10.md)
- [Judge 分数与 reward](judge-reward-validation-2026-09-10.md)
- [Motif 初始训练证据](motif-filter-then-enrich-validation-2026-09-10.md)
- [G-Agent 局部组合初始验证](g-agent-local-composition-validation-2026-09-10.md)
- [成对评测协议](paired-evaluation.md)、[裁判协议](llm-judge.md)

## 图与 Judge 的实际状态

当前持久化图除原三份 G0 外，新增 finance/cancelled_payments 的 Motif G0 `b13e00e4`（`probation`）：条件为 `status == "canceled"`，已有一条后续正常训练成功证据。它仍不是多代链。切换执行环境后需重新读取 `artifacts/online-graphs.json` 核验，不能依赖本页旧快照。

当前 Judge 最新四对的 reward（Plan / RSI）：取消订单 0.965/0.990（分歧），投诉渠道 0.990/0.990（平局），工单讨论 0.980/0.980（平局），近期投诉 0.665/0.940（两次方向一致）。最新四对共8次请求、33840 token。旧0–4与数组格式失败记录保留，不与新版 reward 汇总为统一样本。

最近实验实际使用 qwen/qwen3.5-27b。执行、规划、裁判默认同模型；以后应读取配置/运行元数据，不能把这句话当成当前环境永久配置。

## 尚未证明

1. 历史图/Plan 缓存各自带来的独立收益；虽已有单对复用 Plan 的 ReAct 执行对照，但尚无冻结总体结论。
2. 真实任务反馈驱动的连续多代图改进。G0→G1→G2 目前主要由注入回归测试覆盖。
3. 长期可靠性优于强基线，或高并发吞吐收益。
4. 全任务报告质量等价或更好；独立 Judge 与人工校准尚不足。
5. 完整训练摊销、美元成本、真实企业写入流程完成能力。
6. Persistent TinyEdge 在真实 train 流量中的可组合覆盖、质量与成本收益；本轮只有注入机制验证，不能替代。
7. AutoTool 在真实任务上接受惯性调用后的质量、净成本和重复可靠性。当前只证明保守学习、拒绝和恢复路径正确；默认不能宣称收益。
8. 整体在线 RSI 的累计成本收益。本轮完整训练流得到负收益，下一步必须先诊断失败/覆盖边界，不能通过重跑或调阈值追逐正结果。

## 当前问题

- Motif 当前只支持已声明列表字段的精确相等条件；范围、比较、跨字段或列表外条件仍必须交给模型，不能伪装为已编译。
- 发布报告仍可能有重复 evidenceIds、排序/计数错误；图读取正确不保证报告正确。
- Judge 受格式、同模型偏差、顺序影响；分数不是自动可信标签。
- 来源训练任务已知43220 token只是一部分可追溯成本，不是完整研发或学习账本。
- 当前 Composition 候选使用本地字元重叠，且只接受无 gap、至少两个不同 TinyEdge 的组合；这不是论文 embedding retrieval 或完整细化器。

## 验证状态

在 `9520ae7` 功能提交前：104 个 Python 测试、4 个前端回放测试、前端构建通过。本次交接另按用户指令清理旧沙箱；旧沙箱专用测试移除，共用协议测试保留/迁移，没有产生新的模型性能结果。清理后的检查结果在本页末尾记录。

清理后：61 个 Python 测试、4 个前端回放测试、前端构建、300 条任务库契约校验通过。Motif 本轮后为 64 个 Python 测试；本轮 G-Agent 局部组合后为 67 个 Python 测试、4 个前端回放测试、类型检查与前端构建通过。测试数量变化来自删除旧沙箱专用功能及其测试及新增 Motif/TinyEdge 协议回归；当前在线进化、Judge、成对评测与通用协议测试保留。
