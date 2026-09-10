"""Short descriptions for intent retrieval and function calling."""
DESCRIPTIONS = {
    'finance_get_order': '查看订单状态和配送时间；返回 status、purchased_at、delivered_at、estimated_at。',
    'finance_get_order_items': '核对商品金额、运费及商家；返回 items，每项含 price_cents、freight_cents、product_id、seller_id。金额为 BRL 分。',
    'finance_get_order_payments': '核对支付金额、支付方式、分期和多笔支付；返回 payments，每项含 amount_cents、method、installments、sequence。金额为 BRL 分。',
    'finance_get_customer': '按客户地区汇总或识别同一客户；返回 customer_state、customer_id、customer_unique_id。',
    'finance_get_order_reviews': '查看订单满意度及评价内容；返回 reviews，含 score、title、body。',
    'support_get_complaint': '分析投诉产品、问题分类、企业和渠道；返回 product、sub_product、issue、sub_issue、company、submitted_via。',
    'support_get_response': '核对企业响应类别和是否及时；返回 company_response、company_public_response、timely。',
    'support_get_dates': '计算投诉接收到转交企业的时差；返回 date_received、date_sent_to_company。',
    'support_get_narrative': '阅读消费者公开叙述或检查叙述是否为空；返回 narrative 文本。',
    'tickets_get_issue': '盘点技术问题状态、创建时间和更新时间；返回 title、state、created_at、updated_at。',
    'tickets_get_labels': '按标签分类、筛选 bug 或检查缺少标签；返回 labels 字符串数组。',
    'tickets_get_assignment': '检查技术工单是否有负责人；返回 assignee_count 指派人数。',
    'tickets_get_milestone': '检查技术工单是否设置里程碑；返回 milestone（编号、标题或 null）。',
    'tickets_get_activity': '统计讨论评论数、筛选无评论或近期活动；返回 comments、updated_at。',
    'tickets_get_resolution': '计算技术问题从创建到关闭的周期；返回 state、created_at、closed_at。',
    'tickets_get_body': '阅读技术问题描述与原始链接；返回 body、url。',
}
