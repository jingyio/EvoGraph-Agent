# 三场景真实数据任务库 public-v2-task-contract

已构造财务、客服、技术工单各 100 个任务，共 300 个。每个场景 10 个任务族，每族 10 个任务；同族使用不同来源记录。任务说明和筛选规则由本项目设计，业务记录来自公开真实数据，没有补造交易、投诉或 Issue。

`public-v2-task-contract` 保持 300 条任务的记录 ID、划分、参考时刻和内部评分答案不变，只修正了 Agent 可见的 `selectedIds` 说明：任务要求列出、筛选或排序记录时必须提交这些 ID；只有没有记录清单的任务才提交空数组。此前带有相反通用提示的运行应保留为合同缺陷预检，不能与 v2 结果拼接。

## 数据与任务分布

| 场景 | 来源 | 本任务库使用记录 | 任务数 | 工具数 |
|---|---|---:|---:|---:|
| 财务运营 | Olist 脱敏电商订单、支付、商品、客户与评价 | 1,000 笔订单，每任务 10 笔 | 100 | 11 |
| 客户投诉运营 | CFPB 公开投诉 | 500 条，每任务 5 条 | 100 | 10 |
| 技术工单 | zammad/zammad 的 GitHub Issues，排除 PR | 300 条，每任务 3 条 | 100 | 13 |

原始采集覆盖 99,441 笔 Olist 订单、2,024 条去重投诉和 811 条去重 Issues，再按固定算法选取任务记录。为避免稀有条件任务全为空集，从真实记录中选择部分符合条件的样本，并保留空结果案例；这是有目的的任务覆盖抽样，不代表原始业务分布。

每场景 60 训练、20 验证、20 测试；每任务族为 6/2/2。所有任务的主记录互不重复，财务还按 customer_unique_id 哈希分组，防止同一客户跨划分。客服/工单按记录 ID 隔离，不能由此声称自然语言主题或投诉人完全独立。测试任务及其答案不得用于图学习、负 motif 编译或提示反思。

## 30 个任务族

| 财务 | 客服 | 技术工单 |
|---|---|---|
| 支付、商品、运费金额盘点 | 产品分类分布 | open/closed 状态盘点 |
| 支付金额与订单金额核对 | 问题分类分布 | 标签覆盖 |
| 分期支付盘点 | 企业响应类型 | 未分派问题 |
| 多笔支付核查 | 响应及时性 | 超过 30 天未更新 |
| 运费占比核查 | 投诉渠道统计 | 未关闭且无评论 |
| 取消订单支付核查 | 投诉转交时差 | 最早未关闭问题 |
| 支付方式统计 | 公开叙述覆盖 | 里程碑缺失 |
| 高金额订单排序 | 企业投诉分布 | 关闭周期 |
| 客户地区支付统计 | 规则化跟进清单 | bug 标签筛选 |
| 交付状态支付核查 | 最新投诉排序 | 评论活跃度 |

这些任务是岗位分析与核查任务，不是自动付款、退款、回复客户或在线处理生产工单。CFPB 的公开叙述不是已核实事实，也没有完整客服多轮对话。GitHub Issues 是实际软件问题，不等同于企业内部客服工单。未将公开记录伪装为已有 ERPNext/Zammad 测试实例的生产数据。

## 工具接口

所有工具采用 `backend/tools.py` 的 Tool/JSON Schema 接口，参数强校验，未知字段拒绝。实际接口由 `backend/taskbank.py` 提供；每任务族的静态规格位于 `specs/taskbank/*.tools.json`，运行时 API 返回当前任务的精确规格。

- 财务：`finance_list_orders(page, pageSize)`、`finance_get_order(orderId)`、`finance_get_order_items(orderId)`、`finance_get_order_payments(orderId)`、`finance_get_customer(orderId)`、`finance_get_order_reviews(orderId)`。
- 客服：`support_list_complaints(page, pageSize)`、`support_get_complaint(complaintId)`、`support_get_response(complaintId)`、`support_get_dates(complaintId)`、`support_get_narrative(complaintId)`。
- 工单：`tickets_list_issues(page, pageSize)`、`tickets_get_issue(issueId)`、`tickets_get_labels(issueId)`、`tickets_get_assignment(issueId)`、`tickets_get_milestone(issueId)`、`tickets_get_activity(issueId)`、`tickets_get_resolution(issueId)`、`tickets_get_body(issueId)`。
- 每场景另有带场景前缀的 `get_task_scope()`、`sum_values(values)`、`count_values(values)`、`rank_values(records, direction, limit)`、`publish_report(metrics, selectedIds, evidenceIds, summary)`。排序方向为 asc/desc，数值为整数，并列按字符串 ID 升序。

