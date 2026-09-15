## 2026-09-15 分页式分析演示层

`DataAnalysis` 在筛选和保存结果回放控制之后增加一个共享状态的演示视图层。五个互斥视图分别投影业务结果、记忆进化、成本曲线、请求与可靠性、报告与轨迹；它们读取同一个 `replayVisible` 前缀，所以切换视图不会改变分母、提前读取未来任务或重新执行模型。业务结果提供当前播放任务的紧凑摘要并可进入报告审计；记忆进化集中承载 G0/M0 来源、首次跨任务复用、实质 diff 和后续使用。

标签栏使用可访问的 `tablist/tab/tabpanel` 语义并在长页滚动时保持可见。窄屏将五个标签限制在标签栏内部滚动，页面根节点保持无横向溢出。历史测试组仍复用同一组件和 Analysis Manifest 数据隔离规则。

## 2026-09-15 保存结果回放投影

`DataAnalysis` 继续只读 Analysis Manifest 绑定的单一实验工件。筛选后的完整任务集合是回放上限；播放状态只取其前 N 项作为当前证据范围，并由这同一前缀重算累计 token、成本、串行 latency、模型请求、准确率、执行阶段分解、失败、usage、G/M 创建、实质修订和后续使用。时间线保留未播放任务的冻结题目位置，但把它们显示为待出现；任务账本和选中任务不会读取未来项。这样回放不会提前泄露最终 KPI 或未来修订验证，也不会触发 API 重新执行模型。

初始记忆来源与首次跨任务生效分开表示。第一项成功轨迹结束后保存 G0/M0，只作为来源事实；页面在后续第一项选择同一版本时标记“记忆已构建 · 首次复用”。当前金融12任务中对应 FX01→FX02。实质 G/M 修订仍要求来源 run 和非空 diff，修订后使用仍要求后续 run 记录，三类证据不互相替代。

## 2026-09-15 当前证据的简化投影

Release/Analysis Manifest 仍精确绑定金融12任务候选 `d02f0ecd-8bb5-4359-94be-e7f7233df6a5`，后端身份校验、失败保留和深链不变。展示层将“发布成熟度”与“本组质量”分开：candidate 表示证据范围和审核层级尚未达到formal；本组质量直接按保存评分展示为在线 RSI 12/12、不学习11/12。

`DataAnalysis` 首屏只投影测试组名称、状态和两臂质量结论，不再重复实验ID、runtime、资产、协议、价格快照与质量状态卡；冻结子簇明细默认折叠。若同一筛选范围内在线 RSI 全部通过且两臂usage完整，可显示该固定任务组的累计token、请求和串行时长变化；只有后端正式允许的同质量范围才使用正式“节省”口径，其他范围标为“本组减少”并注明不可跨场景外推。`CurrentEvidence` 使用相同规则，同时保留Release Manifest、具体run、报告、G/M diff和失败审计。

## 2026-09-15 双轨工作区与可续跑 campaign

`POST /api/workspaces/tasks/{taskId}/comparison-runs` 原子创建同一任务的 `plan_react` 与 `graph_rsi` 两个真实 run；前者使用主模型服务凭据且关闭跨任务学习，后者使用 `LLM_API_KEY_SECONDARY` 且开启工作区在线学习。两臂共享任务、附件、27B模型、提示、工具、恢复和预算，调度上限为 `run=2/model=2/read=1`，因此模型请求可以真实并行，读取型工具仍串行。`GET /api/workspaces/comparison-runs/{comparisonId}` 返回 `executionPolicy=parallel_dual_key`、模型、limits、provider profile、学习开关，以及两臂保存的timeline、metrics、evaluation、submission和报告链接；不返回凭据。`WorkspaceWorkbench` 只轮询该DTO，不计算虚构进度。

工作台最后一个workspace和未结束comparison仍通过本地引用静默恢复。可见的旧工作区选择器与追问区已移除；资料预览使用默认关闭的原生 `details`。清空历史记录写入workspace级时间cutoff并删除该workspace的comparison恢复引用，只改变浏览器列表视图，不调用删除API，也不改写任何run、报告、轨迹或实验artifact。

27B真实冒烟 `c762fcdc-e08e-422b-80b0-5ea6968968e6` 验证两次首次模型请求在14ms内开始，调度峰值为2个run和2个模型请求；两臂均通过且usage完整。它是产品执行链验收，在线臂在冷启动后创建G0/M0，但没有后续任务使用，因此不进入正式RSI收益或进化结论。

