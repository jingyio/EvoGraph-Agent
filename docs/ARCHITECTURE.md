## 2026-09-15 未使用槽绑定的有界规范化（最新）

轨迹匹配分为两步：模型提交候选图的 `nodeIds` 与当前参数 `bindings`，运行时先对所选节点求完整上游依赖闭包，再计算闭包真正引用的槽集合。模型可能先填写某节点参数、随后在同一选择中排除该节点；旧实现会因这种无执行影响的多余绑定拒绝整次图复用。

`_bind_one` 现在仍先拒绝重复槽和所选闭包缺失槽，再仅从物化绑定中剔除闭包未引用的额外槽。额外槽不会进入 `resolve_arguments`，因此不能改变任何执行参数；原始 matcher DTO 保存在 `trajectoryMatch`，被剔除的槽另存为 `trajectoryMatchNormalization` 并产生事件。逐字 quote、值、类型和单位校验继续作用于所有实际使用槽。该边界只容忍无效载荷，不补节点、不推导值、不改变 matcher 的覆盖声明。

真实单臂 run `1c904b6b-9f90-46f6-b3f8-b0a522ab6998` 没有触发规范化，因为新一次 matcher 直接选择了23个节点并完整绑定两个10期槽；运行时执行冻结 G2/M2 后只向模型交回未覆盖的金额差比较与报告。3次模型请求分别消耗5,012/22,109/22,375输入token，证明图回放路径已恢复。该单臂诊断不建立新的跨臂latency结论。

## 2026-09-15 工作区 Agent 正常路径恢复的并行诊断（历史）

工作区三臂在创建时共享一个请求级 runtime profile：`computeInterface=granular-compute-v1`、当前附件全部行组成的 `publicScopeEvidenceIds`、`runtimeEvidenceBinding=current_scope_and_group_receipts_v1`。该 profile 只改变工具面、公开证据范围和证据绑定方式，不修改保存的用户任务或历史工件。A/B/C因而读取相同输入、使用相同细粒度工具和报告协议；A/B使用主Key，C使用Secondary Key，并由`TaskRunner(3/3/3)`并行调度。

报告阶段不再要求模型复制完整顶层或分组 evidence ID。运行时仅在当前范围已实际观察后补齐顶层证据；分组证据只从本run成功计算收据的`evidenceByKey`和当前观察集合绑定。模型仍必须提交业务指标、业务ID、原因、条件、数量和正文；运行时不补金额、ID、空组或结论，也不读取gold。进入报告上下文前移除`_evidenceRef`和`evidenceByKey`的大型重复映射，保留计算结果本身。报告校验失败继续走共享的有界恢复，不再由演示策略在首份失败报告后终止。

冻结发布知识库具有显式兼容路径。普通只读经验仍要求审核状态与精确contract hash；只有Release Manifest已绑定的`frozen_finance_release`可读取其probation版本。contract hash不同必须逐节点确认工具仍存在、effect一致、依赖存在且`$output`首段仍是生产工具声明输出；回放时当前工具schema继续验证实际参数。run记录`contractCompatibility=node_schema_revalidated`，避免把“加载版本”冒充执行。

真实验证`9c354b04-6373-4333-80d2-8967b8d50dc1`中，C使用G2/M2执行23个图节点，模型只补1个未覆盖计算和报告；报告输出602 token。A/B报告输出791/808 token。该结果恢复了正常时期“匹配→当前绑定→图回放→模型补残余/报告”的设计，无需用completion截断掩盖长证据数组。

## 2026-09-15 严格串行三臂调度与有界报告完成（最新）

新建工作区三臂 comparison 使用单一主模型凭据，并由共享 `TaskRunner(run_limit=1, model_limit=1, read_limit=1)` 按 A 传统 Plan+ReAct、B 图执行不学习、C 图执行在线 RSI 的创建顺序串行调度。每个新 run 保存 `comparison.executionPolicy=strict_serial_three_arm`；聚合 DTO 只在三个保存 run 都带该策略时返回串行策略和 `1/1/1` 限额。旧记录缺少该字段时继续返回历史并行策略，防止把旧时长误标为串行计量。

