# 当前架构

## 2026-09-14 V3-r3 当前运行线

`releases/manifest.json` 当前唯一候选是
`trajectory-p05-v3-r3-candidate` / `trajectory-review-v3-r3`。它冻结 48 个 train、6 个
validation、6 个 test 任务，固定 12 对预检和 `run=model=read=1`；尚未启动，因此当前证据页只展示
任务审阅与“尚未完成正式对照”。

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


## 当前前端与发布清单

主导航只有 `#home` 数字员工和 `#evidence` 当前证据，全部页面共用 `App.tsx` 的壳。
数字员工面向自由问题、附件、澄清、费用确认、业务成果、结构化清单下载与同工作区追问；
图参数、完整事件、错误和字段契约在技术审计折叠区。可从“继续之前的工作”恢复用户
自己的保存工作区/run。这里不展示实验选择器或benchmark总览。

`releases/manifest.json` 是唯一当前选择源。当前指向尚未运行的
`trajectory-p05-v3-r3-candidate`，任务资产为 `trajectory-review-v3-r3`：48 train、6 validation、
6 test，严格预检固定为六个 cohort 各两项，共12对。页面显示计划48、已运行0和“尚未获得
证据”；不自动补入 V17、V4、V2 或任何历史效率数字。

`backend/releases.py:ReleaseEvidence` 提供 `/api/releases/current`、发布专属evidence、
pair、run、input、report和selection。每次核对experiment/runtime/asset/protocol以及
run-task归属，缺失/不匹配报错且不回退其他实验。指标、可靠性、图与匹配修订/来源/
后续使用、报告和曲线均从这一成员集合派生。未运行候选只校验受版本控制的公开资产清单
并返回空证据。读取不学习、不执行工具、不写原工件。`CurrentEvidence.tsx` 按业务成果→
可信度→进化→成本/可靠性→回放展示，所有下钻保留release边界。成本区同时展示保存工件
的单任务token/串行latency节省率、累计净节省率和两臂绝对曲线；失败且usage完整的pair
保留，usage不完整形成缺口而非补0。

`#archive` 从页尾默认折叠的“开发与历史”进入。历史目录显示各自版本、状态、runtime、
任务资产与协议，无跨版本总计。旧experiments/trajectory/compare/insights/replay/
showcase/live/evaluation/evolution/taskbank/platforms/demo全部转到archive路由并保留
查询参数；具体旧默认指向由manifest.legacyRoutes声明，不按时间猜。历史组件按需加载，
V4页面的实验身份由Archive上下文传入，showcase.ts不再硬编码实验。RsiInsights不再
混读V3，V3保留独立原报告深链。原历史API和artifacts未删除或改写。

完整路由/数据源映射、API和验收见 [版本隔离记录](frontend-release-isolation-2026-09-14.md)。
下面提及旧页面路由的段落是其原业务路径说明；当前入口统一经上述archive兼容层。

## 2026-09-14 工作区轨迹路径（P0.5首阶段）

`backend/trajectory.py` 对通过结构化评分的正常train收据诱导read/compute节点，记录
sourceRun/traceIndex/digest、嵌套当前table/task槽、源请求和操作覆盖描述。临时Plan仍可
用于冷启动，但未执行节点不进入该经验。工作区走当前API/schema硬筛选＋一次有界
语义匹配，不使用family/template/workpackId/difficulty/privateValidation路由；匹配请求
计入同一Agent模型预算与`match`阶段。无法可靠参数化的操作和语义正文留给本次模型。

G保存结构变化；M保存适用描述变化。正常成功同结构在新schema下执行可单独扩展M的
schema约束；结构相同/仅顺序变化不增加G。普通用户只读使用reviewed经验、不学习；
validation/test不写工作区经验。真实G1已有，但后续使用未观察到，不能称进化验收完成。
嵌套上游output推导及报告/草稿/导出图调度尚未实现；本地产物仅已具运行内幂等。

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
React: WorkspaceWorkbench（数字员工 `/#home`） / CurrentEvidence（当前证据 `/#evidence`）
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

