# 项目状态快照

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
