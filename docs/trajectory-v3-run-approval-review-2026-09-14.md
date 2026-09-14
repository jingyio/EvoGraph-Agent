# P0.5 V3 正式运行前任务审阅

日期：2026-09-14。当前发布为 `trajectory-p05-v3-candidate`，实验 ID 为
`not-started`。本文件和 `/#evidence` 只展示冻结题面与输入契约，不启动 Agent、Judge 或
任何付费模型请求。

## 审阅范围

- 任务资产：`trajectory-review-v2`
- 规模：48 train、6 validation、6 test；这里的“48”指正式训练对照，不是48个 test。
- 组织：财务、客服、技术工单三个场景；每场景两个业务契约；每契约8个不同 train 实例、
  1个 validation、1个 test。
- 首轮预检：财务订单复核1–3 → 客服时效复核1–3 → 技术活动分诊1–3，共9对。控制器严格
  串行，任一 pair 的两臂质量、usage 或维护门槛失败即停止，因此财务三对未通过时不会进入客服。
- 正式 full：只能在同一 runtime 的9对预检全部通过后启动48对 train。validation/test 本轮不运行，
  也不写入经验。

## 六个业务契约

| 场景 | 契约 | 输入表 | 变化参数 | 输出分组 |
|---|---|---|---|---|
| 财务 | 订单金额与分期复核 | orders / payments / items | 差额阈值5或10分；分期阈值8/10/12期 | difference / installments / missing_payment / missing_items |
| 财务 | 支付结构与期间复核 | orders / payments / items | 分期阈值8/10/12期 | multiple_payment / high_installment / canceled_paid / missing_payment / missing_items |
| 客服 | 投诉时效与转交复核 | complaints / responses / narratives | 转交阈值48/72/96小时 | late / delayed_transfer / date_review |
| 客服 | 投诉响应完整性复核 | complaints / responses / narratives | 无数值参数变化 | missing_public_response / missing_company_response / narrative_followup / missing_link |
| 技术工单 | 问题活动分诊 | issues / activity | 评论阈值3/5/8条 | focus / unassigned_focus / missing_activity |
| 技术工单 | 问题排期与指派复核 | issues / activity | 无数值参数变化 | no_milestone / unassigned / bug_label / missing_activity |

每个题面都要求：范围只限附件；按业务ID关联；原因独立且允许重叠；给出精确 metrics、各组
`reason/condition/count/selectedIds/evidenceIds`；空组也提交；不执行退款、消息、指派、排期或
状态修改。题面不包含工具名、调用顺序、私有答案或预设图结构。

完整48个 train 题面在 `/#evidence` 的六张“正式运行前审阅”卡片中逐项展开。API 会用
`backend/trajectory_assets.py::request_for()` 重新生成题面并核对
`benchmarks/trajectory-review-v2.json` 中的 `requestHash`；任一哈希漂移会失败关闭。
根目录 `test/` 的六个手工问题由同一函数生成，对应每个契约的位置1。

## 数据真实性与字段

- 财务：Olist 匿名真实历史订单。金额仅由公开小数金额确定性转换为分；`purchased_month`
  是真实 `purchased_at` 的前7个字符。
- 客服：CFPB 公开投诉。`company_public_response`、`company_response`、日期和叙述来自缓存的
  源记录；`narrative_excerpt` 是源叙述前1200字符，并记录是否截断。
- 技术工单：Zammad 公开 GitHub Issues，排除 PR；保留状态、里程碑、评论数、更新时间、
  指派人数和标签，不保留作者或负责人身份。

记录按固定哈希划分和排序，场景内任务业务ID不重复；没有改金额、状态、日期、文本或ID，
也没有根据模型输出挑选记录。来源哈希与源字段/派生字段见 `test/.rsi/provenance.json`。

## 内容审计中需要用户明确接受的限制

当前固定哈希 cohort 保持自然数据分布，没有人为注入异常，因此部分输出组是负向控制：

- 48个 train 中有8个任务的 `selectedIds` 为空；模型仍必须提交全部空组和正确总量。
- 财务前三个预检任务的入选项数为0、1、0，财务预检偏重正确汇总和空组处理。
- 当前 train 中 `multiple_payment`、`canceled_paid`、`missing_company_response` 没有正例。
- `missing_link` 和 `missing_activity` 由当前一对一投影保证为空，测试的是“不伪造缺失”，
  不能作为真实缺关联恢复能力的正例证据。
- 客服响应完整性和技术排期任务有较多自然正例；客服时效与技术活动分诊的正例较少但非零。

这不会制造收益或进化，但会限制“多原因正例覆盖”的展示强度。若接受，预检可以按当前资产
开始；若希望每个主要分组都有自然正例，应另建 `trajectory-review-v3`，用预先声明的分层抽样
从同一真实记录池重新冻结，不能修改当前V2或在运行后挑结果。

## 审批后动作

用户明确批准当前题面和自然 cohort 后，只启动9对严格串行预检。预检结束先报告全部成功、
失败、usage、token、模型请求、工具调用、串行延迟、G/M修订与后续使用，再决定是否满足
48对 full 的自动门槛。不会直接跳过预检启动full。