跨场景正式线在创建时通过 `campaign_plan()` 冻结12、12、24三个阶段和全部48项顺序。`continue_campaign(id, 48)` 只允许在runtime、冻结清单和输入/题面/评分hash一致时恢复同一目录的在线经验并追加剩余任务。campaign `4cfbc988-fab0-4537-b7e2-e509c5cfd76a` 已因基础设施/usage缺口停在stage1的10对；后两阶段未执行，不能补齐或拼接。

## 2026-09-15 跨场景归因运行线

`backend/cross_domain_attribution_assets.py` 从 `trajectory-review-v3-r3` 逐字节复制48个train题面与附件，按三场景/六子簇形成 `cross-domain-rsi-attribution-v1-48`。公开交付契约声明指标语义、字段值口径、业务ID与证据ID边界，以及顶层业务清单由原因组去重合并；这些信息进入系统上下文，不改变用户题面，也不暴露私有评分。

`backend/workspace_compute.py` 的 `granular-compute-v1` 提供 run-local 收据原语：字段映射、映射筛选、键集合限制、业务键清单、按键计数、聚合/对齐/比较、日期时差与异常日期。历史图只保存真实成功工具及 `$output` 依赖，当前数据、字段和值重新绑定。`backend/attribution_experiment.py` 提供 cross-domain smoke/probe/formal；formal 必须由同runtime完整通过的12对probe解锁。

归因运行线分别计算 `qualityGate` 与 `expansionGate`。`qualityGate` 要求两臂同质量全通过，用于同质量成本主张；`expansionGate` 要求12对协议完整、两臂usage完整、在线RSI全通过且真实图执行率至少50%，允许不学习臂的普通业务失败保留为可靠性差异。cross-domain probe遇到普通业务失败继续固定顺序，只有usage丢失、runtime变化或维护故障停止。Release Manifest在新实验完成门槛前仍绑定金融12项candidate。结果边界见 [三场景预检](cross-domain-attribution-probe-results-2026-09-15.md)。

# 当前架构

## 2026-09-14 十二任务候选的冻结子簇投影

当前分析 API 在不改写实验工件的前提下，从同一 `finance-rsi-attribution-v5-12` 任务清单读取运行前已冻结的 `cohort`，投影为订单财务复核 FX01–FX08 与支付结构健康 FX09–FX12。全量12项仍是首要质量账本；子簇只用于解释能力边界，不允许按结果任意挑选成员。订单子簇两臂8/8且usage完整，可显示同质量分层效率；支付健康子簇3/4对4/4，只显示绝对开销、可靠性和修订链。事后排除FX11的11项敏感性结果不进入主卡片。

前端任务类型筛选现在使用该冻结子簇，而不是笼统的“财务复核”。只有后端明确标记 `costConclusionAllowed=true` 的完整冻结子簇才显示token、请求和串行latency变化；全量candidate仍保持 `qualityGate=false`。

## 2026-09-14 十二任务扩大后的候选发布线

最新候选精确绑定 `d02f0ecd-8bb5-4359-94be-e7f7233df6a5`、资产 `finance-rsi-attribution-v5-12` 与 runtime `sha256:11e6f73013a0ad50c4023b637214660087c001cff55a676c354e7aba299d68f4`。同runtime预检通过后，十二任务严格串行运行完整保存。发布层必须显示不学习11/12、在线RSI 12/12及 `qualityGate=false`，不得把原始累计差升级为formal收益；旧六任务formal保持独立。

经验库从空状态形成13节点G0、15节点G1和23节点G2。图执行器分别在FX02–FX09、FX10–FX11和FX12记录实际完成节点；版本加载本身不计使用。运行时语义守卫拒绝 `workspace_aggregate_keyed` 的记录计数别名，错误尝试没有进入版本。G2来源于FX11成功执行，保留可执行的支付业务键频次、状态、月份路径，并增加序号/状态映射和缺失检查，也保留若干重复筛选；架构当前允许保存可审计成功轨迹，但尚未实现基于最终报告依赖的最小化编译。