前端 `5173` 默认 `#home`，当前证据为 `#evidence`；旧 `#experiments`、`#compare`、`#insights` 和 `#replay?task=<id>` 统一重定向到历史区域。默认主页是一个可交互的企业运营数字员工工作台：切换财务、客服、技术工单能力后，用户拖拽/选择 CSV/XLSX/JSON/TXT，并手写业务请求；资料预览、确定性澄清、费用确认、真实 Agent、同一 run 的 DAG、模型/结构化/工具事件、HTML 报告、导出和同工作区追问都由保存 run ID 关联。每个工作区使用可读目录名（如 `finance-取消订单复核-a1b2c3d4`），完整 UUID 只作为内部 API、证据和运行关联身份。用户输入保持可读布局：`inputs/` 是原始附件，`requests/` 是已提交问题文本，`.rsi/` 仅保存解析表、任务状态和内部草稿；普通用户运行使用独立目录且 `learning_enabled=False`，不会污染实验经验。旧根目录 JSON/`sources/` 与 UUID 目录工作区仍可恢复，但不在恢复时迁移或改写。`#home` 不展示 Workpack、预置题目或历史 pair；`#experiments` 才读取独立 Workpack 工件，展示冻结 manifest、同族 G0/Fast 链、同任务累计 token、质量门槛和完整恢复账本。`#compare`、`#insights` 和 `#replay` 保留历史 V4 的只读展示。公开资料经本地受限只读工具访问，不能称为生产企业写入部署；后端为 `4317`，模型配置只在根 `.env`。

运行与恢复命令、配置字段、持久化位置见 [.codex/state.md](../.codex/state.md)。实验结论见 [EXPERIMENT_STATUS.md](EXPERIMENT_STATUS.md)，不要从截图或旧 README 推断当前性能。

`scripts/run_online_e2e.py` 是独立的 36-task 在线训练对照入口。它创建专用 run/experience 目录，基线禁用学习，RSI 仅从此前正常 train 任务更新经验；每次启动后立即 checkpoint run ID，避免恢复时重复学习。`--rsi-source` 只复用已审计的 RSI-only source，并在新目录补跑匹配 Baseline；结果明确标注为分时匹配。静态页由 `/api/online-e2e/{id}/report` 提供，并按 family 给出六条经验形成/复用与准确 trace/report 入口。

完成的严格串行工件 `online-rsi-serial-final-v4` 额外从原始 run 聚合 P95/最大延迟、最大 token、报告恢复、维护、分页和 phase token。它只生成派生摘要，不会重放 Agent/Judge；Agent 成本与 Judge 的已记录 token 下限分开显示。最终证据边界见 [online-rsi-serial-final-results-2026-09-11.md](online-rsi-serial-final-results-2026-09-11.md)。

展示层的严格报告审计不会改变上述原始结构化 evaluation：它再次核查报告 schema、metric/selection/evidence 精确性、证据在当前 trace 中确已观察，并以有限规则检查摘要中的已知 ID、数字和 `cents` 金额表述。gold 仅在后端进程内用于得到布尔结果；不返回预期答案或未通过的具体业务真值。

## 正式运行前任务审阅

`ReleaseEvidence` 对 `trajectory-plan` 发布返回 `taskReview`：六个业务契约、输入表字段、
8个train题面变体、预检位置和公开来源。题面由 `request_for()` 生成后与冻结资产中的
`requestHash` 逐项核对；数量、版本或题面不一致均失败关闭。`CurrentEvidence` 在候选未运行时
展示该审阅清单，并把质量、成本与回放明确显示为“尚未运行”，不显示0/0 usage卡或空方法回放。
该读取路径不创建实验、不加载私有答案、不调用模型。内容审计见
[正式运行前任务审阅](trajectory-v3-run-approval-review-2026-09-14.md)，两臂实际工具面与报告
Schema见[任务与工具契约审阅](trajectory-v3-task-and-tool-review-2026-09-14.md)。


### V3-r2 历史失败预检与 V3-r3 候选投影

`ReleaseEvidence` 对 candidate 的已保存 trajectory experiment 执行 runtime、资产、协议和 pair/run 身份校验。未运行的 V3-r3 只显示冻结任务审阅，不显示指标或曲线；若预检 `quality_stopped`，对应历史 release 只保留同一运行的失败报告、输入、轨迹和绝对开销。节省率/累计收益曲线关闭，直到完整质量门槛通过。