执行器在当前附件已有成功确定性计算、但尚未提交报告时，为终态报告保留一个完整模型调用窗口；模型请求只剩一次时直接限制为报告工具。若同一个成功确定性计算随后以完全相同参数连续两次被守卫拒绝，运行记录 `duplicateComputeFinalizationGuards` 和来源签名，然后进入仅允许 `publish_report` 的边界。严格串行演示额外在完整 `workspace_reconcile_keyed_sums` 成功后立即进入精简报告边界，要求摘要不超过500字且只引用结论所需的已观察证据。首次报告保存后立即释放串行槽：校验通过正常完成，校验失败保存报告并以失败评价完成，不发起二次模型恢复。该演示策略由保存的 execution policy 触发，不改变正式离线实验的恢复协议。

工作区公开任务 DTO 增加 `sourceStatus`。历史 run 列表用公开任务读取路径识别附件已删除的任务；前端静默恢复时清除对应本地引用，不将“任务引用的资料已被移除”作为全局红色错误显示。历史 run、报告、轨迹和错误账本保持不变。

## 2026-09-15 三臂发布解析与精简演示层（最新）

实测在线 RSI 不再在 `backend/app.py` 固定实验 ID。后端从 `releases/analysis-manifest.json.defaultDatasetId` 读取唯一默认数据集，要求其来源为 `attribution`、归因类型为 `cross-task-learning`，随后完整校验实验工件摘要、runtime、资产、协议和任务范围；只有全部任务均为财务场景且对应 `online_rsi/experience.json` 存在时，才把该经验库只读注入 C 臂。返回 DTO 同时携带 `datasetId` 与 `experimentId`，确保实测页和数据分析页使用同一发布上下文。

演示层只保留三张一句话方法卡、A→B/B→C 归因和完整题面。模型、双 Key 分配、知识库身份与计时口径进入默认折叠的“实验说明”；三臂尚未启动时不渲染空指标、空报告和重复等待面板。启动后才显示真实阶段、核心指标、报告和可折叠审计。真实事件仍按800ms轮询，阶段时间来自后端事件时间戳。

验证：Python 259项、前端38项、生产构建和 `git diff --check` 通过；浏览器在1280px宽度下无横向溢出。费用确认保持未勾选，本轮没有产生新的付费模型运行。

## 2026-09-15 实测对比增加传统 Plan + ReAct 参考

`POST /api/workspaces/tasks/{taskId}/comparison-runs` 现在为同一题目和附件同时创建三条真实运行：`plan_react` 传统参考、空经验且禁止读写的 `graph_rsi/no_learning`、只读加载金融12任务冻结知识库的 `graph_rsi/online_rsi`。三臂均固定 `qwen/qwen3.5-27b`、相同工作区工具、报告恢复、预算和输入。A→B用于观察传统规划与图运行时的差异；B→C才隔离跨任务学习贡献，避免把冷启动编译收益误称为RSI学习收益。

实测工作区调度为 `run=3/model=3/read=3`。传统参考与不学习臂使用主Key，在线RSI使用Secondary Key；三条模型请求可以同时进入运行时，本地只读工具也不再由共享 `read=1` 人为排队。该改动只作用于交互演示工作区，不改变正式归因实验的冻结串行/双Key协议。对照DTO声明 `design=plan_react_graph_learning_three_arm`、`executionPolicy=parallel_three_arm_two_key`，并继续兼容此前两臂和旧 `plan_react`/`graph_rsi` 历史记录。

前端增加三臂真实阶段对照，按保存的 `model_start`、匹配、绑定、工具、报告与终态事件显示当前阶段，并用事件时间戳显示该阶段实际持续时间，不生成百分比或模拟进度。弹窗统一为“传统 Plan + ReAct”“图执行 · 不学习”“图执行 · 在线 RSI（金融经验）”，图执行正文不再把不学习臂误称为RSI。