分析数据源仍通过Release/Analysis Manifest精确绑定实验、runtime、资产、协议和工件digest。candidate显示绝对token、请求、工具、时间、质量和修订链；当任一臂失败时关闭收益结论，失败仍进入曲线分母并可下钻真实run。详见 [十二任务结果](finance-attribution-v5-12-results-2026-09-14.md)。

## 2026-09-14 三任务修订链候选发布（历史）

当时发布和默认分析上下文为 `finance-attribution-v5-repair-probe`，只读绑定实验 `16bbb302-a0eb-49ed-9613-47849aa597be`。它使用 `finance-rsi-attribution-v5-12` 的三个冻结财务实例 `FX01 → FX09 → FX10`，两臂共享模型、提示、通用读取/计算工具、冷启动规划编译、参数绑定、报告恢复、预算和输入；唯一差别是跨任务经验读取与正常 train 学习。

运行时新增 `workspace_distinct_values`，从当前工作区字段计算不同非空值；公开交付定义明确 `period_count` 的当前资料语义，但不包含私有期望值。报告事实恢复现在可继续调用确定性计算工具，不再只开放报告提交。失败只给 M 写负证据，不晋升 G；只有恢复或正常执行最终通过，且编译结构有实质差异时才保存后继版本。

本候选形成 G0→G1→后续使用：FX01创建G0/M0，FX09实际执行G0后从成功轨迹新增支付记录计数、订单状态与月份不同值统计并移除重复读取，FX10实际执行G1/M1全部18个节点。运行后语义审计发现其中 `payment_count` 节点错误地对金额求和，最终正确计数由其他当前观察与模型完成；后续runtime拒绝用 `*_count` 别名包装 sum/max/min。该旧版本只作为已执行的候选修订，不称完全正确模板。分析 API 额外投影执行阶段请求，用于解释收益来自读取/计算选择减少，报告组合仍由当前模型完成。该探针协议排除 formal 指标，因此界面显示候选和绝对计量，不把它扩写成跨场景或长期结论。


## 2026-09-14 细粒度学习归因运行线（历史）

当时正式发布与默认数据分析为 `finance-attribution-v4-6`，绑定六任务实验 `33999392-729d-4af2-8d5b-52fe7b18fcc4`。随后冻结 runtime `sha256:3c4fd75319110c4d6dc5cb53964b82b72c4bdc196eef00092a1dadd738ab8f3d` 完成十二任务扩大验证 `7b3e9244-1a2c-4a85-bad6-18d0cee3bf09`：两臂各8/12通过，质量门槛失败，因此登记为 historical，不替换当前formal。两轮两臂均使用图执行、同一27B模型及共享工具/提示/恢复；区别只在跨任务经验读取与正常train学习。

`backend/workspace_compute.py` 实现 run 内映射、聚合、关联、派生、比较和缺失工具；`ToolContext` 保存仅本次运行的计算收据。执行器为成功收据记录显式上游来源；轨迹诱导把这些来源编译为 `$output` 边，从当前附件重算，不保存旧业务结果。数值转换条件保留模型边界，不阻塞其他兼容子图。工具独立步骤仍可批量调用。

正式六任务资产和工件保持冻结。`backend/attribution_assets.py` 生成并已运行扩大验证资产 `finance-rsi-attribution-v5-12`：
从同一 V3-r3 来源精确复制题面、附件和私有评分，依次使用8个订单对账实例及4个支付结构健康实例，
离线机会标签不进入Agent或匹配器。`backend/attribution_experiment.py` 用独立空经验、交替臂顺序和
严格串行1/1/1运行；formal要求同runtime、同资产的双任务probe已通过，并要求至少50%的在线任务
真正选择且执行保存图，只有版本加载不算命中。正式扩大验证已完成：FX01–FX08订单复核通过，FX09–FX12支付健康任务因期间计数交付缺口失败；在线臂实际图执行11/12但无G/M修订。失败、usage和维护开销全部保存。详见
[工具与复用设计](granular-autotool-design-2026-09-14.md)。下面关于 V3-r3 和更早 runtime 的条目为历史架构快照。


## 2026-09-14 V3-r3 当前运行线

`releases/manifest.json` 当前唯一候选是
`trajectory-p05-v3-r3-candidate` / `trajectory-review-v3-r3`。它冻结 48 个 train、6 个
validation、6 个 test 任务，固定 12 对预检和 `run=model=read=1`；尚未启动。候选题面与工具审阅保留在
“开发与历史 → 当前候选审阅”，不进入数据分析页。

