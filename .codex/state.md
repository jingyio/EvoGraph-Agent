## 2026-09-15 财务与技术工单双场景候选（最新）

- 用户决定最终演示只覆盖财务和技术工单；客服旧失败继续保留在三场景历史实验，不从账本删除，也不进入新的两场景指标。
- 新协议冻结四对预检 `F01,F02,T01,T02`；通过后正式运行 `F01–F12 + T01–T12`，技术工单达到12项。两臂仍为同一图执行Agent，区别仅为跨任务学习。
- 主Key与Secondary Key按pair并行，固定27B/thinking关闭；全局 `run=2/model=2/read=1`，单臂内部1/1/1。协议回归、全量Python255项、前端35项和构建已通过；真实预检尚未启动。
- 协议见 `docs/finance-tickets-attribution-protocol-2026-09-15.md`。新实验完成前，当前Release Manifest不切换。

## 2026-09-15 三场景相对质量门槛（最新）

- 用户将扩大门槛调整为“在线 RSI 不比图执行·不学习臂差太多”：冻结12对中在线 RSI 最多少通过1项；两臂usage仍须完整、维护无错误、真实图执行率仍须至少50%。
- `qualityGate` 继续要求两臂12/12，只用于严格同质量成本主张；相对质量门槛只决定是否继续stage2，不删除失败、不改变评分，也不把质量不同的绝对开销写成同质量收益。
- 旧campaign `4cfbc988-fab0-4537-b7e2-e509c5cfd76a` 已完成12对并按旧冻结规则停止；runtime修复后启动的短probe `70f36468-cd5c-4b8a-ab89-131660017446` 和formal `4617dd8c-1989-438d-8ec5-959bf7b768ca` 均在新规则冻结前主动终止，工件与取消开销完整保留。下一正式campaign从空经验按新规则运行，前12对通过后同一experiment自动追加至24对。

## 2026-09-15 宽屏双轨对比与自动执行浮窗

- 数字员工的双轨对比从三列工作区中移到整页宽度区域；页面最大宽度扩大到1720px，资料和历史侧栏缩窄，长题面在对比卡上方完整显示一次。传统与在线RSI两张卡在920px以上保持并排，减少无效留白和纵向换行。
- 长事件流水默认折叠为“完整执行记录”。真实运行期间，传统 Agent 与在线 RSI 各自在右上角显示苹果通知式阶段卡：新保存事件到达时淡入，停留约3.1秒后淡出，可同时堆叠也可手动关闭。通知展示当前表、记录数、业务阈值、token、图节点和G版本等真实实例值；历史完成run首次恢复时保持静默，不生成模拟事件。

## 2026-09-15 分页式演示回放

- 数据分析页将同一保存结果回放拆为五个逻辑标签：业务结果、记忆进化、成本曲线、请求与可靠性、报告与轨迹。回放状态位于标签上方并跨标签共享，切换标签不会重置任务前缀或发起模型调用。
- 默认业务结果页只显示核心 KPI 和当前播放任务；记忆进化页集中显示任务机会链、首次跨任务记忆生效、G/M 修订及后续使用；成本、模型请求/可靠性和完整报告审计分别隔离。标签栏保持粘性，390px 下只在自身区域横向滚动，不造成页面横向溢出。

## 2026-09-15 保存结果回放与首次跨任务记忆生效

- 数据分析页新增只读“保存结果回放”：播放、暂停、重播、三档速度和最终结果。回放按真实任务顺序逐项投影 KPI、累计曲线、请求分解、可靠性、任务详情、G/M 修订及后续使用，只消费已有 artifact，不重新调用模型。
- 任务1只显示成功轨迹结束后保存 G0/M0，是记忆来源，不做蓝色重点且不计入修订。任务2首次选择并复用任务1产生的 G0/M0 时显示蓝色“记忆已构建 · 首次复用”；橙/紫仍表示有来源和实质 diff 的 G/M 修订，绿色仍表示修订后的实际使用。
- 本轮没有运行付费模型、没有改写旧实验结果。浏览器已验证第1项到第2项的逐步投影、任务2高亮和390px无横向溢出。

## 2026-09-15 当前金融证据展示口径（最新）

- 当前 Release/Analysis Manifest 继续绑定金融12任务实验 `d02f0ecd-8bb5-4359-94be-e7f7233df6a5`，状态保持 `candidate`；未改写任何实验工件，也没有新增付费模型运行。
- 本组在线 RSI 12/12，通过率高于不学习图 Agent 的11/12；因此前端不再称其“质量受限”或“质量门槛未通过”。`candidate` 只表示当前仅覆盖12个财务任务，且缺少独立 Judge 与人工全文审核。
- 数据分析首屏只保留测试组名称、候选状态和12/12对11/12的核心结论；实验ID、runtime、资产、协议、价格快照及重复状态卡退出首屏。固定任务组的真实token、模型请求和串行时长变化曲线恢复展示，并明确不外推为跨场景普遍收益。
- FX11不学习臂失败、全部开销、G/M修订与后续使用链继续完整保留；两臂通过率不同，所以不把该观察写成严格同质量消融结论，也不将candidate改为formal。

## 2026-09-15 双轨工作台与分阶段 campaign（最新）

