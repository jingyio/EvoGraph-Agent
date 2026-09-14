# P0.5 V3 任务与工具契约审阅

日期：2026-09-14。当前实验仍为 `not-started`，本文只描述实际将交给模型的公开输入与工具。

## 任务输入形式

每个任务由一个隔离工作区、一个自然语言请求和当前附件解析表组成。模型能看到：

```json
{
  "taskId": "运行时UUID",
  "scenario": "finance | support | tickets",
  "split": "train",
  "request": "完整业务题面",
  "schemaContract": {
    "tables": [{"id": "orders", "fields": ["order_id", "status", "purchased_at", "purchased_month"]}]
  },
  "deliveryContract": {
    "requiredTableSlots": ["orders", "payments", "items"],
    "requiredMetricKeys": ["...题面声明的精确指标键..."],
    "requiredGroupNames": ["...题面声明的精确原因组..."],
    "evidenceScope": "current attachment rows; no outside records"
  }
}
```

六个契约的完整题面可直接审阅：

- 财务主问题：[test/财务/问题.txt](../test/财务/问题.txt)
- 财务变化问题：[test/财务/问题-小幅变化.txt](../test/财务/问题-小幅变化.txt)
- 客服主问题：[test/客服/问题.txt](../test/客服/问题.txt)
- 客服变化问题：[test/客服/问题-小幅变化.txt](../test/客服/问题-小幅变化.txt)
- 技术主问题：[test/技术工单/问题.txt](../test/技术工单/问题.txt)
- 技术变化问题：[test/技术工单/问题-小幅变化.txt](../test/技术工单/问题-小幅变化.txt)

每个契约8个train变体仅改变题面明确的阈值；`/#evidence` 会显示全部48个题面及hash。

## 两臂共同的业务工具

Baseline与RSI底层都从同一个 `WorkspaceManager.tools()` 得到以下20个工具。表ID的JSON Schema
在运行时只允许当前工作区实际表ID，不能读取其他任务或工作区。

| 类型 | 工具 | 必要参数 | 返回/作用 |
|---|---|---|---|
| read | `workspace_list_sources` | 无 | 当前附件与解析表 |
| read | `workspace_get_schema` | 可选tableId | 字段、类型、缺失、行数 |
| read | `workspace_profile_table` | tableId | 数值范围与缺失概览 |
| read | `workspace_preview_rows` | tableId,page,pageSize | 当前行及稳定evidence引用 |
| read | `workspace_get_row` | tableId,rowId | 单行及evidence引用 |
| read | `workspace_filter_rows` | tableId,filters,page,pageSize | 声明条件筛选 |
| read | `workspace_sort_rows` | tableId,field,direction,page,pageSize | 稳定排序 |
| read | `workspace_join_rows` | left/right表与显式键,page,pageSize | 显式键关联，不猜键 |
| compute | `workspace_aggregate_rows` | tableId,operation | count/nonempty_count/sum/avg/min/max/group_count |
| compute | `workspace_ordered_partition` | 主表、键、排序字段、measures | 确定性前后半分段；当前六题一般不需要 |
| compute | `workspace_reconcile_keyed_sums` | anchor表、keyField、aggregates | 一对多按键汇总、派生总额、阈值比较、缺失侧null |
| read | `workspace_compare_tables` | 两表、keyField、fields | 新增/缺失/变化行 |
| read | `workspace_search_text` | query,limit | 当前文本字段检索 |
| read | `workspace_find_evidence` | evidenceRefs | 稳定引用回查当前行 |
| read | `workspace_get_policy_excerpt` | query,limit | 仅搜索用户附件中的政策文本 |
| read | `workspace_get_task_context` | 无 | 当前请求、表摘要、安全边界 |
| read | `workspace_list_saved_reports` | 无 | 同工作区历史报告摘要；实验新工作区为空 |
| artifact | `workspace_save_draft` | title,body | 只保存本地草稿，无外部动作 |
| artifact | `workspace_export_csv` | tableId,name；可选rowIds | 只保存本地CSV |
| artifact | `workspace_publish_report` | metrics,groups,selectedIds,evidenceIds,summary | 保存报告并立即执行结构化校验 |

当前实验任务的 `workspace_publish_report` 已改为前置强Schema：

```json
{
  "metrics": {
    "<每个题面声明的键>": "integer；全部键必填；禁止额外键"
  },
  "groups": [{
    "name": "只能取题面声明的组名",
    "reason": "非空字符串",
    "condition": "非空字符串",
    "count": "非负整数",
    "selectedIds": ["去重业务ID字符串"],
    "evidenceIds": ["实际观察的稳定行引用"]
  }],
  "selectedIds": ["各组业务ID去重并集"],
  "evidenceIds": ["至少1条实际观察引用"],
  "summary": "1–6000字符",
  "assumptions": ["可选"]
}
```

`groups`、精确metrics键和合法组名现在在模型调用工具时就校验，不再等报告提交后才发现格式缺失。
后端仍继续核对组数量、业务ID并集、私有期望值和证据是否来自本次实际观察。

## RSI内部控制工具

这些不是业务数据工具，也不执行外部动作：

- `submit_plan`：冷启动时，规划角色提交最多10个数据获取子目标、依赖和语义表槽；不提交参数或答案。
- `bind_trajectory`：有候选经验时，匹配角色只做兼容性判断和当前题面参数槽绑定；必须引用当前题面原文，最多返回partial。
- `request_tools`：RSI执行阶段本地检索不足时更新简短意图，再返回候选工具卡。

成功train轨迹可保存已实际执行的read与compute节点。报告、草稿和CSV参数始终是
`current_model_output` 边界，旧报告不会被图复制。失败run不晋升经验；validation/test不学习。

## 当前审阅结论

- 工具只读当前附件或在本地确定性计算；没有网络搜索、付款、消息、工单更新、代码执行或外部写入工具。
- 两臂共享相同20个底层业务工具、同一执行提示、模型、附件和任务；RSI的差异是轨迹匹配/复用和本地工具检索。
- 工具集是通用工作区集合，其中ordered partition、table compare、policy和历史报告对当前六题通常无用；保留它们会增加基线工具选择负担，但属于两臂共享的真实产品工具面。
- 任务自然cohort的稀疏正例与空组限制见[正式运行前任务审阅](trajectory-v3-run-approval-review-2026-09-14.md)。