V3-r3 保留 V3-r2 的公开记录选择、切分和来源，并重新冻结题面：用户题面仅保留真实业务目标、
业务阈值/口径、缺失资料语义、业务成果和禁止动作。`metrics`、`groups`、`selectedIds`、
`evidenceIds`、任务编号、工具名和执行顺序不出现在用户题面。财务任务只增加一句可审计口径：订单
为复核主体，支付/商品可一对多，原始金额为分、报告显示 BRL。动态报告工具 Schema 承载机器可检查
交付格式；私有真值不进入模型，`deliveryContract` 不进入模型消息或图匹配输入。

三个场景各有两个连续 cohort、每个 cohort 8 项：首项是合法冷启动，随后七项才有 Fast 复用机会。
完整实验最多有 42/48 的真实机会，预检最多 6/12。`fastReuseMinimumRate=50%` 是候选硬发布门槛：
只计实际 RSI run 的 `planningPath=fast`，未达到时即使其他质量门槛通过也不得晋升或主张 Fast 收益。

V3-r2 的 F01 真实 API 预检 `94620ba7-efd1-4fb9-b323-2bde8b22f78d` 已转为 historical，保留
失败报告、trace 和完整成本，不能进入当前总览。V3-r1 仍为 historical/not-started；更早 V3 9B 预检
`350cd048-9b15-4ead-bae5-073b03ca63ad` 也保留历史审计。它们均不提供当前业务、效率、可靠性或进化结论。

核对日期：2026-09-14。当前前端采用单一发布上下文；业务runtime的既有边界及历史实验保持原义。


## 当前前端与分析数据集

主导航只有 `#home` 数字员工和 `#analysis` 数据分析，全部页面共用 `App.tsx` 的壳。
数字员工面向自由问题、附件、澄清、费用确认、业务成果、结构化清单下载与同工作区追问；
图参数、完整事件、错误和字段契约在技术审计折叠区。可从“继续之前的工作”恢复用户
自己的保存工作区/run。这里不展示实验选择器或 benchmark 总览。旧 `#evidence` 保留兼容，
由 `navigation.ts` 跳转到 `#analysis`。

`releases/analysis-manifest.json` 是数据分析测试组的唯一选择源。默认测试组
`workpack-v17-48` 精确绑定 Workpack V17 实验 `005ffeb9-964e-42ac-86e9-fb9e8f2212fe`；第二项
`taskbank-v4-36` 精确绑定历史 online-e2e V4 实验 `online-rsi-serial-final-v4`。清单为每项声明
`source.kind`，后端只允许固定的 `workpack` 和 `online-e2e` 目录布局，不接受任意工件路径。
`backend/analysis_datasets.py:AnalysisDatasets` 分别校验保存工件 SHA-256、实验 ID、runtime revision、
任务 hash/资产、协议、completed 状态、pair 数和质量门槛；不按创建时间猜实验。
`/api/analysis/datasets` 返回可选测试组，`/api/analysis/datasets/{datasetId}` 将两类历史工件投影为
统一的逐任务 token、串行 latency、成功状态、模型/工具请求、G0/Fast 路径和 run/report 深链。
V4 原始 pair 序号 0–35 作为 `sourceIndex` 保留，界面序号规范为 1–36。任一身份不匹配都拒绝显示。

`DataAnalysis.tsx` 可以按测试组、业务场景和工作流整体切换数据上下文。筛选后的曲线按真实到达
顺序重新累计 Baseline/RSI token、端到端 `durationMs` 和真实 `modelRequests`，同时显示累计
token/latency/大模型调用节省率。累计任务准确率定义为当前范围中结构化校验通过任务数除以已评测
任务数，失败保留在分母；未评分和未知调用数保持缺口，不按 0 补齐。它不是 Judge 分数或模型置信度。
V17 的 12 个 G0 与 35 次 Fast 可展示，但页面明确
说明没有 G1/G2 或匹配规则修订，不能把 Fast 命中称为递归结构进化。V4 也只展示其自身 36 项：
539,468→347,368 token、1,386,926→806,186.644ms 保存串行时长、6 个 G0 与 24/36 Fast；切换时
整套替换上下文，不与 V17 拼接。后续实验只有新增一条精确清单记录后才会成为可切换测试组，
不能把 P0.5 candidate 拼入任何历史曲线。