- 数字员工页一次启动同题同附件的两个真实 run：传统 `plan_react` 使用主 Key、在线 `graph_rsi` 使用 `LLM_API_KEY_SECONDARY`。工作区调度上限为 `run=2/model=2/read=1`，两臂规划、执行与报告均固定 `qwen/qwen3.5-27b`、thinking关闭；前端每800ms轮询后端保存事件，不生成模拟进度。
- 真实27B双Key冒烟 comparison `c762fcdc-e08e-422b-80b0-5ea6968968e6` 已通过：两个run创建相差6ms，首次模型请求相差14ms，调度峰值 `runs=2/models=2/reads=1`。传统臂 `d9e4deba` 与在线臂 `5fed857f` 均通过结构化事实/证据评分且usage完整；token 34,410→32,386，请求4→3，时长72.960→66.250秒。该单对只验证产品双轨链、真实并行和冷启动G0/M0创建，不是正式学习收益或后续复用证据。
- 工作台已删除可见的“继续之前的工作”和“继续追问”区域；最后工作区仍静默恢复。资料预览整体默认收起。工作记录提供“清空历史记录”，通过workspace级本地cutoff隐藏旧run并清除恢复引用，不删除后端run、报告、轨迹或实验artifact；刷新后旧记录仍保持隐藏，新run继续显示。
- 长题面输入框按内容自动增高，桌面双栏、窄屏上下堆叠。数据分析页按筛选范围隔离曲线、G/M修订与后续使用，并高亮有来源和实质diff的真实G/M修订。
- 跨场景 campaign `4cfbc988-fab0-4537-b7e2-e509c5cfd76a` 已在stage1第10对后因基础设施/usage缺口停止：完成10对，不学习与在线RSI各8/10，双方usage均不完整；stage2和stage3未启动。C11、T01、T05等失败与开销完整保留，不能剔除或续写成24/48对结果。
- 源任务资产仍为48 train、6 validation、6 test；campaign只学习train，test题面与经验写入保持隔离。

## 2026-09-15 三场景扩展门槛调整（最新）

- 已冻结 `cross-domain-rsi-attribution-v1-48`：财务、客服、技术工单各16项，六个子簇各8项；题面/附件逐字节复用V3-r3，公开字段口径放系统交付契约，不改题面。
- 旧 probe `3fe6c157-0a32-4268-b9bf-3c38e88b6381` 完成前7对：不学习6/7、在线RSI 7/7，usage完整，实际图执行5/7。绝对token 1,091,875→647,952、请求82→44、工具错误32→8；C10不学习臂达到24请求上限。全部失败与开销保留。
- 用户确认在线RSI准确率高于不学习臂可作为可靠性结果继续展示。协议现分离 `qualityGate` 与 `expansionGate`：前者仍要求两臂同质量全通过；后者允许不学习臂的普通业务失败留在分母，只要求完整12对、两臂usage完整、在线RSI 12/12且真实图执行率≥50%。
- 新runtime先运行完整12对probe；普通业务失败不提前停止，只有usage缺失、runtime变化或维护故障才停止。满足 `expansionGate` 后才启动48对formal。质量不等时只展示准确率与绝对成本差，不主张同质量节省率。
- 当前Release/Analysis Manifest继续指向金融12项candidate `d02f0ecd-8bb5-4359-94be-e7f7233df6a5`；跨场景新结果完成门槛前不替换当前发布。详情见 `docs/cross-domain-attribution-probe-results-2026-09-15.md`。

# 项目状态快照

## 2026-09-14 十二任务候选分层展示（最新提交在途）

- 全量 `d02f0ecd-8bb5-4359-94be-e7f7233df6a5` 继续作为首要candidate，FX11失败与全部开销不删除；没有新的付费模型运行。
- 同一实验按运行前冻结资产分为FX01–FX08订单财务复核与FX09–FX12支付结构健康。订单子簇两臂8/8，token 1,025,754→366,230、请求84→30、串行时间649.760→383.985秒、工具错误19→1；支付子簇3/4→4/4，承担可靠性和两条修订使用链。
- 分析API返回 `summary.cohorts`，前端显示两个可点击子簇卡片并用同一任务集合重算曲线。全量仍关闭正式收益；只有后端确认两臂全通过且usage完整的冻结子簇显示同质量分层效率。事后11项敏感性分析不进入主卡片。

## 2026-09-14 十二任务修复后扩大实验（最新候选）

- 同 runtime 双任务预检 `092bb7b9-52a1-4c82-92c9-ab25701078ee` 两臂2/2通过、usage完整、实际图执行1/2，满足50%启动门槛；随后运行正式阶段 `d02f0ecd-8bb5-4359-94be-e7f7233df6a5`，资产 `finance-rsi-attribution-v5-12`，runtime `sha256:11e6f73013a0ad50c4023b637214660087c001cff55a676c354e7aba299d68f4`，27B统一规划/执行/组合、thinking关闭、严格串行1/1/1。
- 在线RSI 12/12通过；不学习图Agent 11/12，FX11达到24请求上限且未提交报告。usage全部完整，非基础设施故障。质量门槛失败，发布保持candidate，旧六任务formal不替换。
- 全量绝对计量：token 2,119,742→936,718，请求165→58，工具250→216，工具错误46→8，串行时长1081.771→742.943秒。原始token差55.81%、时长差31.32%，因两臂质量不等不得作为formal收益。
- 实际图执行11/12。FX01创建13节点G0/M0；FX09产生15节点G1/M1，FX10实际使用；FX11通过有界补全产生23节点G2/M2，FX12实际执行全部节点，以2请求、24工具、0错误通过。三个版本均无错误 `*_count` 数值聚合别名；G2仍有重复筛选，是可用但非最小模板。
- FX11不学习臂反复选择错误计数聚合并发生收据类型不匹配；在线RSI使用历史频次统计路径后通过。这是跨任务经验的真实可靠性差异，不通过提高上限或改评分抹掉。未继续48任务或跨场景扩展。
- 结果说明见 `docs/finance-attribution-v5-12-results-2026-09-14.md`。前端作为质量受限candidate只展示绝对量、失败、修订链和真实轨迹，不与历史formal拼接。
- 本轮全量Python 232项、前端18项、TypeScript/Vite构建、Release/API和报告下载验证通过；最终浏览器视觉复核因Mac锁屏无法执行，未伪报通过。

## 2026-09-14 三任务修订后使用探针（上一候选，已保留）

