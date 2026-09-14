# 实验状态与可主张的结论

更新时间：2026-09-13；实验功能基线 `9520ae7`，本文另记录其后的修复、最终串行验证和 Workpack V17。本文件为状态索引，原始数字与协议见链接，执行轨迹保存在本地 artifacts（不随 Git 分发）。

## 已完成的真实验证

> **Workpack V17 full** `005ffeb9-964e-42ac-86e9-fb9e8f2212fe` 已完成：48 个冻结
> train 工作包、每臂 48 次、串行 `1/1/1`、独立空 RSI 经验。两臂私有结构化事实/证据
> 校验均为 48/48，usage 完整且没有 transport retry。Baseline/RSI Agent token 为
> 2,244,017→1,243,546（**-44.5839%**），模型请求 258→149，工具调用 422→325。
> RSI 形成 12 个 G0，后续 Fast 35 次，Fallback 13 次，Composition 0；没有 G1/G2。
> 报告恢复和工具错误计入全部尝试，不把初次失败过滤掉。它是新的、可比较的工作包结论，
> 不与旧 V12/V15 取消或 V4 任务库工件拼接；完整边界见
> [V17 全量结果](workspace-workpack-v17-full-results-2026-09-13.md)。

> **2026-09-13 交互交付验收**：默认 `/#home` 已不是历史 benchmark 入口，而是同一
> Workspace/`runId` 贯通的上传、预览、澄清、真实 Agent、轨迹、报告下载与追问工作台。
> 已用保存的财务、客服、技术工单三组主任务与追问 run 实际核验；它们不学习，也不污染
> V17 经验。实验中心 `/#experiments` 的列表和仪表盘摘要不再重复传输所有 48 对的原始
> trace：列表约 29,869 B、V17 摘要约 290,393 B；点击单 run 才请求 DAG、观察、Plan 与报告。
> 这是展示性能与关联正确性的交付验证，不是新的 Agent 成本或质量实验。

> **2026-09-14 工作台题库与保存同题回放**：每个岗位在 `/#home` 提供 16 个冻结 train
> Workpack，资料和问题经过与上传相同的解析路径。加载 `finance-reconciliation-01` 已验证
> 同一工作包可同时显示其保存的 V17 Baseline/RSI pair、两侧报告和按需 RSI DAG/事件轨迹；
> `finance-reconciliation-05` 没有 V17 train pair 时明确拒绝展示，且不会自动发起 Agent。
> 这只改善可审计展示，不增加模型调用或改变 V17 实验数据。

> 2026-09-12 工作区 Workpack 后续实验：V5 Smoke、V6 Smoke 均保留为
> 诊断；V6 的 12-task 预检因 Baseline `tickets-triage-01` 发生共享
> `evidence_coverage` 恢复缺陷而未通过同质量门槛，不能用于经济性结论。
> V7 Smoke `59892bb0-66ab-4d7f-93b9-0ee7dc8e95e4` 已运行：Baseline 3/3，
> RSI 1/3，故质量门槛失败，成本只保留为诊断。财务失败是模型对已观察
> 分组数据的手工算术错误；技术项是人工停止后的取消，不能归为机制失败。
> V8 已以共享确定性键控对账工具建立独立 runtime 版本；协议与边界见
> [V8 对账协议](workspace-workpack-v8-reconciliation-protocol-2026-09-12.md)。

> 2026-09-13 Workpack V11/V12：V11 的 RSI Fast 路径出现重复确定性 compute
> 长尾，故新增两臂共享的重复 compute guard 并新建 V12 runtime。V12 smoke
> 3/3 与 precheck 12/12 均通过；V12 full 42/48 vs 46/48，末尾还有两臂共同的
> 模型网络失败，因此表面 -40.513% token 仅为诊断，不是同质量经济性结论。完整
> 边界见 [V12 结果](workspace-workpack-v12-results-2026-09-13.md)。

> 2026-09-13 Workpack V13：V12 财务失败定位到通用一对多锚定表被错误要求唯一，
> 另有模型服务瞬断完全不重试且缺少实际尝试计量。V13 按业务键去重对账、保留完整行证据，
> 并对 transient transport 仅重试一次、标记未知 usage；它尚未产生真实 smoke 结果。
> 协议见 [V13 修复协议](workspace-workpack-v13-repair-protocol-2026-09-13.md)。

