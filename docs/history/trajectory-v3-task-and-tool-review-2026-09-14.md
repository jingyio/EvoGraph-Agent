# P0.5 V3-r2 任务与工具契约审阅

日期：2026-09-14。当前实验 `trajectory-p05-v3-r2-candidate` 为 `not-started`。本文只描述
已经冻结的用户输入、通用工具面和后台交付校验；不运行模型。

## 模型实际收到的任务形式

模型收到的是当前工作区的自然业务请求与资料 schema。它不会收到 cohort 名、任务编号、私有
答案或机器交付契约：

```json
{
  "taskId": "运行时 UUID",
  "scenario": "finance | support | tickets",
  "split": "train",
  "request": "自然业务请求",
  "schemaContract": {
    "tables": [{"id": "当前附件表", "fields": ["当前字段"]}]
  }
}
```

用户题面可以要求业务口径、阈值、缺失语义、成果和禁止动作，但不规定如何读取、关联或计算。
完整冻结题面在 [运行前审阅](trajectory-v3-run-approval-review-2026-09-14.md) 与 `/#evidence`
中查看。每个 cohort 有 8 个 train 变体，cohort 标签只留在离线实验清单。

## 两臂共同的业务工具

Baseline 与 RSI 从同一个 `WorkspaceManager.tools()` 获得 20 个工作区工具。表 ID 的 JSON
Schema 只允许当前工作区实际表，不能访问其他任务或工作区。

| 类型 | 工具 | 用途 |
|---|---|---|
| read | `workspace_list_sources` / `workspace_get_schema` / `workspace_profile_table` | 了解当前附件、字段、类型、行数和缺失情况 |
| read | `workspace_preview_rows` / `workspace_get_row` / `workspace_filter_rows` / `workspace_sort_rows` | 查看、筛选、排序当前资料并得到稳定资料引用 |
| read | `workspace_join_rows` / `workspace_compare_tables` | 按显式键关联或比较当前两张表 |
| compute | `workspace_aggregate_rows` | 计数、分组计数和数值汇总 |
| compute | `workspace_reconcile_keyed_sums` | 按当前键汇总一对多资料、派生总额、比较阈值并保留资料引用 |
| compute | `workspace_ordered_partition` | 按当前排序字段进行确定性前后分段 |
| read | `workspace_search_text` / `workspace_find_evidence` / `workspace_get_policy_excerpt` | 在当前文本资料中检索并回查资料依据 |
| read | `workspace_get_task_context` / `workspace_list_saved_reports` | 读取本次要求或同工作区已保存成果摘要 |
| artifact | `workspace_save_draft` / `workspace_export_csv` | 保存本地草稿或当前资料 CSV，不执行外部操作 |
| artifact | `workspace_publish_report` | 保存本次有资料依据的业务报告 |

这些工具没有网络搜索、付款、发消息、工单更新、代码执行或外部写入能力。两臂有相同工具、
模型、附件、通用执行提示和限制；RSI 的差异只来自成功 train 轨迹的匹配与复用。

## 后台 Delivery Contract

`workspace_publish_report` 的动态 JSON Schema 承载机器可检查的报告字段：总体数值、业务记录
选择、每个独立原因及当前实际观察的资料引用。它用当前场景的业务 ID 字段校验清单，资料引用
只能来自本次 run。工具 Schema 约束最终交付格式，但没有任何参数能指定读取顺序、关联方式、
计算步骤或结论。

私有评分继续核对真实业务数值、清单和资料覆盖范围；私有真值不会传入模型、工具说明、任务题面、
图匹配器或浏览器。`deliveryContract` 只服务工具构造、公开范围恢复与审计事件，不再作为模型
message 或 trajectory descriptor 的输入。

## RSI 内部控制工具

这些不是业务资料工具，也不执行外部动作：

- `submit_plan`：冷启动时提交至多 10 个资料获取子目标及依赖，不提交答案。
- `bind_trajectory`：有候选经验时只做当前请求与已执行轨迹的兼容性判断和槽绑定，最多 `partial`。
- `request_tools`：本地检索不足时更新简短意图后返回候选工具卡。

成功 train 轨迹只可保存实际执行成功的 read/compute 节点。报告、草稿、CSV 和正文始终由本次
模型生成；失败 run、validation、test 都不晋升经验。

## Fast 质量门槛

V3-r2 的六个连续 cohort 各有 8 项。每个 cohort 的首项可以冷启动，后续任务只有在真实轨迹
通过、图与当前资料兼容时才可能 `Fast`。候选要求保存 RSI run 的实际 `planningPath=fast` 占比
至少 50%；冷启动、partial、composition 和 fallback 一律不计。未达到即保持候选，不显示为
Fast 收益或正式发布证据。