- 当时发布与默认数据分析切换为 candidate `finance-attribution-v5-repair-probe`，精确绑定真实 API 实验 `16bbb302-a0eb-49ed-9613-47849aa597be`、资产 `finance-rsi-attribution-v5-12`、协议 `finance-graph-rsi-error-recovery-probe-v1` 和 runtime `sha256:66f943479bc4b693e1b412e7af7d919f1609ebf21210eb1954c9a039a41d0cce`。协议明确 `excluded from formal metrics`，因此不替换六任务 formal 的历史身份。
- 固定顺序 `FX01 → FX09 → FX10`，同一图执行 Agent 两臂各3/3通过，六次 usage 完整。绝对总量：不学习臂609,447 token、47请求、67工具调用、12工具错误、369.756秒；在线RSI 324,130 token、23请求、60工具调用、3工具错误、184.904秒。
- FX01 在线冷启动较贵（103,558→151,265 token）；FX09实际执行G0的13个节点，成功后产生覆盖扩展G1/M1；FX10实际执行G1/M1的18个节点并通过且无工具错误。实际图执行2/3，达到50%探针门槛。运行后语义审计发现G1的 `payment_count` 节点错误地对 `amount_cents` 求和；最终正确计数来自其他当前观察与模型判断，因此它是“已执行的候选修订”，不是完全正确的可直接复用模板。
- G0→G1新增支付记录计数、订单状态不同值统计和 `purchased_month` 不同值统计，移除重复 `order_id` 不同值统计；节点16→18。它是正常成功后的覆盖扩展，不是错误纠正。
- 请求减少主要来自读取选择11→1、计算选择28→16；报告组合保持3→3。图复用减少的是重复工具选择和参数绑定决策，不声称跳过当前报告生成或按节点数换算收益。
- 失败探针 `9ee28f75-59ba-42c2-8c56-739d4ad464c8`（runtime冻结失败）与 `4aaf803b-d236-45d0-8d2c-827352ae47c9`（FX09报告恢复屏蔽计算工具）完整保留，不进入当前指标。后者已定位为实现缺陷并修复。
- 最终验证：230项Python测试、17项前端测试、TypeScript/Vite构建和 `git diff --check` 通过；浏览器核验 `#home` 上传/输入入口、`#analysis` 单一候选上下文与请求分解、FX09 diff、FX10报告/清单/轨迹、`#archive` 52个历史上下文，以及窄屏无横向溢出。未推广客服/技术工单，未做独立Judge或人工全文复核，不能主张普遍或长期收益。


## 2026-09-14 上一轮十二任务扩大失败验证（历史）

- 已完成同 runtime 双任务 probe `fd0bbc4c-9297-43fb-ac81-1cec05f4b991`，两臂2/2通过，在线臂实际图执行1/2（50%）；随后按冻结顺序完成 formal `7b3e9244-1a2c-4a85-bad6-18d0cee3bf09`，资产 `finance-rsi-attribution-v5-12`，24次真实Agent usage全部完整。
- 结果为两臂各8/12通过。FX01创建G0，FX02–FX08连续实际复用并通过；在线臂总体实际图执行11/12，但FX09–FX12支付结构健康任务两臂均失败，主要表现为期间去重计数错误：期望9，提交为0或12，并伴随报告恢复终止。
- 全链绝对计量：不学习臂1,467,397 token、124请求、1,140.885秒、44工具错误；在线RSI 1,401,822 token、88请求、925.425秒、21工具错误。原始差为token 4.47%、串行时长18.89%，因质量门槛失败不得作为收益结论。
- 没有产生实质G/M修订，也没有修订后使用。本轮只证明订单复核子簇的经验复用；支付健康扩展未完成，11/12命中不等于11/12成功。FX11/FX12在线恢复分别达到24/20次请求，全部失败与开销保留。
- 前端数据分析新增历史测试组 `finance-attribution-v5-12-expanded`，支持12任务时间线、绝对token/请求/latency/成功率、同run报告与轨迹。质量不通过时隐藏收益曲线；当前发布和默认分析仍是六任务formal `finance-attribution-v4-6`。
- 下一步先补通用时间分桶/期间计数能力及交付映射，做无模型回归和同runtime小规模probe；未通过前不再次运行12×2，也不推广客服/技术工单。
- 本轮验证：222项Python测试、16项前端测试、TypeScript/Vite构建、API/Release深链和`git diff --check`通过；浏览器实测默认formal与十二任务历史组切换、12点时间线、中文机会标签、失败门控、4/6与11/12实际图执行显示，以及390px无横向溢出。


## 2026-09-14 六任务学习归因正式发布