> V13 smoke `5dbcb2fc` 为 Baseline 2/3、RSI 3/3；财务一对多对账通过，但客服
> Baseline 把 `count + groupBy` 的总行数误作不同分组数。V14 已将此调用改为显式拒绝，
> V13 token 差仅诊断，详见 [V13 诊断](workspace-workpack-v13-results-2026-09-13.md)。

> V15 smoke `a83b9db0` 为 3/3 vs 3/3，token 99,192→74,096（-25.300%）；财务
> 一对多 anchor、group count 和 comparison matchingTotals 均实际通过。它是首到达
> 小样本，0 Fast，不能主张在线复用或 30% 全量收益；详情见
> [V15 Smoke](workspace-workpack-v15-smoke-results-2026-09-13.md)。

> V15 precheck `c64f1bca` 为 12/12 vs 12/12，Agent token 419,583→271,902
> （-35.197%）；第一轮形成 6 个 Workflow，第二轮 6 次实际 Fast 复用，0 维护错误。
> 它通过质量门槛；详情见
> [V15 Precheck](workspace-workpack-v15-precheck-results-2026-09-13.md)。

> V15 full `6c56245b-3dc1-4218-ae81-f1e02434a88e` 在 pair 2 中取消。pair 1 完整，pair 2 的
> RSI 已完成但 Baseline 在两次实际 transient transport retry 后被取消；失败 attempts 的 provider usage
> 不可审计，Baseline 标记 `usageComplete=false`。因此 full 不能用于质量、token 或经济性结论。原始
> artifact 的旧摘要曾把取消 pair 计为 2 个 `pairedCompleted`；读取侧汇总现已修复为 1，且不改写历史 artifact。
> 详见 [V15 Full 取消诊断](workspace-workpack-v15-full-cancelled-diagnostic-2026-09-13.md)。