金额统一为 BRL 分（Olist 原生币种 BRL）；时间差字段为秒。未将分期金额解释为未偿债务，未把多条支付记录当作重复扣款，未把 agency 转交时差解释为企业响应时长，未把项目更新时间阈值冒充真实 SLA。

所有源数据工具只能读取当前 task.recordIds 指定的记录。SQLite 以只读模式打开；报告保存在本地会话，不能修改源数据。工具输出带 `_evidenceRef`，发布报告须引用本任务实际观察过的全部主记录。

## 文件与运行

- `benchmarks/tasks.jsonl`：300 条可审查的任务定义，含来源 ID、划分、参考时刻、验收字段和预算建议，不含答案。
- `benchmarks/manifest.json`：来源 URL、许可说明、原始文件摘要、选取记录摘要与分布。
- `artifacts/taskbank-raw/`：原始来源缓存，被 Git 忽略；其中 draft-tasks-v0.jsonl 为本轮覆盖校验前的任务草稿，不属于最终基准。
- `artifacts/taskbank/records.sqlite3`：1,800 条主记录及其关联字段；`gold.json` 为内部参考答案，不通过工具或任务 API 提供。
- `artifacts/taskbank/validation.json`：全量工具验证结果。
- `artifacts/taskbank-sessions/`：手工调试会话及本地报告，不作为 LLM 运行统计。

`npm run taskbank:build` 在不存在任务定义时生成新库；存在时按冻结定义和来源缓存恢复数据库与参考答案，并检查选取记录摘要。上游记录变化会报错，不能静默刷新原有测试集。移到新机器时应携带冻结原始缓存或数据库/答案；仅克隆 Git 不保证能从动态 API 还原历史记录。

`npm run taskbank:validate` 遍历全部任务和字段接口，检查分页、分组隔离、参考答案可提交与错误答案被拒绝。此命令不调用 LLM。

页面：`http://127.0.0.1:5173/#taskbank`。可筛选任务、查看规格并手动调试工具；Agent 执行区已支持 ReAct、Plan + ReAct 和 Plan + AutoTool DAG，见 [执行机制](intent-autotool.md)。尚未运行完整 300 任务对照。

HTTP 接口：

```text
GET  /api/taskbank/manifest
GET  /api/taskbank/tasks?scenario=finance&split=train
GET  /api/taskbank/tasks/{taskId}/tools
POST /api/taskbank/sessions                 {"taskId":"finance-payment_totals-01"}
POST /api/taskbank/sessions/{sessionId}/call
     {"tool":"finance_list_orders","arguments":{"page":1,"pageSize":10}}
```

## 评分与验证范围

`publish_report` 校验整数/分组统计、筛选集合或排序、证据覆盖。参考答案存储与执行工具隔离；评分失败只返回不匹配字段名，不返回正确值。错误的数字、布尔冒充计数、重复 ID、错误排序、越界引用都不能通过。自然语言总结只保存，未进行全面语义评分。

本次 300 个任务完成 10,400 次本地工具契约检查，0 次 LLM。单元测试另用独立小样本校验金额口径、1 分容差、缺失数据、及时性未知值、30 天边界、排序和证据约束。不能将参考答案回填验证当作 Agent 成功率。后续质量/token 对比应先在训练/验证任务上固定策略，再对未用于优化的测试任务运行两种方法。

来源许可：Olist 为 CC BY-NC-SA 4.0；CFPB API 元数据标记 CC0；GitHub 用户 Issue 文本保留原作者权利，不将项目 AGPL 代码许可推定为用户文本许可。本地原始文本和数据库没有加入 Git，也没有发布到第三方。