- 当时发布/默认分析同为 `finance-attribution-v4-6`，精确绑定实验 `33999392-729d-4af2-8d5b-52fe7b18fcc4`、资产 `finance-rsi-attribution-v4`、协议 `finance-graph-rsi-learning-attribution-v4` 和 runtime `sha256:0a97c2949a483492485bd414a7d7b7cebeeef306e625af6dc4990bcbea015207`。状态 formal；不复用旧V17/V4指标。旧V3-r3候选与V1停止实验转历史审计，原工件不改写。
- 同一图执行Agent，不学习与在线RSI各6/6结构化事实/证据通过，usage完整。token 944,492→549,900（节省41.7782%），模型请求72→42，串行耗时651.867→548.372秒（节省15.8767%）；工具错误21→12均保留，正文没有独立Judge/全面人工质量评分。
- 4/6任务实际部分历史子图复用；FA06匹配错误拒绝可变槽并缺依赖闭包，安全回退后通过，13请求/183,752token/170.786秒全部计入。此处不冒充完整Fast命中或满足旧48任务Fast发布门槛。
- 发布后已在隔离目录保留两次FA06真实API诊断。首个 `d047dea8-8dfe-4fd7-8e3c-ecfd4806a72f` 因 `learning_enabled=False` 无法读取 probation 经验，退化冷启动：14请求、216,002 token、104.149秒；这是诊断配置失败。修复匹配输入与依赖闭包后，`d7dd21a0-570c-4a59-9f15-bf5d51566b2d` 使用正式FA06之前的经验状态，实际命中G2/M2候选并以当前10期阈值重绑定，15个图节点完成；结构化评测通过、3请求、40,158 token、62.880秒、17工具调用/0错误。它验证维护器修复，不进入原formal指标，也不单独证明普遍收益。
- 前端数据分析已增加发布后维护验证区，严格从两份诊断清单和摘要校验读取，并与正式KPI/曲线隔离。新的扩展资产 `finance-rsi-attribution-v5-12` 已冻结12个财务train实例：8个订单对账后接4个支付结构健康任务；双任务probe通过后才允许12任务formal，实际历史图执行率门槛为50%，仅加载版本不计命中。当前尚未启动该扩展实验。
- FA03正常反馈产生状态覆盖扩展G1/M1，FA04实际执行新增筛选节点。原始G2/M2为图重编号/顺序变化，展示审计排除其进化主张，原工件保留。M1是覆盖描述扩展，不证明独立匹配纠错算法。
- 新计算接口、run内收据与来源依赖已实现；不添加完整AutoTool/TIG。正式运行源码快照保持不变；后续维护器已补充与节点ID/顺序无关的结构比较及协议回归，并完成上述隔离真实API诊断；正式发布仍指向冻结运行的原runtime。
- 交付文档 `docs/teacher-rsi-attribution-delivery.md`，三分钟脚本 `docs/teacher-rsi-attribution-recording.md`。前端支持六任务点击、同release问题/附件/两臂成果、真实调用回放与报告下载，曲线只读取本实验。
- 最终验证：217项Python测试、14项前端测试、TypeScript/Vite构建和`git diff --check`通过。浏览器检查`#home`上传/解析/费用闸门、`#analysis`六任务与FA03 diff/FA04回放和下载、`#archive` 47个上下文的版本/状态/runtime/资产/协议；`#home`与`#analysis`在390px均无横向溢出。
- 剩余：48任务、其他两场景推广、独立Judge、长期可靠性及匹配器稳定性；不得由本次六实例主张普遍收益。共享.env仍9B，真实实验进程统一27B/thinking关闭。


## 2026-09-14 reconciliation clause IR（已实现，未运行付费模型）

- 对冻结 V2 smoke `c0a387c3-5272-4a24-8743-9bd6ed821c13` 的 RSI run
  `5879a866-a4e0-423c-bc04-357c0f2dfe88` 做了只读审计：结构化报告通过，但 13 次模型请求、
  175,453 输入 token、94.321 秒；1 次 plan、11 次执行工具决策、1 次报告。两个工具错误分别是
  `comparisons` 被传成字符串，以及 `group_count` 缺少 `groupBy`。旧工件未改写。
- `workspace_reconcile_keyed_sums` 的成功收据现按 aggregate、derivedTotal、每个 comparison 和
  missingByAlias obligation 编译为可独立选择的逻辑片段；依赖闭包验证后，同一 bundle 合并为一次
  物理 reconciliation 调用。单个不可绑定 comparison 不再丢弃其余对账主体。
- `0.05 BRL`→5分保存为可审计精确缩放槽；V2 的 `missing_payment/missing_items equals 0`
  伪比较不进入经验，真实缺失语义来自已成功工具返回的 `missingByAlias`。别名、core、Schema 或依赖
  不一致均失败关闭；旧普通 trajectory node 仍兼容。
- 无模型验证：相关 65 项通过，全量 Python 208 项通过，TypeScript/Vite build 与
  `git diff --check` 通过。尚未产生新的真实 RSI 命中或成本收益，需新 runtime smoke 才能判断。

## 2026-09-14 数据分析新增调用次数与准确率（已完成）

- V17/V4 及后续同格式测试组新增累计大模型调用曲线和累计任务准确率曲线；顶部 KPI 显示两臂真实 `modelRequests`、调用节省率与结构化通过率。
- 准确率仅定义为结构化校验通过数/已评测任务数，失败保留在分母；未知调用或未评分结果保持空缺，不按0补齐，也不等同 Judge/人工文字质量。

## 2026-09-14 数据分析加入历史 V4 36-task（已完成）

- `releases/analysis-manifest.json` 新增 `taskbank-v4-36`，精确绑定 `online-rsi-serial-final-v4`、runtime `1c32ff2...`、任务 hash 和工件 SHA-256；默认仍是 V17 48-task。
- `AnalysisDatasets` 统一读取 workpack 与 online-e2e 两类固定来源并失败关闭。V4 显示 36/36 对通过、539,468→347,368 token（-35.6092%）、1,386,926→806,186.644ms（-41.8724%）、203→114 次 LLM、24/36 Fast。
- V4 标为 historical；切换测试组会整体替换任务、曲线、轨迹和报告。V4 只有6个G0且没有G1/G2或M修订，不主张递归结构进化。本次不运行模型，不改写历史工件。

## 2026-09-14 当前前端：可切换数据分析（已完成）

- 主导航第二入口改为 `#analysis` 数据分析；旧 `#evidence` 兼容跳转。V3-r3 任务与工具审阅保留在 `#archive?page=candidate`。
- 新 `releases/analysis-manifest.json` 首项精确绑定 V17 48-task 保存工件 `005ffeb9-964e-42ac-86e9-fb9e8f2212fe`，并冻结 runtime/artifact digest、任务资产、协议、48对与质量状态。
- 只读 API 返回逐任务 token、`durationMs`、请求/工具、成功状态、G0/Fast 和报告深链；场景/工作流筛选后重新累计。V17 token 节省44.5839%，保存串行时长节省26.9232%；无G1/G2，不主张递归结构进化。
- 本次只使用保存工件，不运行模型，不改写 V17 或 P0.5 候选实验。前端8/8、Python 193/193、构建和diff检查通过；浏览器核验默认页、数据分析、筛选、报告、候选审阅与390px宽度。