`releases/manifest.json` 仍负责 P0.5 当前候选与历史发布审计。原 `CurrentEvidence.tsx` 不删除，
从 `#archive?page=candidate` 打开，用于审阅 V3-r3 题面、工具契约和失败证据。`#archive` 继续
保存旧 experiments/trajectory/compare/insights/replay/showcase/live/evaluation/evolution/taskbank/
platforms/demo 深链；历史工件与当前分析测试组之间没有跨版本总计。

## 2026-09-14 工作区轨迹路径（P0.5首阶段）

`backend/trajectory.py` 对通过结构化评分的正常train收据诱导read/compute节点，记录
sourceRun/traceIndex/digest、嵌套当前table/task槽、源请求和操作覆盖描述。临时Plan仍可
用于冷启动，但未执行节点不进入该经验。工作区走当前API/schema硬筛选＋一次有界
语义匹配，不使用family/template/workpackId/difficulty/privateValidation路由；匹配请求
计入同一Agent模型预算与`match`阶段。无法可靠参数化的操作和语义正文留给本次模型。

G保存结构变化；M保存适用描述变化。正常成功同结构在新schema下执行可单独扩展M的
schema约束；结构相同/仅顺序变化不增加G。普通用户只读使用reviewed经验、不学习；
validation/test不写工作区经验。正式六任务已有FA03 G1/M1→FA04实际使用链；原G2/M2仅为重编号，
不作为新的结构进化。

匹配请求保留槽的类型、单位、绑定策略和操作契约，但移除历史 `sourceValue/sourceQuote`，避免把
当前阈值变化误判为不兼容。当前绑定仍须逐字来自当前任务并通过硬校验。选中下游只读/计算节点后，
运行时依据保存图自动加入完整依赖闭包；不存在的依赖、缺失绑定或不兼容类型/单位继续失败关闭。
FA06发布后隔离诊断已验证15个图节点实际执行与当前10期重绑定；该维护结果不改写冻结formal工件。
报告/草稿/导出图调度尚未实现；本地产物仅已具运行内幂等。

`workspace_reconcile_keyed_sums` 支持按键sum/max/min，缺失值返回null并排除相应比较，
保留一对多行证据、独立集合和空集合。`workspace_publish_report.groups` 保存每组
name/reason/condition/count/selectedIds/evidenceIds；组内缩写只从本次唯一观察引用绑定。
所有能力两臂共享，私有真值仅评分；P0.5公开证据范围单独生成，不读取gold补报告。

`trajectory_assets_v3_r3.py` 生成 `trajectory-review-v3-r3` 的六个连续业务 cohort；每项的
自然题面从同一冻结资产生成，离线 cohort 标签不进入 Agent 或匹配器。报告交付字段只存在于
动态工具 Schema，图描述也不再带 delivery contract。`trajectory_experiment.py` 冻结并严格串行
执行，首个质量/usage/维护错误或 Fast 门槛失败都会阻止扩大。旧 V2/V3 结果均为历史审计。

## 目标与边界

用数字员工任务证明相同或更好质量下的 token/cost/latency 改善，并取得递归进化与流程可靠性的独立证据。不是通用 Agent 平台；没有训练或修改基础模型。前端 React/TypeScript，后端 Python/FastAPI，图处理 NetworkX。

核心思想是把可确定执行的结构从模型决策中分离。旧任务库主要覆盖读取图，工作区另支持受限compute片段；不能把它描述成完整业务工作流编译器，也不声称完整复现 AutoTool/G-Agent/MotifAgent 论文。

## 当前任务库路径

```text
React: WorkspaceWorkbench（数字员工 `/#home`） / DataAnalysis（数据分析 `/#analysis`）
       └─ Archive（`/#archive`）→ WorkpackExperimentPanel / CompareExperience / RsiInsights / TaskReplay
                 ↓ JSON API
backend/app.py → WorkspaceManager（上传/预览/追问） / WorkpackExperiment / TaskRunner
                 ├─ ReAct / Strong ReAct
                 ├─ Plan + ReAct
                 ├─ Plan DAG（每次规划）
                         └─ Graph RSI：Fast 完整 Workflow → Composition Persistent TinyEdge → Fallback 完整 Plan
                         ↓
        工具观察 → 模型计算/报告 → 确定性评分
                         ↓
          正常训练任务才可生成后继图
