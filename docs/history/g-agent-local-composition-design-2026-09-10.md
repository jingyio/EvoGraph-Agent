# G-Agent 式局部规划复用 · 最小设计

日期：2026-09-10。范围是当前 TaskBank 的只读数据获取图；不是对参考论文或 `HG-Planning` 的完整复现。

## 目标与路由

每个 `graph_rsi` 任务在相同的图执行器前走且只走以下一条路径：

1. `fast`：已有同规范化任务模板、工具契约和执行器版本的完整 Workflow/Plan 时，直接复用其已保存 Plan 与图，不请求生成 Plan。
2. `composition`：Fast 未命中时，轻量规划角色只生成有序粗粒度子目标；本地检索 Persistent TinyEdge，为每个子目标确定性选择一个候选。只有所有子目标被覆盖、至少使用两个不同 TinyEdge、组合后的图通过契约/依赖校验时，才直接执行组合图。
3. `fallback`：任何覆盖、来源、绑定或组合校验不足均记录原因，由完整 Plan 角色生成 Plan，继续现有检索、编译、执行和恢复流程。

`composition` 记录最终 `selectedTinyEdgeIds`。执行器只消费这个已选清单和对应图模板，重新绑定当前任务的确定性槽位并校验；不会再次调用模型选择同一片段。粗计划的语义解释才使用 composition 角色。未单独配置该角色时，它继承 planner 配置，运行记录标注同模型，不能据此声称大小模型协同收益。

## 共享数据契约

持久化状态仍为 `artifacts/online-graphs.json` 的 Python dict，新增顶层 `tinyEdges`，不引入新的大型 IR。

- Workflow：现有保存图版本；包含 `id`、训练 `sourceRunId`、Plan、读取 nodes、工具契约范围和来源 split。
- Canonical operation：`tool`、该工具的 JSON 参数/输出契约、参数绑定槽类别（literal/page、item、result、foreach/reuse）和局部控制形状；不含旧记录 ID、答案或自由文本。
- Persistent TinyEdge：连续可执行 nodes 的有序片段，包含规范化 identity、`nodeTemplates`、Plan 子目标文本、输入/输出槽、support、`sourceWorkflowIds`、`sourceRunIds`、适用场景和工具契约哈希。
- Boundary：`defer`、分支/汇聚、非读取行为和不连续依赖都是不可跨越边界。只从一个线性读取链内提取片段。

入库仅来自结构化评分通过的 `train` Graph RSI 正常轨迹。每个 Workflow 对一个 identity 至多贡献一次支持度。默认仅 materialize 支持度至少 2、仍可由当前工具契约执行的片段；保存来源和支持度，即使未达门槛也不伪称可复用。

## Composition 与参数

粗计划 schema 为有序子目标（id、intent、dependencies），不包含工具、记录 ID 或答案。候选检索为本地规范化 token overlap，并严格限制同场景/同工具契约的已 materialize TinyEdge；这和论文的 embedding 检索不同。候选选择为可审计的确定性排序（分数、support、id），结果写入 `compositionPlan`、`graphSelection` 与 trace。

组合器按粗计划顺序展开选中片段，并只在相邻片段边界去重相同规范化 node。它重新命名 node ID、恢复片段内部依赖、连接无入边的后续片段到前一段出口；若形成歧义、多出口/多入口、重复 node 的参数契约不等或任何 `ordered_nodes` 校验失败，即拒绝组合并走 Fallback。节点内的参数仍是现有 `literal`、`item`、`result`、`foreach`、`paginate`、`reuse` 与 Motif `filter` 绑定；读取时全都来自本次任务的工具观察。筛选字段缺失/类型变化和缺失字段补查沿用已有失败关闭与模型恢复。

## 模型、成本与恢复

`backend/model_client.py` 仍是唯一 HTTP 边界，所有角色关闭 thinking。新增 `COMPOSITION_*` 配置和注入角色；运行分别记录 Fast 查找、composition 粗计划、Fallback 完整 Plan、图阶段和执行阶段的请求/token。路由、TinyEdge 检索、组合校验和持久化维护耗时分别记录为本地开销；Fallback 与恢复的模型/工具请求计入任务总成本。没有配置不同模型时 `models.composition` 与 `models.planner` 相同并明确展示。

本轮不实现论文 §4.6 的 Transient TinyEdge Group。现有普通并发读取不会被标成 shared-prompt batching，也不会计为其收益。

## 论文与参考实现差异

论文 §4.2–4.5 / 算法 1 与参考 `router.py` 使用工作流相似度、轻量模型的粗/细规划、候选阈值、至少两个片段的组合和 base-LLM fallback；`historical_tinyedge.py` 与 `tinyedge_mining.py` 以连续 executable fragments、support、closedness 和 executability 定义 Persistent TinyEdge；`tinyedge_param_batcher.py` 对运行时 prompt 组批另计。

本实现只借鉴这些边界：不引入向量 embedding、Hyperedge LRU、数据集特定 preference policy、AppWorld code generation、置信度升级和 gap-filler。主项目的 TaskBank 读取图已有严格 JSON 契约和可靠恢复，故 composition 只接受无 gap 的完整覆盖，且组合详细图是确定性展开而不是将历史节点文本作为提示词让模型再选择。由于不使用论文的检索/扩展器、基准与组批机制，本项目不能声称论文复现或论文的数值收益。

## 验收

- Fast 命中事件显示 `plan` 阶段请求为 0。
- 两个不同 Workflow 支持同一 identity，且 composition 轨迹显示同一个 Persistent TinyEdge ID 被复用。
- composition 实际生成、校验、执行组合 nodes；不是把片段放入提示词。
- 槽位和工具结果来自当前任务；图失败仍保留已有观察并进入既有 ReAct 恢复。
- trace/UI 展示路径、候选/选中 ID、来源、模型角色、每阶段 token、工具、延迟和维护开销。
- 训练任务仅用于入库/修订；验证与测试不产生 Persistent TinyEdge 或结构 Patch；没有影子 rollout。
