# 工具简明目录

仅列用途和主要返回内容；精确参数见 specs/taskbank 或任务 API。

## finance

| 工具 | 用途与返回内容 |
|---|---|
| `finance_list_orders` | 分页列出本任务订单记录及 ID；返回 records 数组（id、概要字段）、page、mayHaveMore。 |
| `finance_get_order` | 查看订单状态和配送时间；返回 status、purchased_at、delivered_at、estimated_at。 |
| `finance_get_order_items` | 核对商品金额、运费及商家；返回 items，每项含 price_cents、freight_cents、product_id、seller_id。金额为 BRL 分。 |
| `finance_get_order_payments` | 核对支付金额、支付方式、分期和多笔支付；返回 payments，每项含 amount_cents、method、installments、sequence。金额为 BRL 分。 |
| `finance_get_customer` | 按客户地区汇总或识别同一客户；返回 customer_state、customer_id、customer_unique_id。 |
| `finance_get_order_reviews` | 查看订单满意度及评价内容；返回 reviews，含 score、title、body。 |
| `finance_get_task_scope` | 读取当前任务范围、参考时间及输出字段名称；不返回参考答案。 |
| `finance_sum_values` | 整数求和，不做币种换算。输入值需来自已读取记录。 |
| `finance_count_values` | 按精确字符串分组计数；缺失字段使用 (missing)。 |
| `finance_rank_values` | 按整数值排序，并列按记录 ID 字符串升序。 |
| `finance_rank_time_values` | 按 ISO-8601 时间排序，并列按记录 ID 字符串升序。时间比较不应由模型手工判断。 |
| `finance_elapsed_seconds` | 计算两个 ISO-8601 时间戳的 end - start 秒数。时间差计算不应由模型手工心算。 |
| `finance_publish_report` | 保存本地分析结果并检查结构化事实。不是企业系统写入，不发送消息；不返回标准答案。 |

## support

| 工具 | 用途与返回内容 |
|---|---|
| `support_list_complaints` | 分页列出本任务投诉记录及 ID；返回 records 数组（id、概要字段）、page、mayHaveMore。 |
| `support_get_complaint` | 分析投诉产品、问题分类、企业和渠道；返回 product、sub_product、issue、sub_issue、company、submitted_via。 |
| `support_get_response` | 核对企业响应类别和是否及时；返回 company_response、company_public_response、timely。 |
| `support_get_dates` | 计算投诉接收到转交企业的时差；返回 date_received、date_sent_to_company。 |
| `support_get_narrative` | 阅读消费者公开叙述或检查叙述是否为空；返回 narrative 文本。 |
| `support_get_task_scope` | 读取当前任务范围、参考时间及输出字段名称；不返回参考答案。 |
| `support_sum_values` | 整数求和，不做币种换算。输入值需来自已读取记录。 |
| `support_count_values` | 按精确字符串分组计数；缺失字段使用 (missing)。 |
| `support_rank_values` | 按整数值排序，并列按记录 ID 字符串升序。 |
| `support_rank_time_values` | 按 ISO-8601 时间排序，并列按记录 ID 字符串升序。时间比较不应由模型手工判断。 |
| `support_elapsed_seconds` | 计算两个 ISO-8601 时间戳的 end - start 秒数。时间差计算不应由模型手工心算。 |
| `support_publish_report` | 保存本地分析结果并检查结构化事实。不是企业系统写入，不发送消息；不返回标准答案。 |

## tickets

| 工具 | 用途与返回内容 |
|---|---|
| `tickets_list_issues` | 分页列出本任务技术工单记录及 ID；返回 records 数组（id、概要字段）、page、mayHaveMore。 |
| `tickets_get_issue` | 盘点技术问题状态、创建时间和更新时间；返回 title、state、created_at、updated_at。 |
| `tickets_get_labels` | 按标签分类、筛选 bug 或检查缺少标签；返回 labels 字符串数组。 |
| `tickets_get_assignment` | 检查技术工单是否有负责人；返回 assignee_count 指派人数。 |
| `tickets_get_milestone` | 检查技术工单是否设置里程碑；返回 milestone（编号、标题或 null）。 |
| `tickets_get_activity` | 统计讨论评论数、筛选无评论或近期活动；返回 comments、updated_at。 |
| `tickets_get_resolution` | 计算技术问题从创建到关闭的周期；返回 state、created_at、closed_at。 |
| `tickets_get_body` | 阅读技术问题描述与原始链接；返回 body、url。 |
| `tickets_get_task_scope` | 读取当前任务范围、参考时间及输出字段名称；不返回参考答案。 |
| `tickets_sum_values` | 整数求和，不做币种换算。输入值需来自已读取记录。 |
| `tickets_count_values` | 按精确字符串分组计数；缺失字段使用 (missing)。 |
| `tickets_rank_values` | 按整数值排序，并列按记录 ID 字符串升序。 |
| `tickets_rank_time_values` | 按 ISO-8601 时间排序，并列按记录 ID 字符串升序。时间比较不应由模型手工判断。 |
| `tickets_elapsed_seconds` | 计算两个 ISO-8601 时间戳的 end - start 秒数。时间差计算不应由模型手工心算。 |
| `tickets_publish_report` | 保存本地分析结果并检查结构化事实。不是企业系统写入，不发送消息；不返回标准答案。 |