## 2026-09-14 当前接力：V3-r3 候选修复（未运行）

- 当前模型配置为 `qwen/qwen3.5-9b`（执行、规划、组合），thinking 关闭；`AGENT_MAX_STEPS=24`。
- V3-r2 的真实 API F01 预检 `94620ba7-efd1-4fb9-b323-2bde8b22f78d` 已按质量门槛停止并转为 historical：Baseline 24 次模型请求、31 工具调用、609,579 token、144.346 秒，`metrics` 失败；RSI 13 次、20 调用/3错误、185,288 token、111.181 秒，`metrics/selectedIds/groups` 失败。RSI Fast 0/1。所有失败、费用和 trace 保留；69.60% token 差只能诊断。
- 当前 Release Manifest 指向未运行的 `trajectory-p05-v3-r3-candidate` / `trajectory-review-v3-r3`。它保持同一 48 train、6 validation、6 test、公开记录与私有评分边界；财务题面仅增加一句订单主体、一对多、分/BRL业务口径。机器交付字段不进题面、模型初始消息或轨迹匹配。
- 已修复：通用 prompt 的字段类型/单位/缺失原则；对账工具的文本键、数值字段、comparisons 数组与原始单位说明；模型上下文仅对字节完全相同的重复行观察压缩，ledger/trace完整保留。相关 Python 回归 40/40 通过；未再调用付费模型。
- 下一步：向用户展示 V3-r3 的简短财务题面及工具契约供最终复核。明确启动后，才以新的空 RSI 经验库运行 12 对严格串行预检；质量、usage、维护和实际 Fast `>=50%` 全部通过后才可 48 对 full。



- 下方关于 V2/V3-r1 的审阅、9 对预检和旧 current release 的文字是当时的历史快照；当前
  执行基线以本文件顶部 V3-r3 条目、Release Manifest 与 `docs/trajectory-v3-run-approval-review-2026-09-14.md` 为准。


- 2026-09-14 执行阶段已推进P0.5，**未完成整体验收**。工作区现在从通过评分的真实
  toolTrace收据诱导读取/compute片段，绑定当前嵌套表/语义槽；不再按family/template选图。
  多原因groups、缺失null排除比较、sum/max/min、BRL报告、artifact运行内幂等已实现。
  当前M支持从正常成功相同结构的新schema扩展适用约束，非train工作区不回写。
- V1预检 `0795dece-988a-42f0-910a-45480aa50a3b` 首对Baseline组内证据缩写失败，
  RSI通过但token负收益；保留。共享唯一当前证据绑定修复后，V2
  `96c69be0-fc62-494a-b05d-2267d0925c03` 财务三对均通过，随后客服首对Baseline把
  rowId当complaint_id，两次报告仍失败，按协议停止。V2两臂3/4 vs4/4；
  token270092→124617仅诊断，禁止主张全量同质量收益。财务子集165949→95996
  （-42.1533%），也不代表全文质量等价。两版本总开销614150token/54模型请求。
- 财务已有实际G0→G1/覆盖M1，但G1/M1后续使用均0，进化验收未达标。嵌套上游output
  依赖推导、报告/草稿/导出图调度、第二代表工作流组仍待做；不把模型边界写成完整编译。
  预检未过，未启动技术工单付费预检或full。财务G1、客服G0经执行代理协议审核后注册
  产品只读经验，不算后续使用或独立质量审核。首页learning=false。
- 新 `/#trajectory` 展示同run报告/下载、当前绑定、G/M差异、全部失败和曲线。
  `test/轨迹复核-v1` 提供三场景新公开来源JSON/问题；独立资产24train+3validation+3test，
  非建议的48train规模。三岗位浏览器首传/解析/准备请求已核验，未额外运行模型。
  修复首次上传FileList在await后被清空、中文文件名被替换、恢复后实验顺序问题。
  详细证据及剩余项：`docs/trajectory-v2-results-2026-09-14.md`。

- 2026-09-14 用户附聊天记录并进一步纠正重构目标：不增加人工SOP；可复用图从真实
  执行轨迹诱导，编译时同时提炼适用描述/参数槽，匹配逻辑由后续train反馈修订，
  不预定义业务题族或用family/template决定选择。新完整财务样例为差额>5分、分期>=8、
  缺失待核查、多原因独立保留、证据和BRL简报；不能说它已在旧V17冻结题库实际运行。
  最新规格 `docs/trajectory-rsi-refactor-handoff-2026-09-14.md`、D42-D45、TODO P0.5
  优先于上一版交接；新48train三场景×两组×八实例为建议，旧V17保留。
  本讨论session只更新文档，未改runtime、未跑模型、未重写任何实验或用户附件。

- 2026-09-14 讨论审核后确认下一阶段目标：上传工作区可继续不学习，但需用户文本到
  已审核历史图匹配；工作区图应覆盖确定性 compute 和已有本地草稿/导出/报告；下一版
  48-task train 要验证真实反馈修订和后续实例使用。完整执行规格见
  `docs/workspace-graph-evolution-handoff-2026-09-14.md`，设计 D39-D41、TODO P0.4。
  本讨论 session 仅更新交接文档，未修改 runtime、未运行模型、未更改 V17 工件。

