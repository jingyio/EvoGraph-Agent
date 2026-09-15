# 读取图与在线版本协议

这是现有 Python dict / JSON 的内部约定，不是独立 IR 框架。执行入口为 `backend/intent_graph.py:execute_graph`，共享结构校验为 `backend/graph.py:ordered_nodes`。目前仅支持读取 DAG；计算、报告发布和业务写操作继续由模型和现有工具执行。

节点沿用 `id/tool/arguments/dependencies/foreach/paginate`。参数来自本次工具结果，保存的图不包含历史记录 ID、答案或业务快照。`sourceEventSeqs`、版本的 `sourceRunId` 用于追溯。

## 筛选后补查 Motif

详情 Plan 步骤可保存 `selection.kind=match`，其中 `sourceStepId` 必须是该步骤的依赖，`field` 必须是来源列表工具声明的输出，当前仅支持 `operator=equals` 和原始类型字面量。编译器将它写入现有 `foreach.filter`，例如：

```json
"foreach": {
  "nodeId": "list_orders",
  "collectionPath": ["records"],
  "filter": {"field": "status", "operator": "equals", "value": "canceled"}
}
```

执行先收集本次分页列表，验证每条记录都有该字段且类型与字面量一致，再确定性筛选；仅命中的记录绑定详情 ID。实际入选/排除数量写入运行指标和 `motif` 事件。字段缺失、类型变化或无法绑定到声明字段时不扩大读取范围，保留已完成列表观察并交给本任务模型恢复。

当规划角色不能可靠选择列表条件时，使用 `selection.kind=model` 和原因；编译器将详情节点及其下游标为 `defer`。省略 `selection` 仍表示详情需要遍历全部记录，兼容旧保存 Plan。

## 字段复用与恢复

```json
{
  "id": "state",
  "tool": "tickets_get_issue",
  "arguments": {},
  "dependencies": ["list"],
  "reuse": {
    "nodeId": "list",
    "collectionPath": ["records"],
    "fields": ["state"],
    "onMissing": "detail"
  }
}
```

每次执行检查 `records` 是对象数组，逐条检查字段是否存在。`null` 是存在的字段值，不擅自视作缺失；这里不证明字段语义正确或数据新鲜。字段缺失时，使用当前记录 `id` 调用本节点的单 ID 读取工具，验证返回 ID 和字段后合并。仅补查缺失的记录，同 ID 的补查去重；形状变化、非法 ID 或补查失败交给本次任务的模型恢复。原始工具观察不被改写。

`elidedToolCalls` 是图内相对于被替代的逐 ID 查询的消除计数，不等于相对于 ReAct 的净收益。`recoveryToolCalls` 是成功的缺字段补查次数，实际补查请求（含失败）均通过统一工具计量进入总调用和延迟。

没有 `onMissing` 的旧复用节点在字段缺失时拒绝执行，不能静默当成成功。类型校验本身不证明删除某个节点保持任务语义；自然任务评分和受限适用范围仍然必要。

## 失败子图交接

节点可以增加 `defer: true`，其所有下游节点也必须交接。执行器保留图中的节点、依赖和来源，但把该子图交给模型处理；此前成功观察保留，已成功的上游不整体重跑。Prompt 明确列出待处理工具，模型获得完整工具集，继续受原任务预算和工具权限限制。

这种修改表示学会在特定结构上交接模型，不表示已学会任意参数纠错。模型恢复消耗的 token、工具调用与延迟必须计入总成本。

## Patch 与版本

在线反思目前只输出本地、有限操作：

- `compile_observed_graph`：保存成功训练任务实际执行的参数化读取图，形成 G0。
- `reuse_with_fallback`：根据 Plan 显式字段需求和分页列表输出契约，将详情节点改为带逐条补查的复用节点。
- `defer_subgraph`：图工具失败后，同一任务模型成功调用同一工具且整任务结构化评分通过，将失败节点及依赖它的子图交接模型。
- `rebuild_after_failure`：无法直接提取 Patch 时，后续正常训练任务重新规划，成功后形成保留父 ID 的修订图。

Patch 与父图保存完整快照，运行以实际读取的图版本 ID 记账。结构没有变化不新增版本；失败原因未知、未完成任务或没有有效修复证据时，保留待分析，不捏造修复。多个并发任务固定使用各自选中的快照，旧版本的迟到反馈不覆盖已产生的后继图。

## 数据隔离与生命周期

匹配键包含场景、任务类型、仅替换明确 task ID/记录数/参考时刻槽位后的任务文本、全部工具契约、数据集 manifest 和执行器版本。不会根据相似词把图直接扩展到全场景。保存计划仅包含工具说明和显式字段名，不复用旧任务自由文本。

`probation` 表示相同模板与契约内的正常任务试用。三个不同任务通过完整结构化评分、没有整图回退且 usage 完整时标记 `family-supported`。这只是使用门槛，不能声称统计显著改进。图失败标记 `needs-repair`；有依据时生成子图，未能修复时下一次正常任务重新规划，不自动把父图设为新的默认版本。

训练任务可以生成修改；验证任务只更新验证证据；测试任务只读取已获支持的版本，执行结果不回写经验库。需要固定整批评测时，应先结束训练/验证流量，冻结版本文件，再运行测试，避免同时到达的新训练任务改变测试所见版本。