## 2026-09-15 实测对比使用当前金融知识库

`POST /api/workspaces/tasks/{taskId}/comparison-runs` 现在创建两个相同 `graph_rsi` 运行时。`no_learning` 臂使用进程内独立空 `OnlineEvolution`，禁止跨任务读写并从当前任务重新规划和编译；`online_rsi` 臂只读加载实验 `d02f0ecd-8bb5-4359-94be-e7f7233df6a5/online_rsi/experience.json` 的3个冻结版本。两臂通过主Key与Secondary Key并行运行，共享模型、提示、工具、预算和当前输入；B仍对当前附件重新绑定金额、阈值和业务ID。

`TaskRunner.start` 支持显式 `evolution_override` 与独立的 `learningWriteEnabled`。这让B可以读取已学习知识而不把演示任务写回证据库。每个run保存 `comparison.arm`、`experience.mode/releaseId/versionCount/readOnly`；对照DTO声明 `design=same_graph_runtime_learning_ablation` 和知识库身份。旧 `plan_react` vs `graph_rsi` comparison 仍可按历史arm读取，但新实测不再用它生成指标。

## 2026-09-15 工单独立归因运行线（最新）

最终演示按两个独立证据上下文展示：财务继续读取已完成的12项候选实验 `d02f0ecd-8bb5-4359-94be-e7f7233df6a5`，不重复运行；技术工单使用新的 `tickets_probe` / `tickets_formal`。工单清单在运行前从 `cross-domain-rsi-attribution-v1-48` 精确冻结 `T01–T12`，预检只运行 `T01,T02`。客服及此前跨场景失败完整保留在历史审计，不进入最终主展示。

工单每个 pair 同时启动两臂：不学习臂使用主 Key，在线 RSI 使用 Secondary Key；两臂均固定 `qwen/qwen3.5-27b`、thinking关闭，共享提示、工具、恢复、预算和输入。全局调度 `run=2/model=2/read=1`，单臂内部仍为 `1/1/1`。两臂运行目录和经验文件隔离；不学习臂每项后强制验证版本数仍为0。工单 formal 必须由同 runtime、同资产且两臂全部通过的 `tickets_probe` 解锁。

## 2026-09-15 财务与技术工单双场景运行线

`AttributionExperiment` 新增 `finance_tickets_probe` 和 `finance_tickets_formal`。它们从已有48项来源资产在运行前固定选择 `F01–F12` 与 `T01–T12`，不读取旧实验结果决定成员；四对预检只取两个场景的第1、2项，验证冷启动和首次复用。客服工件不删除，仍由旧实验深链审计。

双场景模式给不学习臂和在线RSI臂分别注入主Key和Secondary Key的同模型客户端。每个pair并行创建并等待两臂，两个runner共享一个读取信号量，因此总体调度为2个run、2个模型请求、1个读取；每臂经验文件和运行目录隔离。不学习臂在每项后继续验证经验版本数为0。

## 2026-09-15 相对质量扩大门槛

跨场景campaign在创建时冻结 `maximumOnlineQualityGapTasks=1`。stage1完成12对后，以同一任务集合比较“图执行 · 不学习”和“图执行 · 在线RSI”的通过数；在线RSI最多少通过1项，同时要求两臂usage完整、维护无错误且真实图执行率至少50%，才进入stage2。严格 `qualityGate` 仍要求两臂全部通过，并继续单独控制同质量成本主张。旧实验缺少该冻结字段时沿用原规则，不追溯放宽。

## 2026-09-15 数字员工宽屏对比与瞬时执行投影

`WorkspaceWorkbench` 将资料、题面和历史记录保留在顶部三列工作区，将双轨对比作为其后的全宽兄弟区域渲染。这样资料/历史侧栏不再贯穿完整执行卡高度，长题面只在全宽对比头部展示一次，两臂在普通桌面宽度继续并排。

