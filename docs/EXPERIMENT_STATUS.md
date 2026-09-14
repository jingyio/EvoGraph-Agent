# 实验状态与可主张的结论

## 2026-09-14 十二任务扩大验证完成

- probe `fd0bbc4c-9297-43fb-ac81-1cec05f4b991` 满足2/2质量、usage和50%实际图执行门槛。formal `7b3e9244-1a2c-4a85-bad6-18d0cee3bf09` 随后严格串行完成12×2，runtime `sha256:3c4fd75319110c4d6dc5cb53964b82b72c4bdc196eef00092a1dadd738ab8f3d`。
- 两臂均8/12通过且usage完整。FX01–FX08订单复核全部通过；FX01创建G0，FX02–FX08实际使用。FX09–FX12支付健康任务两臂均失败，集中缺少正确 `period_count`，并出现有界报告恢复终止。
- 在线臂实际图执行11/12（91.7%），但没有G/M实质修订。该指标只说明旧子图被执行，不能覆盖任务失败，也不能被称为反馈进化。
- 绝对总量为1,467,397→1,401,822 token、124→88请求、1,140.885→925.425秒、44→21工具错误。质量门槛失败，因此4.47% token差与18.89%时长差不展示为收益；FX11/FX12的在线恢复长尾完整保留。
- 该结果登记为 historical `finance-attribution-v5-12-expanded`。当前formal仍为 `finance-attribution-v4-6`，不同实验不拼接。
- 本轮验证为222项Python、16项前端、构建、API深链和浏览器闭环通过；390px无横向溢出。


## 2026-09-14 六任务学习归因正式发布

- 当前发布/默认分析同为 `finance-attribution-v4-6`，精确绑定实验 `33999392-729d-4af2-8d5b-52fe7b18fcc4`、资产 `finance-rsi-attribution-v4`、协议 `finance-graph-rsi-learning-attribution-v4` 和 runtime `sha256:0a97c2949a483492485bd414a7d7b7cebeeef306e625af6dc4990bcbea015207`。状态 formal；不复用旧V17/V4指标。旧V3-r3候选与V1停止实验转历史审计，原工件不改写。
- 同一图执行Agent，不学习与在线RSI各6/6结构化事实/证据通过，usage完整。token 944,492→549,900（节省41.7782%），模型请求72→42，串行耗时651.867→548.372秒（节省15.8767%）；工具错误21→12均保留，正文没有独立Judge/全面人工质量评分。
- 4/6任务实际部分历史子图复用；FA06匹配错误拒绝可变槽并缺依赖闭包，安全回退后通过，13请求/183,752token/170.786秒全部计入。此处不冒充完整Fast命中或满足旧48任务Fast发布门槛。
- 发布后维护验证没有改写正式工件：诊断 `d047dea8-8dfe-4fd7-8e3c-ecfd4806a72f` 因错误关闭学习而冷启动（14请求、216,002 token、104.149秒）；修正配置及匹配器后，诊断 `d7dd21a0-570c-4a59-9f15-bf5d51566b2d` 从FA06之前的独立经验状态实际使用版本 `4a9f228d-4917-4afe-80a4-f2fa6f85f31f`，当前10期阈值成功重绑定，15个图节点完成，结构化评测通过，3请求、40,158 token、62.880秒、17工具调用且0错误。该单次跨runtime结果只验证FA06阻塞已消失，不加入formal收益曲线。
- 数据分析页已把上述两份诊断投影为单独的“发布后维护验证”，原六任务KPI与累计曲线仍只读取formal工件。下一轮 `finance-rsi-attribution-v5-12` 已冻结12个财务实例和50%实际图执行率门槛；先运行同runtime双任务probe，通过后才启动12任务×2臂formal。
- FA03正常反馈产生状态覆盖扩展G1/M1，FA04实际执行新增筛选节点。原始G2/M2为图重编号/顺序变化，展示审计排除其进化主张，原工件保留。M1是覆盖描述扩展，不证明独立匹配纠错算法。
- 新计算接口、run内收据与来源依赖已实现；不添加完整AutoTool/TIG。正式运行源码快照保持不变；后续维护器已补充与节点ID/顺序无关的结构比较及协议回归，并完成上述隔离真实API诊断；正式发布仍指向冻结运行的原runtime。
- 交付文档 `docs/teacher-rsi-attribution-delivery.md`，三分钟脚本 `docs/teacher-rsi-attribution-recording.md`。前端支持六任务点击、同release问题/附件/两臂成果、真实调用回放与报告下载，曲线只读取本实验。
- 最终验证：217项Python测试、14项前端测试、TypeScript/Vite构建和`git diff --check`通过。浏览器验证唯一当前发布、六任务下钻、FA03实质diff、FA04实际使用回放、同run下载、历史隔离与390px宽度。
- 剩余：48任务、其他两场景推广、独立Judge、长期可靠性及匹配器稳定性；不得由本次六实例主张普遍收益。共享.env仍9B，真实实验进程统一27B/thinking关闭。