```

| 模块 | 已实现职责 | 不拥有的职责 |
|---|---|---|
| `backend/task_runner.py` | 任务队列、预算、模型/读取并发槽、运行上下文、观察 ledger、trace、恢复和结果保存 | 不实现模型 HTTP 协议 |
| `backend/model_client.py` | 唯一 LLM HTTP 边界，持有连接配置，清洗响应与 usage | 不拥有 Agent 生命周期、业务状态、图库或任务调度 |
| `backend/tools.py` / `taskbank.py` | 参数校验、任务范围内读取、ToolContext 证据、报告提交和事实评分 | 工具说明不直接代表已验证执行依赖 |
| `backend/gagent.py:build_data_plan` | 用规划角色生成字段读取子目标与依赖 | 不要求模型输出隐藏思维链 |
| `backend/autotool.py` | 本地 BM25 工具检索；另有旧 OpenAPI 工具获取能力 | BM25 不是嵌入检索，不消耗 LLM token |
| `backend/intent_graph.py` | 本地选择、契约绑定、分页/foreach 编译、依赖分层执行 | 不编译任意代码，不自动执行业务写入 |
| `backend/graph.py` | 共用 DAG/绑定校验、字段复用与缺失补查；另有旧轨迹编译器 | 有图不等于业务语义已证明正确 |
| `backend/online_evolution.py` / `tinyedge.py` / `tool_inertia.py` | 保存完整 Workflow、按场景和工具契约分区从正常 train 图连续读取链挖掘 Persistent TinyEdge、确定性组合与来源记录；`tool_inertia.py` 仅保留历史记录/契约兼容 | 不执行 TIG 惯性预测，不从图/惯性动作自我强化，也不做 provider 或额外工具 rollout |
| `backend/paired_evaluation.py` | 固定验证/测试任务与图，运行明确的两臂对照，保留失败成本 | 不从评测结果生成经验 |
| `backend/llm_judge.py` | 匿名双顺序报告评分、reward、独立裁判计量 | 不执行 Agent，不改写事实评分，不训练图 |
| `backend/business_report.py` | 所有 Agent 共用 HTML 报告与实际工具证据展示；按场景标注岗位与简报名称 | 不读取 gold 来补写业务结果，也不生成 PPTX |
| `backend/workspace.py` / `workpacks.py` | 隔离用户文件、受限只读资料工具、确定性澄清、同工作区报告/追问、公开来源工作包的相同解析入口 | 不把用户资料写入共享 RSI 经验、评测库或生产平台 |
| `backend/workpack_experiment.py` | 用独立经验库串行运行冻结工作包的 Plan + ReAct / Graph RSI，对所有已启动尝试、恢复和 usage 做配对账本 | 不重写历史工件，不将私有校验或 Judge 反馈回写学习，也不因工作台查看而启动另一侧 Agent |
| `backend/showcase.py` | 只读聚合最终严格串行 artifact，生成全量/三领域聚合、成对任务、保存事件时间步（模型/结构化/控制通道）、DAG/绑定回放和严格报告审计 DTO | 不运行 Agent/Judge，不写经验，不向前端泄漏 gold 或把有限摘要审计称为全面文字事实评分 |

用户粘贴的架构示例中的 `Resolver`、`MotifContext` 是说明性概念，不是当前仓库类名。不要据此未经任务需要重建框架。

## Plan、图与状态

Graph RSI 命中版本时同时复用保存的 Plan 和读取图，规划请求为零。Plan 已去除旧任务自由文本，仅保留字段需求/工具说明；业务 ID 从本次读取绑定，不复用旧观察结果。旧任务库路径匹配使用场景、family、规范化任务模板、工具契约、数据集摘要与执行器版本；工作区已由上面的轨迹匹配路径替代。

当前图节点沿用 Python dict：`tool/arguments/dependencies/foreach/paginate`，可加 `reuse` 和 `defer`。`foreach.filter` 是由 Plan `selection.kind=match` 绑定到已声明列表字段的精确相等筛选：图先读取当前列表、复用筛选字段，只对入选记录调用详情。无法可靠绑定的 Plan 使用 `selection.kind=model`，该详情子图交给模型；当前字段缺失或类型变化也失败关闭并保留上游观察。`reuse.onMissing=detail` 逐条检查并补查缺失字段。没有独立 IR 框架；准确协议见 [graph-ir.md](graph-ir.md)。

编译器记录 `retrievalMs`、`selectionMs`、`compileMs` 和运行时 `bindingMs`；绑定只能来自当前列表/上游输出/字面分页参数。它还会裁剪任务语义无关的独立 detail 步骤、合并等价读取节点。父图不原地改变：发现旧图不兼容时标记 `needs-repair`，仅通过的新正常 train 轨迹才能保存修订图。`filteredOutDetailReads` 和 `elidedToolCalls` 是图内原因计数，不等同于对 ReAct 的净收益。

当前 Patch 有保存来源图、带恢复的字段复用、已获模型有效恢复的失败子图交接、后续正常任务重新规划。未知失败不能凭空生成新图，结构相同不能虚增版本。`probation/family-supported/needs-repair` 表示适用证据与修订状态；不是全场景推广或统计显著性证明。

Graph RSI 的规划路由是 Fast（同任务模板/工具契约/执行器的完整图，Plan 请求为零）、Composition（Fast 未命中而有 support>=2 的 Persistent TinyEdge 时，composition 角色只生成粗子目标，本地确定性选择/组合）和 Fallback（覆盖、来源或契约校验不足时生成完整 Plan）。TinyEdge identity 共享 tool、输入输出契约和绑定槽，连续读取链以 `defer`、扇入/扇出与非连续依赖为边界；执行器消费已选 ID 而不再调用模型重选。当前候选检索是本地字元重叠而非论文 embedding，详细差异与实证边界见 [g-agent-local-composition-design-2026-09-10.md](g-agent-local-composition-design-2026-09-10.md)。

AutoTool/TIG 惯性执行已经退役：保留历史轨迹读取与共享参数契约，当前 Graph RSI 不在模型交接点预测或抢占工具调用。回放仍会区分历史惯性字段，避免把历史实验误称为当前机制。

## 数据与评测

- 公开历史任务库：Olist 财务、CFPB 投诉、Zammad GitHub Issues 技术工单，各 100 任务；每场景 10 family，每 family 10 实例，6 train / 2 validation / 2 test。
- 财务/客服/工单每任务分别 10/5/3 条记录。同 family 指令高度模板化，记录不同；不是 300 种独立需求。
- 来源数据库在 `artifacts/taskbank/records.sqlite3`。`gold.json` 仅供确定性评分，不进入 Agent 或裁判输入。
- 工作包数据：公开历史记录经同一文件解析器重组为 CSV/JSON/TXT；总库 72 项，每场景四类工作流，每类 4 train、1 validation、1 test。V17 全量实验只使用冻结的 48 条 train 工作包；私有声明式校验不进入模型上下文。
- LLM 裁判分别输出事实、覆盖、可读性 0–10 分；后端计算 `(0.5F+0.3C+0.2R)/10`，两次顺序取均值。reward 不含成本，不是成功概率。

## 平台路径与已删除沙箱

`service.py/runtime.py/graph_store.py` 保留真实平台只读路径，旧 GraphStore 的平台图验证成本单列。合成业务数据、sandbox_tools、fixture_provider、沙箱专用 evolution/reliability/negative_motif 和对应页面/API已删除。当前在线失败子图修订能力仍在 `online_evolution.py`，没有一起删除。

ERPNext/Zammad 已有部署与只读连接器，但初始化的业务记录属于项目生成的种子记录。GitHub Issues 是真实软件问题记录，不等于企业内部客服工单。当前任务库与已部署平台数据库也不是同一个数据源。

## 入口与文件

前端 `5173` 默认 `#home`，数据分析为 `#analysis`（旧 `#evidence` 兼容跳转）；旧 `#experiments`、`#compare`、`#insights` 和 `#replay?task=<id>` 统一重定向到历史区域。默认主页是一个可交互的企业运营数字员工工作台：切换财务、客服、技术工单能力后，用户拖拽/选择 CSV/XLSX/JSON/TXT，并手写业务请求；资料预览、确定性澄清、费用确认、真实 Agent、同一 run 的 DAG、模型/结构化/工具事件、HTML 报告、导出和同工作区追问都由保存 run ID 关联。每个工作区使用可读目录名（如 `finance-取消订单复核-a1b2c3d4`），完整 UUID 只作为内部 API、证据和运行关联身份。用户输入保持可读布局：`inputs/` 是原始附件，`requests/` 是已提交问题文本，`.rsi/` 仅保存解析表、任务状态和内部草稿；普通用户运行使用独立目录且 `learning_enabled=False`，不会污染实验经验。旧根目录 JSON/`sources/` 与 UUID 目录工作区仍可恢复，但不在恢复时迁移或改写。`#home` 不展示 Workpack、预置题目或历史 pair；`#analysis` 只读取分析清单固定的一个保存实验，历史 `#experiments` 在 archive 中保留完整控制台。`#compare`、`#insights` 和 `#replay` 保留历史 V4 的只读展示。公开资料经本地受限只读工具访问，不能称为生产企业写入部署；后端为 `4317`，模型配置只在根 `.env`。