| 实验 | 覆盖与 ID | 结果 | 结论边界 |
|---|---|---|---|
| **Workpack V17 full** | `005ffeb9-964e-42ac-86e9-fb9e8f2212fe`；48 对 train workpack、串行 1/1/1、独立空经验 | 两臂 48/48；token 2,244,017→1,243,546（**-44.5839%**），请求 258→149，工具 422→325；Fast 35、G0 12、Composition 0 | 同一保存工件的结构化质量门槛和 usage 完整；分时 provider 延迟不作通用优势。Judge 未运行；没有 G1/G2 或 Composition 结论。详见 [V17 结果](workspace-workpack-v17-full-results-2026-09-13.md)。 |
| Workpack V12 staged train | smoke `2413c09a`、precheck `587d7c50`、full `f8acd9e2`；48 对 train workpack、串行 1/1/1 | Smoke 3/3、预检12/12均通过；full Baseline/RSI 42/48、46/48，token 1,813,753→1,078,947，Fast 36、Composition 0 | full 有三次 Baseline 有界失败、一条 Baseline 模型超时、两条两臂共同网络失败；质量门槛失败且服务异常，表面 -40.513% 仅诊断，不能替代 V4。 |
| Strong ReAct vs RSI | 30 对 validation；`6d01875c-ceaa-4640-9511-f29c2c6e3fc4` | 双方 30/30；token 628397→439413（-30.1%）；均延迟 33.56→22.98s；工具 324→339 | 27 次冷启动、3 次历史图命中；不是纯 Motif/递归贡献；文字未全量评分 |
| Plan + ReAct vs RSI | 同一批 30 validation 任务；`1535dc8e-a865-4f7c-b00f-69d606f5a4e7` | 29/30 vs 30/30；token 673279→485075；均延迟 34.90→31.39s；工具错误 0→6 | 全量 token -28.0%、延迟 -10.1% 受基线一次失败影响；双方通过的29对为 -15.5%/-4.9% |
| 正常任务在线复用 | 三场景 8 次运行，见在线验证记录 | 8/8 结构化通过；5次后续任务跳过 Plan；维护约3.7–5.0ms | 仅产生三份 G0，没有真实 G1/G2 链；不是对照性能结论 |
| 筛选后补查 Motif | `finance-cancelled_payments` 两条正常 train；`b5abdd11`、`fa813841` | 两次均通过；每次 10 条中入选 1、排除 9，实际只读 1 条支付详情；热启动跳过 Plan | G0 仍为 `probation`，没有人为生成 G1；不是冻结总体性能评测 |
| 复用 Plan 的 ReAct 对照 | 同一 train 任务 `finance-cancelled_payments-03`；`7c32fa3e` vs `fa813841` | 两者通过；Motif 3 vs 7 LLM、10,370 vs 22,135 token、4 vs 6 工具；Motif 延迟 26.04 vs 24.88 s | ReAct 也自行筛选到 1 条详情；本对分离规划/执行成本，不证明详情调用净节省或总体延迟优势 |
| G-Agent 式三路径 / Persistent TinyEdge | 注入协议回归 + 五条正常 train 尝试，见 `g-agent-local-composition-validation` | 回归实际执行两个片段组合；真实 train 未形成 support>=2 的可组合片段，未触发 Composition | 不把注入机制测试说成模型性能结果；真实尝试含编译歧义和模型超时，未观察到成本、延迟或大小模型协同收益 |
| 最小 AutoTool / TIG 惯性预检 | 三条正常 train 模型轨迹 `35234b93`、`e8312d69`、`f24650ef`；`motif_first` `381f3fa5` | 三条 train 均通过，产生模型来源路径/参数契约；预检通过且惯性尝试 1 次，`finance_get_order_payments` 支持 2、CIPS 0.1348 < 0.55，拒绝且回到模型 | 没有实际惯性调用、没有模型/token/工具/延迟净收益；不扩大成对评测、不降低阈值制造命中。较早 `3ae50cb8` 暴露并发上下文误用，已保留并用串行边规则修正，不能作为机制收益证据。 |
| **最终严格串行在线对照** | `online-rsi-serial-final-v4`；36 个固定 train 任务，独立空 RSI 经验，`run=model=read=1` | Baseline/RSI 均 36/36；token 539,468→347,368（**-35.6%**），模型请求 203→114，工具 274→277；Fast 24、Composition 0、G0 6、G1/G2 0 | 主交付结论：全量 Agent token 达到约30%目标；六个 family 均正向，`cancelled_payments` 修复后 -44.0%。延迟为同 session 交替串行观测，不能作稳定 provider 优势。Judge 26/36 完成、10 个服务超时、同模型且15个顺序分歧；详见 [最终结果](online-rsi-serial-final-results-2026-09-11.md)。 |
| 最终展示与严格摘要审计 | 只读 `online-rsi-serial-final-v4` artifact；`/api/showcase/...` | 默认全量 36 对、财务/客服/技术工单各 12 对；三领域播放器与具体任务回放按保存事件逐步推进，显示累计 LLM/token/工具/时间、模型/结构化/控制通道、执行器和 DAG 绑定。结构化精确通过 Baseline/RSI 均 36/36；额外摘要 audit 为 Baseline 25/36、RSI 26/36 | 新 audit 和动态展示没有重跑 Agent/Judge、没有改写历史结果或泄漏 gold。事件粒度不按不同长度 trace 的比例插值；结构化步骤不直接计作 LLM 节省。技术 `unassigned` 留在指标分母但不作代表回放。公开历史数据通过本地 SQLite + JSON Schema 只读接口模拟岗位读取，非生产平台写入部署；严格文字质量仍受同模型 Judge 覆盖 26/36 和顺序分歧限制。 |
| 企业运营数字员工主工作台 | `#home`；交互式 Workspace API 与保存 HTML 报告 | 财务、客服、研发运营共用一套工作台：上传、预览、确定性澄清、真实 Agent、同 run 的 DAG/轨迹、报告下载、导出、追问和历史工作均可用；`#experiments` 展示冻结 Workpack 结果 | 普通用户工作区不会学习或污染实验经验；公开历史资料经本地受限只读工具模拟，非生产企业写入。报告为可打印 HTML，不是 PPTX。 |
| V3 全 family 冷启动诊断 | `online-rsi-all-train-saturation-v3`；30 个 train family 的第一个实例各一对 | Baseline 29/30、613,523 token、181 请求、311 工具；RSI 30/30、500,157 token、129 请求、358 工具。RSI token `-18.48%`、请求 `-28.73%`；保存端到端时长为分时交替观察 | 仅可作为冷启动诊断，按设计 Fast=0，不能替代或拼接最终 V4。V3 的本地 overhead 归因错误：约14.3s Composition 模型等待被计入 `compositionLocalMs`；token、请求、工具、任务结果与端到端时长未受影响，但不得用此工件支持 overhead 结论。 |
| 36-task 在线训练对照 | `online-e2e-train-v1`；36 个固定 train 任务 × `plan_react` / `motif_first`，六轮串行 | 基线 36/36、601,435 token、737.62s；RSI 35/36、766,076 token、890.26s。RSI Fast 5 次，Composition/AutoTool 运行时调用均为 0；双顺序 Judge 平均 reward 两臂同为 0.9714，另耗 339,938 token | 历史 Workflow 在 `support-channels-02...06` 实际复用且跳过 Plan，但全量 RSI token +27.4%、延迟 +20.7%，并有一次确定性失败；不能主张总体净收益。完整协议、审计修复和结果见 `online-e2e-train-results-2026-09-10.md`。 |
| 修复后 36-task 分时匹配对照 | RSI source `online-rsi-graph-precheck-v3` + 新 Baseline `online-rsi-graph-matched-v4`；同一固定 train manifest | Baseline 32/36、509,630 token、648.18s；RSI 36/36、386,813 token、502.10s；RSI token -24.1%，模型请求 -93，工具 +65；Judge 72 请求/336,757 token，平均 reward 0.9768/0.9746 | 记录模型名、预算、契约和源码 runtime revision 均匹配，但 provider endpoint 历史指纹未保存，且为分时执行；可主张匹配记录下 token/结构化质量结果，不能称严格同时段或独立 Judge 结论。30% token 目标未达到；六 family 中 `cancelled_payments` +77.7% 为负收益，其余五个获益。详见 `online-rsi-matched-results-2026-09-10.md`。 |
| cancelled_payments 编译修复、规模与并发 | `online-rsi-cancelled-optimized-v4`；`efficiency-scale-reliability-v1` | 修复后的 family 6/6、51,647 token、19 工具；相对兼容历史 Baseline -36.0%。规模 10/30/60 和冻结任务/模型并发 1/2/4 已真实运行 | 编译器正确性修复和 Fast 复用，不是 G1/G2。规模 Baseline 两个 evidence 失败，并发1 RSI一条报告失败；读取峰值固定为1，不能声称工具并发或一般可靠性优势。详见 `efficiency-scale-reliability-results-2026-09-10.md`。 |
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
7. 多代结构进化：新 36-task 流证明 G0 形成和 Fast 复用，但没有正常反馈产生的 G1/G2。
8. 独立/同时段的质量与延迟结论：最终 V4 是同 session 交替串行而不是同时执行，Judge 与执行器同模型且 10 对超时，不能替代独立裁判、重复实验或同时段性能测量。