## 2026-09-14 V2 smoke 审计与 clause IR 机制修复

冻结实验 `c0a387c3-5272-4a24-8743-9bd6ed821c13` 的 RSI run
`5879a866-a4e0-423c-bc04-357c0f2dfe88` 最终通过结构化报告校验，但使用 13 次模型请求、
175,453 输入 token 和 94.321 秒。请求构成为 1 次 plan、11 次执行工具决策和 1 次报告；两个工具错误
分别是 `comparisons` 字符串类型错误和 `group_count` 缺 `groupBy`。这说明该任务成功，但执行与上下文
回灌成本过高，不能用它主张 RSI 已节省调用或 token。

当前编译器已把一条成功 `workspace_reconcile_keyed_sums` 收据拆为 aggregate、derivedTotal、逐条
comparison 与 missingByAlias obligation，并在回放前校验依赖、别名、Schema 和当前槽，随后合并为一次
物理调用。用冻结 V2 trace 只读重编译得到 3 aggregate、1 derivedTotal、1 差额 comparison 和 3 missing
片段；`0.05 BRL` 精确绑定为5分，两个 `missing_* equals 0` 伪比较停留在模型边界。该结果是无模型机制
验证，不是新的在线效果实验；旧 V2 JSON 与 experience 均未改写。全量 Python 208 项、构建和 diff 检查通过。

## 2026-09-14 数据分析补充调用次数与准确率

V17 48-task 和 V4 36-task 现在都从各自保存 run 绘制累计大模型调用次数，并以结构化任务通过数/
已评测任务数绘制累计准确率。V17 为 258→149 次调用、两臂 48/48（100%）；V4 为 203→114 次
调用、两臂 36/36（100%）。这些准确率只覆盖冻结任务的结构化事实与证据校验，不代替 Judge 或
人工文字质量审查；未来失败会保留在分母，未评分项保持数据缺口。

## 2026-09-14 V3-r3 当前候选；V3-r2 真实失败预检转历史审计

当前 Release Manifest 指向 `trajectory-p05-v3-r3-candidate` / `trajectory-review-v3-r3`。它保留
V3-r2 的 60 个公开记录选择、切分、私有评分边界和六个连续 cohort；唯一题面变化是每个财务请求
增加一句业务数据口径：订单为复核单位，支付/商品可一对多，原始金额以分保存、报告按 BRL 展示。
题面仍不包含任务编号、工具名、执行顺序、`metrics`、`groups`、`selectedIds` 或 `evidenceIds`。

运行时同时修复三项跨场景问题：通用提示要求按 schema 核对类型/单位且不将缺失当零；对账工具明确
文本业务键与数值聚合字段、比较数组和原始单位阈值；模型上下文仅压缩字节完全相同的重复行观察，完整
ledger、工具 trace 和失败开销仍原样保存。V3-r3 尚未启动 12 对严格串行预检，也没有业务、效率、
可靠性、Fast 或进化结论。实际 Fast 命中率仍须 `>=50%`，并与质量、usage、维护门槛同时通过后，才可
扩大到 48 对正式对照。

`trajectory-p05-v3-r2-candidate` / `94620ba7-efd1-4fb9-b323-2bde8b22f78d` 已转为 historical。
F01 两臂都在质量门槛失败后停止：Baseline 的 `metrics` 未通过；RSI 的 `metrics`、业务 ID 清单和原因
分组未通过。它的 token、工具、延迟、报告和完整 trace 均保留，69.60% 的诊断性 token 差不能作为收益。
其余 11 对预检、48 对正式对照、validation 与 test 均未运行。


## 2026-09-14 V4 36-task 已加入数据分析独立测试组

`taskbank-v4-36` 只读绑定 `online-rsi-serial-final-v4`，状态标为 historical。两臂均为 36/36
结构化事实与证据通过且 usage 完整；Baseline/RSI token 为 539,468→347,368（节省 35.6092%），
保存的端到端串行时长为 1,386,926→806,186.644ms（节省 41.8724%），LLM 请求 203→114，
工具调用 274→277。RSI 实际 Fast 24/36（66.7%）、形成 6 个 G0、Fallback 12、Composition 0。