运行与恢复命令、配置字段、持久化位置见 [.codex/state.md](../.codex/state.md)。实验结论见 [EXPERIMENT_STATUS.md](EXPERIMENT_STATUS.md)，不要从截图或旧 README 推断当前性能。

`scripts/run_online_e2e.py` 是独立的 36-task 在线训练对照入口。它创建专用 run/experience 目录，基线禁用学习，RSI 仅从此前正常 train 任务更新经验；每次启动后立即 checkpoint run ID，避免恢复时重复学习。`--rsi-source` 只复用已审计的 RSI-only source，并在新目录补跑匹配 Baseline；结果明确标注为分时匹配。静态页由 `/api/online-e2e/{id}/report` 提供，并按 family 给出六条经验形成/复用与准确 trace/report 入口。

完成的严格串行工件 `online-rsi-serial-final-v4` 额外从原始 run 聚合 P95/最大延迟、最大 token、报告恢复、维护、分页和 phase token。它只生成派生摘要，不会重放 Agent/Judge；Agent 成本与 Judge 的已记录 token 下限分开显示。最终证据边界见 [online-rsi-serial-final-results-2026-09-11.md](online-rsi-serial-final-results-2026-09-11.md)。

展示层的严格报告审计不会改变上述原始结构化 evaluation：它再次核查报告 schema、metric/selection/evidence 精确性、证据在当前 trace 中确已观察，并以有限规则检查摘要中的已知 ID、数字和 `cents` 金额表述。gold 仅在后端进程内用于得到布尔结果；不返回预期答案或未通过的具体业务真值。