执行过程有两个投影：默认折叠的完整事件账本负责审计；右上角通知栈只读取各run最新保存事件，运行时随800ms后端轮询更新。每臂独立按事件序号触发约3.1秒的淡入、停留和淡出，并从该事件展示当前表、记录数、业务阈值、token、图节点或G版本等真实实例值。通知不驱动run、不伪造进度；组件只有在当前页面生命周期内观察到该run处于queued/running后，才允许显示执行和紧随其后的终态事件，因此刷新或切换到历史完成run不会误弹。完整事件和报告仍留在页面。

## 2026-09-15 分页式分析演示层

`DataAnalysis` 在筛选和保存结果回放控制之后增加一个共享状态的演示视图层。五个互斥视图分别投影业务结果、记忆进化、成本曲线、请求与可靠性、报告与轨迹；它们读取同一个 `replayVisible` 前缀，所以切换视图不会改变分母、提前读取未来任务或重新执行模型。业务结果提供当前播放任务的紧凑摘要并可进入报告审计；记忆进化集中承载 G0/M0 来源、首次跨任务复用、实质 diff 和后续使用。

标签栏使用可访问的 `tablist/tab/tabpanel` 语义并在长页滚动时保持可见。窄屏将五个标签限制在标签栏内部滚动，页面根节点保持无横向溢出。历史测试组仍复用同一组件和 Analysis Manifest 数据隔离规则。

## 2026-09-15 保存结果回放投影

`DataAnalysis` 继续只读 Analysis Manifest 绑定的单一实验工件。筛选后的完整任务集合是回放上限；播放状态只取其前 N 项作为当前证据范围，并由这同一前缀重算累计 token、成本、串行 latency、模型请求、任务通过率、失败、usage、G/M 创建、实质修订和后续使用。时间线保留未播放任务的冻结题目位置，但把它们显示为待出现；选中任务不会读取未来项。模型请求的内部工具类别继续存在于保存 DTO 中供离线审计，但不进入导师主展示。这样回放不会提前泄露最终 KPI 或未来修订验证，也不会触发 API 重新执行模型。

初始记忆来源与首次跨任务生效分开表示。第一项成功轨迹结束后保存 G0/M0，只作为来源事实；页面在后续第一项选择同一版本时标记“记忆已构建 · 首次复用”。当前金融12任务中对应 FX01→FX02。实质 G/M 修订仍要求来源 run 和非空 diff，修订后使用仍要求后续 run 记录，三类证据不互相替代。

## 2026-09-15 当前证据的简化投影

Release/Analysis Manifest 仍精确绑定金融12任务候选 `d02f0ecd-8bb5-4359-94be-e7f7233df6a5`，后端身份校验、失败保留和深链不变。展示层将“发布成熟度”与“本组质量”分开：candidate 表示证据范围和审核层级尚未达到formal；本组质量直接按保存评分展示为在线 RSI 12/12、不学习11/12。

`DataAnalysis` 首屏只投影测试组名称、状态和两臂质量结论，不再重复实验ID、runtime、资产、协议、价格快照与质量状态卡；冻结子簇明细默认折叠。若同一筛选范围内在线 RSI 全部通过且两臂usage完整，可显示该固定任务组的累计token、请求和串行时长变化；只有后端正式允许的同质量范围才使用正式“节省”口径，其他范围标为“本组减少”并注明不可跨场景外推。`CurrentEvidence` 使用相同规则，同时保留Release Manifest、具体run、报告、G/M diff和失败审计。

## 2026-09-15 双轨工作区与可续跑 campaign

2026-09-15 早期工作台曾创建 `plan_react` 与 `graph_rsi` 两个真实run；该协议只作为历史comparison兼容读取。随后该两臂消融又被本文顶部的三臂实测替代；旧记录继续按 `run=2/model=2/read=1` 和双Key协议只读恢复。`GET /api/workspaces/comparison-runs/{comparisonId}` 返回design、知识库身份、provider profile、学习/写入开关、timeline、metrics、evaluation、submission和报告链接；不返回凭据。`WorkspaceWorkbench` 只轮询该DTO，不计算虚构进度。