- 2026-09-14 用户需要可手工拖入的测试输入，之前将其误解为运行后工作区布局。
  新增 `test/财务`、`test/客服`、`test/技术工单`：每类两个新编写的TXT问题和基础/扩展XLSX
  （12/16条主记录）。从公开原始缓存排除冻结记录库及已有工作区ID后，按固定哈希选取剩余
  train记录；未使用旧问题、报告或答案。来源和六份附件的上传解析/任务创建检查见
  `test/.rsi/`，0次模型调用。前端不增加题库；本次交付不是新的效果评测或学习收益证据。

更新时间：2026-09-14。功能基线 `9520ae7`；本快照所在的文档提交在其后，实际 HEAD 以 `git log -1` 为准。

- 项目：RSI 数字员工 Lab。
- 仓库：`/Users/apple/Documents/PPT/RSI吹牛PPT/rsi-agent-lab`。
- 当前分支：`feat/graph-rsi`。不要在父目录误建第二个仓库。
- 2026-09-13 Workpack V17 full 已完成：`005ffeb9-964e-42ac-86e9-fb9e8f2212fe` 的 mode
  名为 `full_train_v15`，但运行时修订线是 V17，不能与旧 V15 cancelled full 混淆。48 个
  冻结 train 工作包、两臂各48次、串行 `run=model=read=1`，两臂均48/48私有结构化事实与
  证据通过且 usage 完整。Baseline/RSI token 2,244,017→1,243,546（**-44.5839%**），模型
  请求258→149，工具422→325；RSI形成12个Workflow，后续Fast35次、Fallback13次、
  Composition0。报告恢复、工具拒绝/错误和本地开销均保留，详情见
  `docs/workspace-workpack-v17-full-results-2026-09-13.md`。旧V15 full `6c56245b` 仍是
  pair2 transport retry usage未知的取消诊断，绝不覆盖或拼接。
- 2026-09-14 工作台题库/同题回放曾作为临时展示交付实现，现已被后续产品决定替代：`#home`
  仅接受用户拖拽/选择上传的资料与手写业务请求，不展示 Workpack、预置题目或历史 A/B pair。
  新工作区在 `artifacts/workspaces/<role>-<label>-<short-id>/inputs/` 保存原始附件，在 `requests/`
  保存已提交的问题文本；`.rsi/` 保存解析表、任务状态和内部草稿。普通用户工作区始终
  `learning_enabled=False`。冻结 Workpack、严格 pair、历史轨迹和结果只在
  `#experiments` 及其按需详情接口可查看，不会因首页查看或上传启动 Agent。
  `#home` 首次加载不会创建空目录；首次附件上传或解析工作要求才落盘，并在顶部显示相对资料目录。
- 2026-09-13 交付验收完成：默认 `/#home` 通过实际三岗位工作区运行验证了资料加载、任务、
  真实 Agent、同 run 轨迹、HTML 下载和同工作区追问。财务主任务/追问为
  `dfb877a2`/`136ef9c8`，客服为 `a2886561`/`4d307152`，技术工单为
  `d16052ad`/`2807d3ae`；六个 run 均完成、usage 完整、各一次报告。客服主任务保留
  3 次工具错误/拒绝，不能写成零错误。`/#experiments` 首屏改用轻量实验 DTO：列表约
  29,869 B，V17 摘要约 290,393 B；原始图、观察、Plan 和报告仍须从单 run 接口按需读取。
  HTML 下载接口均返回 `Content-Disposition: attachment`，不会另做示例数据或伪造进度。
- 2026-09-13 Workpack V14 在途：V13 财务一对多对账已通过，但客服 Baseline 暴露
  `count + groupBy` 静默返回总行数、被误作不同分组数的问题。V14 明确拒绝该调用并要求
  `group_count`，重新从隔离 smoke 开始。V13 结果 `5dbcb2fc` 为 2/3 vs 3/3，保留诊断，
  不得主张其 token 差。V13 此前确认财务订单行按业务键对账时被错误要求唯一，
  已改为唯一键计算加完整行级证据；`model_client.py` 已对短暂传输失败增加一次有界重试，
  分别记录逻辑模型请求、实际 provider attempts、retry 与 usage 不完整。V13 是独立
  staged runtime，先运行 smoke；协议见
  `docs/workspace-workpack-v13-repair-protocol-2026-09-13.md`，不得与 V12 混接。
- 2026-09-13 Workpack V12：V11 Fast 路径的重复确定性 compute 长尾已用两臂共享
  guard 修复，并通过 smoke `2413c09a`（3/3）与 precheck `587d7c50`（12/12）。
  full `f8acd9e2` 为 Baseline 42/48、RSI 46/48；表面 token 1,813,753→1,078,947
  （-40.513%）因质量门槛失败且末尾两臂共同网络失败，只能作诊断。RSI 有12个 G0、
  36次 Fast、0 Composition、0维护错误；详情见
  `docs/workspace-workpack-v12-results-2026-09-13.md`，不得与 V4 主结论拼接。
- 协作：原 session 作为讨论 session，用户将另建执行 session。当前未替用户新建任务，没有安排自动化。
- 读取顺序：`AGENTS.md` → `docs/ARCHITECTURE.md` → `docs/DESIGN_DECISIONS.md` → `docs/EXPERIMENT_STATUS.md` → `docs/TODO.md`。
- 最终主证据是严格串行 `online-rsi-serial-final-v4`：固定 36 个不同 train 任务、独立空 RSI 经验、`run_limit=model_limit=read_limit=1`、同 session 交替运行。Baseline/RSI 均 36/36；Agent token 539,468→347,368（**-35.6%**），模型请求 203→114，工具 274→277。RSI 形成 6 个 G0，后续实际 Fast 复用 24 次；无 Composition、无 G1/G2。全部 Agent usage 完整、工具/维护错误均为0；Judge 26/36完成、10个服务超时、同模型且15个顺序分歧。详见 `docs/online-rsi-serial-final-results-2026-09-11.md`。运行 artifacts 不入 Git。
- 旧 `online-e2e-train-v1` 保留为负收益历史；`online-rsi-graph-matched-v4` 保留为分时匹配且 token -24.1% 的历史对照，不能与最终 V4 拼接。`cancelled_payments` 的编译器语义/等价读取修复在 V4 的严格对照中转正为 -44.0%。规模补验为 `efficiency-scale-serial-v4`，读取峰值固定为1，不主张并发收益。