## 当前问题

- Motif 当前只支持已声明列表字段的精确相等条件；范围、比较、跨字段或列表外条件仍必须交给模型，不能伪装为已编译。
- 发布报告仍可能有重复 evidenceIds、排序/计数错误；图读取正确不保证报告正确。
- Judge 受格式、同模型偏差、顺序影响；分数不是自动可信标签。
- 来源训练任务已知43220 token只是一部分可追溯成本，不是完整研发或学习账本。
- 当前 Composition 候选使用本地字元重叠，且只接受无 gap、至少两个不同 TinyEdge 的组合；这不是论文 embedding retrieval 或完整细化器。

## 验证状态

在 `9520ae7` 功能提交前：104 个 Python 测试、4 个前端回放测试、前端构建通过。本次交接另按用户指令清理旧沙箱；旧沙箱专用测试移除，共用协议测试保留/迁移，没有产生新的模型性能结果。清理后的检查结果在本页末尾记录。

清理后：61 个 Python 测试、4 个前端回放测试、前端构建、300 条任务库契约校验通过。Motif 本轮后为 64 个 Python 测试；本轮 G-Agent 局部组合后为 67 个 Python 测试、4 个前端回放测试、类型检查与前端构建通过。测试数量变化来自删除旧沙箱专用功能及其测试及新增 Motif/TinyEdge 协议回归；当前在线进化、Judge、成对评测与通用协议测试保留。
