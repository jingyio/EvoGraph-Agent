# 当前架构

核对日期：2026-09-13；功能演进基线：`9520ae7`，本文包含其后的沙箱清理和交互式工作区，当前行为以本文所属提交为准。本文件描述已实现状态，未实现方向见 [TODO.md](TODO.md)，设计约束见 [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)。

## 目标与边界

用数字员工任务证明相同或更好质量下的 token/cost/latency 改善，并取得递归进化与流程可靠性的独立证据。不是通用 Agent 平台；没有训练或修改基础模型。前端 React/TypeScript，后端 Python/FastAPI，图处理 NetworkX。

核心思想是把可确定执行的结构从模型决策中分离。当前主要覆盖读取图，不能把它描述成完整业务工作流编译器，也不声称完整复现 AutoTool/G-Agent/MotifAgent 论文。

## 当前任务库路径

```text
React: WorkspaceWorkbench（默认 `/#home`） / WorkpackExperimentPanel（`/#experiments`）
       └─ CompareExperience / RsiInsights / TaskReplay / 历史实验面板
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

Graph RSI 命中版本时同时复用保存的 Plan 和读取图，规划请求为零。Plan 已去除旧任务自由文本，仅保留字段需求/工具说明；业务 ID 从本次读取绑定，不复用旧观察结果。匹配使用场景、family、规范化任务模板、工具契约、数据集摘要与执行器版本。

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

前端 `5173` 默认 `#home`，并提供 `#experiments`、`#compare`、`#insights` 和 `#replay?task=<id>`。默认主页是一个可交互的企业运营数字员工工作台：切换财务、客服、技术工单能力后，用户拖拽/选择 CSV/XLSX/JSON/TXT，并手写业务请求；资料预览、确定性澄清、费用确认、真实 Agent、同一 run 的 DAG、模型/结构化/工具事件、HTML 报告、导出和同工作区追问都由保存 run ID 关联。用户资料、解析表和任务文本按工作区隔离保存于 `artifacts/workspaces/<workspace-id>/`，普通用户运行使用独立目录且 `learning_enabled=False`，不会污染实验经验。`#home` 不展示 Workpack、预置题目或历史 pair；`#experiments` 才读取独立 Workpack 工件，展示冻结 manifest、同族 G0/Fast 链、同任务累计 token、质量门槛和完整恢复账本。`#compare`、`#insights` 和 `#replay` 保留历史 V4 的只读展示。公开资料经本地受限只读工具访问，不能称为生产企业写入部署；后端为 `4317`，模型配置只在根 `.env`。

运行与恢复命令、配置字段、持久化位置见 [.codex/state.md](../.codex/state.md)。实验结论见 [EXPERIMENT_STATUS.md](EXPERIMENT_STATUS.md)，不要从截图或旧 README 推断当前性能。

`scripts/run_online_e2e.py` 是独立的 36-task 在线训练对照入口。它创建专用 run/experience 目录，基线禁用学习，RSI 仅从此前正常 train 任务更新经验；每次启动后立即 checkpoint run ID，避免恢复时重复学习。`--rsi-source` 只复用已审计的 RSI-only source，并在新目录补跑匹配 Baseline；结果明确标注为分时匹配。静态页由 `/api/online-e2e/{id}/report` 提供，并按 family 给出六条经验形成/复用与准确 trace/report 入口。

完成的严格串行工件 `online-rsi-serial-final-v4` 额外从原始 run 聚合 P95/最大延迟、最大 token、报告恢复、维护、分页和 phase token。它只生成派生摘要，不会重放 Agent/Judge；Agent 成本与 Judge 的已记录 token 下限分开显示。最终证据边界见 [online-rsi-serial-final-results-2026-09-11.md](online-rsi-serial-final-results-2026-09-11.md)。

展示层的严格报告审计不会改变上述原始结构化 evaluation：它再次核查报告 schema、metric/selection/evidence 精确性、证据在当前 trace 中确已观察，并以有限规则检查摘要中的已知 ID、数字和 `cents` 金额表述。gold 仅在后端进程内用于得到布尔结果；不返回预期答案或未通过的具体业务真值。