## 已完成

任务库300任务，Python runtime，强基线/Plan基线/AutoTool/Graph RSI，在线图版本，冻结成对评测，真实执行可视化与回放，共用业务报告，匿名双顺序 LLM Judge（0–10维度分、0–1 reward）。本轮在现有 dict runtime 加入 Persistent TinyEdge 规范化 identity、train-only 连续读取片段挖掘、Fast/Composition/Fallback 路由、composition 模型角色和片段来源/绑定/执行 UI；不做 Transient TinyEdge Group。详细边界和实证见 [g-agent-local-composition-design-2026-09-10.md](../docs/g-agent-local-composition-design-2026-09-10.md) 与 [g-agent-local-composition-validation-2026-09-10.md](../docs/g-agent-local-composition-validation-2026-09-10.md)。

AutoTool/TIG 惯性执行已退役；保留 `backend/autotool.py` 的 BM25、参数契约和历史轨迹兼容，但不再调优触发或把历史拒绝写成收益。

修复后对照复用 RSI-only 的完整原始运行，检查 frozen manifest、36 条成功/usage、空经验与 train-only 顺序、模型名、预算、工具契约、任务哈希和 runtime revision 后，在新目录仅补跑 Baseline。Baseline 四个 `cancelled_payments` 样本有 `evidence_coverage` 有界失败；RSI 36/36。六个 G0 首次保存后实际被后续各五条同 family 任务使用；没有 G1/G2 或 Composition。Judge 72 请求、336,757 token，平均 reward Baseline/RSI 0.9768/0.9746，但同模型且 18 对顺序分歧，不作质量优劣证明。

最近功能提交：`9520ae7` Judge/reward/Plan对照；`e9e9df1` 强基线评测/报告；`e15d7c1` 执行回放；`f50d97d` 在线图进化。

## 环境与检查

```bash
git status --short
git log -3 --oneline
npm test
npm run test:frontend
npm run build
```

已有 `.venv`，前端 Node 22+。后端 `npm run dev:backend` 或 `.venv/bin/python -m backend serve`（4317），前端 `npm run dev:frontend`（5173）。启动前检查端口，避免重复服务；重启前确认没有在途模型任务。

主展示页面（开发基址 `http://127.0.0.1:5173`）：`/#home` 是交互式企业运营数字员工工作台；财务、客服、研发运营是同一员工的业务能力。页面支持 CSV/XLSX/JSON/TXT 上传、资料预览、确定性澄清、费用确认后的真实 Agent、同 run 的 DAG/模型/结构化/工具轨迹、HTML报告下载、导出、追问和历史工作。普通用户工作区使用独立存储且 `learning_enabled=False`，不会污染实验经验；追问只加载同工作区父报告的公开摘要，仍需本次观察证据。`/#experiments` 默认展示保存的 V17 48-task 结果和同族经验使用；`/#compare`、`/#insights`、`/#replay` 保留 V4 历史审计。公开历史数据经本地 JSON Schema 的只读工具访问，不能称生产企业写入部署。FastAPI 文档：`http://127.0.0.1:4317/docs`。
- 展示 API `GET /api/showcase/online-rsi-serial-final-v4` 和任务细节 `GET /api/showcase/online-rsi-serial-final-v4/pairs/{taskId}` 只读地从最终 V4 artifact 派生 DTO。它使用 gold 计算 audit，但不返回 gold、不调用模型、不改写 artifact：两臂结构化精确检查均 36/36；加上已知 ID、可追溯数字和金额单位措辞的有限摘要审计为 Baseline 25/36、RSI 26/36。后者不是全面自然语言事实判定。

清理前为104个Python测试；旧沙箱专用测试移除，共用协议测试改用注入工具。当前为92个Python测试、4个前端回放测试、类型检查和构建通过；展示 API/严格审计/事件执行来源的协议回归已覆盖。300条契约校验（10,400 次工具调用、0 次模型调用）通过。真实 train 尝试 `800f792f`、`9ef504a8`、`acfa3b5e`、`504f58d7`、`982d7e44` 未 materialize 可组合 TinyEdge：保留编译歧义/模型超时/网络失败，不声称 Composition 收益。

## 配置与私有状态

根 `.env` 已有用户配置，不读取/打印密钥，不覆盖文件。执行角色 `LLM_*`；规划 `PLANNER_*`；裁判 `JUDGE_*`，后两者未填时继承执行配置；HTTP全部经 `model_client.py`，thinking=false。最近实验为qwen/qwen3.5-27b，不代表以后配置不变。

本地不入Git的证据：

- `artifacts/taskbank/records.sqlite3`、`gold.json`：冻结记录/仅供硬评分的参考答案。
- `artifacts/taskbank-runs/<id>.json`：原始运行。
- `artifacts/online-graphs.json`：已有图版本、`workflows` / `tinyEdges` 与历史兼容字段；不再更新或执行 TIG 惯性动作。
- `artifacts/paired-evaluations/<id>.json`、`sources/`：成对实验与新实验源码快照。
- `artifacts/llm-judgements/<id>.json`、`inputs/`：裁判与输入。

在新机器或 worktree 中这些文件不一定存在。先核查，不静默重造数据或复制凭据。Linux需要时用户已允许 `ssh v100`；当前任务库可在本地运行。ERPNext/Zammad是另一条已部署的只读平台路径，连接状态需现场检查。

## 下一步