工作台最后一个workspace和未结束comparison仍通过本地引用静默恢复。可见的旧工作区选择器与追问区已移除；资料预览使用默认关闭的原生 `details`。清空历史记录写入workspace级时间cutoff并删除该workspace的comparison恢复引用，只改变浏览器列表视图，不调用删除API，也不改写任何run、报告、轨迹或实验artifact。

27B真实冒烟 `c762fcdc-e08e-422b-80b0-5ea6968968e6` 验证两次首次模型请求在14ms内开始，调度峰值为2个run和2个模型请求；两臂均通过且usage完整。它是产品执行链验收，在线臂在冷启动后创建G0/M0，但没有后续任务使用，因此不进入正式RSI收益或进化结论。

跨场景正式线在创建时通过 `campaign_plan()` 冻结12、12、24三个阶段和全部48项顺序。`continue_campaign(id, 48)` 只允许在runtime、冻结清单和输入/题面/评分hash一致时恢复同一目录的在线经验并追加剩余任务。campaign `4cfbc988-fab0-4537-b7e2-e509c5cfd76a` 已因基础设施/usage缺口停在stage1的10对；后两阶段未执行，不能补齐或拼接。

## 2026-09-15 跨场景归因运行线

`backend/cross_domain_attribution_assets.py` 从 `trajectory-review-v3-r3` 逐字节复制48个train题面与附件，按三场景/六子簇形成 `cross-domain-rsi-attribution-v1-48`。公开交付契约声明指标语义、字段值口径、业务ID与证据ID边界，以及顶层业务清单由原因组去重合并；这些信息进入系统上下文，不改变用户题面，也不暴露私有评分。

`backend/workspace_compute.py` 的 `granular-compute-v1` 提供 run-local 收据原语：字段映射、映射筛选、键集合限制、业务键清单、按键计数、聚合/对齐/比较、日期时差与异常日期。历史图只保存真实成功工具及 `$output` 依赖，当前数据、字段和值重新绑定。`backend/attribution_experiment.py` 提供 cross-domain smoke/probe/formal；formal 必须由同runtime完整通过的12对probe解锁。

归因运行线分别计算 `qualityGate` 与 `expansionGate`。`qualityGate` 要求两臂同质量全通过，用于同质量成本主张；`expansionGate` 要求12对协议完整、两臂usage完整、在线RSI全通过且真实图执行率至少50%，允许不学习臂的普通业务失败保留为可靠性差异。cross-domain probe遇到普通业务失败继续固定顺序，只有usage丢失、runtime变化或维护故障停止。Release Manifest在新实验完成门槛前仍绑定金融12项candidate。结果边界见 [三场景预检](history/cross-domain-attribution-probe-results-2026-09-15.md)。

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
[工具与复用设计](history/granular-autotool-design-2026-09-14.md)。下面关于 V3-r3 和更早 runtime 的条目为历史架构快照。


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
token/latency/大模型调用节省率。累计任务通过率定义为当前范围中结构化校验通过任务数除以已评测
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

当前图节点沿用 Python dict：`tool/arguments/dependencies/foreach/paginate`，可加 `reuse` 和 `defer`。`foreach.filter` 是由 Plan `selection.kind=match` 绑定到已声明列表字段的精确相等筛选：图先读取当前列表、复用筛选字段，只对入选记录调用详情。无法可靠绑定的 Plan 使用 `selection.kind=model`，该详情子图交给模型；当前字段缺失或类型变化也失败关闭并保留上游观察。`reuse.onMissing=detail` 逐条检查并补查缺失字段。没有独立 IR 框架；准确协议见 [graph-ir.md](reference/graph-ir.md)。

编译器记录 `retrievalMs`、`selectionMs`、`compileMs` 和运行时 `bindingMs`；绑定只能来自当前列表/上游输出/字面分页参数。它还会裁剪任务语义无关的独立 detail 步骤、合并等价读取节点。父图不原地改变：发现旧图不兼容时标记 `needs-repair`，仅通过的新正常 train 轨迹才能保存修订图。`filteredOutDetailReads` 和 `elidedToolCalls` 是图内原因计数，不等同于对 ReAct 的净收益。