该历史结果没有 G1/G2 或匹配描述修订，不能用来主张递归结构进化。latency 包含 provider 等待、
恢复和工具执行，不能解释为稳定纯推理加速。页面切换到 V4 后，36 个任务点、筛选、KPI、轨迹与
报告都来自同一 V4 工件；切回 V17 时整体恢复 V17 数据，不进行跨实验拼接。

## 2026-09-14 V17 48-task 数据分析入口

主导航的第二入口现为 `/#analysis`。它不代表 P0.5 当前 runtime 已完成，而是从独立
`releases/analysis-manifest.json` 选择完整保存测试组。首个测试组
`workpack-v17-48` 只读取 V17 `005ffeb9-964e-42ac-86e9-fb9e8f2212fe`：48/48 对通过，
token 2,244,017→1,243,546（节省 44.5839%），保存的端到端串行时长
3,215,447ms→2,349,744.47ms（节省 26.9232%），请求 258→149，工具 422→325。

这些 latency 是每个保存 run 的 `durationMs` 串行求和，包含模型服务等待、恢复与工具执行，
不能解释为稳定的纯推理速度优势。测试组中有 12 个 G0、35 次 Fast、13 次 Fallback，
没有 G1/G2 或匹配规则修订。页面只把它作为复用和成本变化展示，不主张递归结构进化。
场景/工作流筛选、曲线和逐任务报告均留在同一 V17 成员集合；P0.5 candidate 不会补入。
实现后验证：Python 193/193、前端 8/8、TypeScript/Vite 构建和 `git diff --check` 通过；真实浏览器检查 `#home`、`#analysis`、财务/单工作流筛选、报告下钻、旧链接跳转、候选审阅与 390px 宽度均通过。

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

> **2026-09-14 工作台题库与保存同题回放（已替代）**：该临时首页展示曾读取冻结 train
> Workpack 的保存 V17 pair，未启动新 Agent 或改写实验数据。后续产品决定已将它从 `/#home`
> 移除；首页只接收用户上传资料和手写业务请求。Workpack 与已保存对照继续仅在
> `/#experiments` 的实验语境中保留，不影响历史 V17 结论。

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

2026-09-14 阶段末验证：163项Python协议测试、4项前端回放测试、TypeScript/Vite构建、git diff --check通过。三岗位浏览器首传/解析/请求准备与同run报告下载已检查；这些不是额外模型实证。

## 2026-09-14 · V3-r2 真实 API 预检首对失败（保留）

实验 `94620ba7-efd1-4fb9-b323-2bde8b22f78d` 以 `qwen/qwen3.5-9b`、thinking 关闭、`run=model=read=1` 运行 F01 的 Baseline/RSI 成对真实 API 调用。两臂 usage 完整，但均未通过私有结构化验收，协议在首对后 `quality_stopped`，其余 11 对预检和 48 对正式对照均未运行。

- Baseline：`limited`；24 模型请求、31 工具调用、1 工具错误、609,579 token、144.346 秒；报告 `metrics` 不匹配。
- RSI：`limited`；13 模型请求、20 工具调用、3 工具错误、185,288 token、111.181 秒；报告 `metrics`、`selectedIds`、`groups` 不匹配；冷启动 `fallback`。
- Fast：0/1，未达到 50% 门槛；无 G/M 修订、无后续使用。

表面 token 差仅为失败诊断，不能主张效率、质量、可靠性或进化收益。主要待修复点是单位/一对多汇总与报告交付契约的一致性；本次原始运行、失败报告与全部开销保留在本地 artifacts。

## 2026-09-14 · 分析页成本估算（非新增实验）

未运行任何模型调用，也未改写 artifact。`#analysis` 新增模型成本估算 KPI 和累计曲线，计费依据固定在 Release/Analysis Manifest：27B `$0.195/M` 输入、`$1.56/M` 输出；9B `$0.080/M` 输入、`$0.130/M` 输出（OpenRouter 标准价格快照，2026-09-14）。V17 48-task 的保存 token 对应 Baseline `$0.563529`、RSI `$0.350068`，估算差 `37.8793%`；V4 36-task 对应 `$0.151395`、`$0.104017`，估算差 `31.2941%`。这些是历史保存运行的标准价估算，不是供应商账单。归因候选的 RSI usage 不完整，成本累计从缺口处留空，未主张节省。