2026-09-12 在途工作：新增交互式工作区/三场景 Workpack 运行路径后，V6 预检发现
Baseline 的公开资料范围恢复缺陷，故 V6 不可用于同质量成本结论。V7 的公开
`requiredTableSlots` 确定性恢复已回归并实际运行 Smoke `59892bb0-66ab-4d7f-93b9-0ee7dc8e95e4`：
Baseline 3/3，RSI 1/3，故 V7 不可作为同质量成本结论。财务 RSI 已读取正确资料却模型手工
汇总错误；技术 RSI 是人工停止后的取消，成本和失败 artifact 均保留。

当前工作树新增 V8 共享确定性键控对账能力 `workspace_reconcile_keyed_sums`：只接受当前
工作区表/字段/键/别名/阈值并回传证据，不访问私有验收或自动改写报告。两臂同样可用，故
V8 是新的独立 staged runtime。Smoke `57c295a5-d7d9-4a22-b77c-d1893fef696f` 为 6/6；
预检 `31313718-fb89-491f-81d5-9ee7cb925433` 为 24/24，RSI token 比 Baseline 高10.0%，
但已验证财务实际调用对账工具、5 个 G0 形成和4次 Fast 复用。预检中的3次 schema/tool
拒绝与4次一次性公开范围恢复均可审计，没有维护错误或无界循环；正式 V8 train 将在不改
runtime 的前提下执行。详见 `docs/workspace-workpack-v8-reconciliation-protocol-2026-09-12.md`。
旧 V5/V6/V7 artifacts 保留。

当前可展示结论是在线经验积累与 Fast 复用：六个 family 均在最终严格串行 V4 中降低 token，全量达到 -35.6%。这不证明多代结构进化、Composition 收益、独立 Judge 优势或通用低延迟。不要重跑该实验直到结果好看；若继续研究，必须建立新版本、固定新协议，validation/test 反馈不得回写 Workflow/TinyEdge。

2026-09-11 收口补记：`online-rsi-all-train-saturation-v3` 的 30-family 首到达任务结果可受限展示（RSI token `-18.48%`、模型请求 `-28.73%`），但其 `runtimeOverhead` 含约 14.3 秒被误分类的 Composition 模型等待，不能用于 overhead 结论或与 V4 合并。`#live` 已支持真实、可保存回放的 Baseline/RSI 对照；启动必须显式费用确认，单任务为两次 Agent、两任务为四次 Agent，且后端拒绝并行 live 会话。预算暂停期间不发起额外模型调用，使用保存会话录制。

2026-09-11 展示叙事收口：原 `#employees` 三岗位卡已撤回，改为 `#home` 单一企业运营数字员工工作台，旧链接重定向。财务分析、客服分析、研发运营是可切换能力；首屏只展示业务需求、保存的真实工作记录、模型与 RSI 运行时差别、业务指标和完整 HTML 简报入口。36 个案例、原始任务 ID、审计和边界移至 `#compare`、`#insights` 与 `#replay`。工作台只读取最终 V4 DTO 和已有报告，没有新增 Agent/Judge/学习调用，也不把 HTML 报告称为 PPTX 或生产部署。验证：`npm test` 99 passed、`npm run test:frontend` 4 passed、`npm run build` passed、`git diff --check` passed；浏览器确认财务能力显示真实 Fast 流程的 RSI 运行时载入、同任务对照与格式化业务金额，且不显示 task ID/train/benchmark 语言。

每阶段结束更新本文件的基线、在途任务、验证结果和下一步；它是普通 Markdown 快照，没有自动 `.save_state` 命令。

平台恢复记录：远端 v100 容器运行正常，本地18080/18081隧道曾缺失；本轮已重新建立SSH转发。隧道属于进程状态，新session应核查，不能假定永久存活。

本轮恢复后 `npm run platforms` 检查 ERPNext/Zammad 均 reachable（只读端点），没有重新部署或重置远端数据库。

2026-09-14 阶段末验证：163项Python协议测试、4项前端回放测试、TypeScript/Vite构建、git diff --check通过。三岗位浏览器首传/解析/请求准备与同run报告下载已检查；这些不是额外模型实证。


## 2026-09-14 V3-r2 真实 API 预检结果

已按用户授权启动 `94620ba7-efd1-4fb9-b323-2bde8b22f78d` 的 12 对预检，但 F01 首对两臂均质量失败后严格停止；未启动其余任务。Baseline `limited`（24 请求、31 工具、609,579 token、144.346s、metrics 失败）；RSI `limited`（13 请求、20 工具、185,288 token、111.181s、metrics/selectedIds/groups 失败、Fast 0/1）。这是已保存的真实 API 失败工件，不能主张 69.60% token 差或任何效率/进化收益。下一步先修一对多金额/单位与报告交付契约，再以新空经验库重新预检。

## 2026-09-14 · 数据分析成本快照

`#analysis` 的每个测试组现从 `releases/analysis-manifest.json` 的版本化 OpenRouter 价格快照读取模型估算单价，并按每个保存 run 的真实 `inputTokens`、`outputTokens` 和 `models` 计算 USD 估算成本；没有完整 usage、没有记录角色模型、没有对应单价，或混合模型缺少可核对的 phase 计量时保持空值，不按 token 总量或默认模型猜测。当前快照：`qwen/qwen3.5-27b` 输入 `$0.195/M`、输出 `$1.56/M`；`qwen/qwen3.5-9b` 输入 `$0.080/M`、输出 `$0.130/M`，来源为 OpenRouter 标准价格页面，抓取日为 2026-09-14。

V17 48-task 保存工件全用 27B，估算成本 Baseline `$0.5635`、RSI `$0.3501`，在同任务质量门槛下对应 `37.9%` 估算节省；V4 36-task 为 `$0.1514`、`$0.1040`，对应 `31.3%`。财务归因候选的 RSI 有 usage 缺口，只展示已知绝对成本，不计算成本收益。