当前 Patch 有保存来源图、带恢复的字段复用、已获模型有效恢复的失败子图交接、后续正常任务重新规划。未知失败不能凭空生成新图，结构相同不能虚增版本。`probation/family-supported/needs-repair` 表示适用证据与修订状态；不是全场景推广或统计显著性证明。

Graph RSI 的规划路由是 Fast（同任务模板/工具契约/执行器的完整图，Plan 请求为零）、Composition（Fast 未命中而有 support>=2 的 Persistent TinyEdge 时，composition 角色只生成粗子目标，本地确定性选择/组合）和 Fallback（覆盖、来源或契约校验不足时生成完整 Plan）。TinyEdge identity 共享 tool、输入输出契约和绑定槽，连续读取链以 `defer`、扇入/扇出与非连续依赖为边界；执行器消费已选 ID 而不再调用模型重选。当前候选检索是本地字元重叠而非论文 embedding，详细差异与实证边界见 [g-agent-local-composition-design-2026-09-10.md](history/g-agent-local-composition-design-2026-09-10.md)。

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

仓库文档入口见 [`docs/README.md`](README.md)：当前执行与交付文档保留在 `docs/` 顶层，机制说明位于 `docs/reference/`，带日期的阶段性协议、验证和失败诊断位于 `docs/history/`。Benchmark 顶层只保留当前资产与候选，旧冻结版本位于 `benchmarks/history/`；release 深链使用归档后的明确路径，不按文件时间猜测当前版本。

前端 `5173` 默认 `#home`，数据分析为 `#analysis`（旧 `#evidence` 兼容跳转）；旧 `#experiments`、`#compare`、`#insights` 和 `#replay?task=<id>` 统一重定向到历史区域。

`#analysis` 使用一套跨标签共享的保存结果回放状态，并按“业务结果 / 记忆进化 / 成本曲线 / 请求与可靠性”分开展示。首屏只保留测试组状态、两臂质量、token/请求效率和 G/M 修订后使用；保存结果控制在桌面端位于右侧，成本页三张累计曲线并列。“报告与轨迹”暂时退出演示标签，前端也不再为选中任务额外请求报告详情；原始报告、结构化清单和轨迹 artifact 继续保留在后端与历史审计入口。记忆进化页仅显示任务编号和“首次复用 / 结构修订 / 新版本使用”等核心状态，再以一行汇总真实图执行、G/M 修订及后续使用。进化与成本标签首次进入显示 0 项空态，只有播放或显式选择最终结果后才投影保存数据。冻结子簇、逐任务账本、发布后维护诊断、数据限制长列表和模型请求内部分类退出主展示。单场景筛选自动隐藏，任务类型筛选仅在有多个类型时显示；窄屏标签栏局部滚动，页面本身不产生横向溢出。所有内容仍由当前选中的同一分析清单项提供；学习归因数据若任一臂不是 `graph_rsi`，分析 API 直接拒绝该测试组，不改变 Release Manifest 或历史工件。默认主页是一个可交互的企业运营数字员工工作台：切换财务、客服、技术工单能力后，用户拖拽/选择 CSV/XLSX/JSON/TXT，并手写业务请求；资料预览、确定性澄清、费用确认、真实 Agent、同一 run 的 DAG、模型/结构化/工具事件、HTML 报告、导出和同工作区追问都由保存 run ID 关联。每个工作区使用可读目录名（如 `finance-取消订单复核-a1b2c3d4`），完整 UUID 只作为内部 API、证据和运行关联身份。用户输入保持可读布局：`inputs/` 是原始附件，`requests/` 是已提交问题文本，`.rsi/` 仅保存解析表、任务状态和内部草稿；普通用户运行使用独立目录且 `learning_enabled=False`，不会污染实验经验。旧根目录 JSON/`sources/` 与 UUID 目录工作区仍可恢复，但不在恢复时迁移或改写。`#home` 不展示 Workpack、预置题目或历史 pair；`#analysis` 只读取分析清单固定的一个保存实验，历史 `#experiments` 在 archive 中保留完整控制台。`#compare`、`#insights` 和 `#replay` 保留历史 V4 的只读展示。公开资料经本地受限只读工具访问，不能称为生产企业写入部署；后端为 `4317`，模型配置只在根 `.env`。