## 正式运行前任务审阅

`ReleaseEvidence` 对 `trajectory-plan` 发布返回 `taskReview`：六个业务契约、输入表字段、
8个train题面变体、预检位置和公开来源。题面由 `request_for()` 生成后与冻结资产中的
`requestHash` 逐项核对；数量、版本或题面不一致均失败关闭。`CurrentEvidence` 在 archive 的候选审阅入口中
展示该审阅清单，并把质量、成本与回放明确显示为“尚未运行”，不显示0/0 usage卡或空方法回放。
该读取路径不创建实验、不加载私有答案、不调用模型。内容审计见
[正式运行前任务审阅](trajectory-v3-run-approval-review-2026-09-14.md)，两臂实际工具面与报告
Schema见[任务与工具契约审阅](trajectory-v3-task-and-tool-review-2026-09-14.md)。


### V3-r2 历史失败预检与 V3-r3 候选投影

`ReleaseEvidence` 对 candidate 的已保存 trajectory experiment 执行 runtime、资产、协议和 pair/run 身份校验。未运行的 V3-r3 只显示冻结任务审阅，不显示指标或曲线；若预检 `quality_stopped`，对应历史 release 只保留同一运行的失败报告、输入、轨迹和绝对开销。节省率/累计收益曲线关闭，直到完整质量门槛通过。

### 数据分析成本投影（2026-09-14）

`AnalysisDatasets` 在读取固定实验 artifact 时同时读取 `releases/analysis-manifest.json` 中的版本化 `modelPricing` 快照。`/api/analysis/datasets/{id}` 返回每个 run 的输入/输出 token、实际角色模型、USD 估算成本和独立累计曲线。角色模型一致时按 run 总 token 计费；角色不同只在 `phaseMetrics` 与总 usage 完全闭合时按 plan/match→planner、composition/compile→composition、execute/graph→executor 计费。任何缺口返回 `null`，前端保留曲线缺口，绝不以 0 或默认模型补写。