运行与恢复命令、配置字段、持久化位置见 [.codex/state.md](../.codex/state.md)。实验结论见 [EXPERIMENT_STATUS.md](EXPERIMENT_STATUS.md)，不要从截图或旧 README 推断当前性能。

`scripts/run_online_e2e.py` 是独立的 36-task 在线训练对照入口。它创建专用 run/experience 目录，基线禁用学习，RSI 仅从此前正常 train 任务更新经验；每次启动后立即 checkpoint run ID，避免恢复时重复学习。`--rsi-source` 只复用已审计的 RSI-only source，并在新目录补跑匹配 Baseline；结果明确标注为分时匹配。静态页由 `/api/online-e2e/{id}/report` 提供，并按 family 给出六条经验形成/复用与准确 trace/report 入口。

完成的严格串行工件 `online-rsi-serial-final-v4` 额外从原始 run 聚合 P95/最大延迟、最大 token、报告恢复、维护、分页和 phase token。它只生成派生摘要，不会重放 Agent/Judge；Agent 成本与 Judge 的已记录 token 下限分开显示。最终证据边界见 [online-rsi-serial-final-results-2026-09-11.md](history/online-rsi-serial-final-results-2026-09-11.md)。

展示层的严格报告审计不会改变上述原始结构化 evaluation：它再次核查报告 schema、metric/selection/evidence 精确性、证据在当前 trace 中确已观察，并以有限规则检查摘要中的已知 ID、数字和 `cents` 金额表述。gold 仅在后端进程内用于得到布尔结果；不返回预期答案或未通过的具体业务真值。

## 正式运行前任务审阅

`ReleaseEvidence` 对 `trajectory-plan` 发布返回 `taskReview`：六个业务契约、输入表字段、
8个train题面变体、预检位置和公开来源。题面由 `request_for()` 生成后与冻结资产中的
`requestHash` 逐项核对；数量、版本或题面不一致均失败关闭。`CurrentEvidence` 在 archive 的候选审阅入口中
展示该审阅清单，并把质量、成本与回放明确显示为“尚未运行”，不显示0/0 usage卡或空方法回放。
该读取路径不创建实验、不加载私有答案、不调用模型。内容审计见
[正式运行前任务审阅](history/trajectory-v3-run-approval-review-2026-09-14.md)，两臂实际工具面与报告
Schema见[任务与工具契约审阅](history/trajectory-v3-task-and-tool-review-2026-09-14.md)。


### V3-r2 历史失败预检与 V3-r3 候选投影

`ReleaseEvidence` 对 candidate 的已保存 trajectory experiment 执行 runtime、资产、协议和 pair/run 身份校验。未运行的 V3-r3 只显示冻结任务审阅，不显示指标或曲线；若预检 `quality_stopped`，对应历史 release 只保留同一运行的失败报告、输入、轨迹和绝对开销。节省率/累计收益曲线关闭，直到完整质量门槛通过。

### 数据分析成本投影（2026-09-14）

`AnalysisDatasets` 在读取固定实验 artifact 时同时读取 `releases/analysis-manifest.json` 中的版本化 `modelPricing` 快照。`/api/analysis/datasets/{id}` 返回每个 run 的输入/输出 token、实际角色模型、USD 估算成本和独立累计曲线。角色模型一致时按 run 总 token 计费；角色不同只在 `phaseMetrics` 与总 usage 完全闭合时按 plan/match→planner、composition/compile→composition、execute/graph→executor 计费。任何缺口返回 `null`，前端保留曲线缺口，绝不以 0 或默认模型补写。
