"""Task families and deterministic fact checks over public historical records."""
from collections import Counter, defaultdict
from datetime import datetime


FAMILIES = {
    'finance': [
        ('payment_totals', '支付金额盘点', '汇总支付、商品和运费金额，单位为 BRL 分。', ['paid_cents', 'items_cents', 'freight_cents']),
        ('reconciliation', '订单金额核对', '识别支付金额与商品加运费金额相差超过 1 分的订单。缺失支付或商品记录的订单单独计数，不判定为差额异常。', ['mismatch_count', 'incomplete_count']),
        ('installments', '分期支付盘点', '找出至少一条支付记录分期数达到 6 的订单，汇总这些订单的支付总金额；不将其解释为未偿债务。', ['order_count', 'paid_cents']),
        ('multiple_payments', '多笔支付核查', '找出包含多条支付记录的订单，汇总这些订单的支付总金额；不将多笔支付直接认定为重复扣款。', ['order_count', 'paid_cents']),
        ('freight_burden', '运费占比核查', '找出商品金额大于零且运费达到商品金额 20% 的订单，汇总其运费。', ['order_count', 'freight_cents']),
        ('cancelled_payments', '取消订单支付核查', '找出状态为 canceled 且存在支付记录的订单，统计数量和支付金额；不推断已退款或应退款。', ['order_count', 'paid_cents']),
        ('payment_methods', '支付方式统计', '按支付方式汇总支付记录数量与金额。', ['records_by_method', 'cents_by_method']),
        ('value_ranking', '高金额订单核查', '按订单支付总金额降序列出前三个订单；并列按订单 ID 升序。汇总前三个订单支付金额。', ['top_paid_cents']),
        ('state_payments', '地区支付统计', '按客户所在州汇总订单支付金额及订单数量。', ['orders_by_state', 'cents_by_state']),
        ('delivery_payments', '交付状态支付核查', '按订单状态统计数量和支付金额，列出 delivered 订单；不把该口径当作会计收入确认。', ['orders_by_status', 'cents_by_status']),
    ],
    'support': [
        ('products', '投诉产品分布', '按投诉记录的 product 字段统计数量。', ['counts']),
        ('issues', '投诉问题分布', '按投诉记录的 issue 字段统计数量。', ['counts']),
        ('responses', '企业响应类型', '按 company_response 字段统计数量，不把响应分类视为投诉事实已核实。', ['counts']),
        ('timeliness', '响应及时性核查', '列出 timely 为 No 的投诉，分别统计 Yes、No 和其他或缺失值。', ['timely_count', 'late_count', 'unknown_count']),
        ('channels', '投诉渠道统计', '按 submitted_via 字段统计投诉数量。', ['counts']),
        ('forwarding', '投诉转交时差', '计算 date_received 到 date_sent_to_company 的秒数总和及有效记录数；列出时差超过 86400 秒的投诉。这是转交时差，不是企业响应时长。', ['valid_count', 'total_seconds']),
        ('narratives', '投诉叙述覆盖', '列出有非空公开投诉叙述的记录，统计有叙述与无叙述数量。叙述为消费者陈述，未经事实核实。', ['with_narrative', 'without_narrative']),
        ('companies', '企业投诉分布', '按 company 字段统计投诉数量，不做市场份额归一化或行业总体排名。', ['counts']),
        ('followup', '跟进清单生成', '按本任务规则：选取 timely=No 且有公开叙述的投诉，统计数量；该规则不是监管风险定级。', ['followup_count']),
        ('recent', '近期投诉摘要', '按 date_received 降序列出最新三条投诉，并列按投诉 ID 升序，统计涉及企业数量。', ['company_count']),
    ],
    'tickets': [
        ('states', '技术工单状态盘点', '统计 open 与 closed 数量，列出 open 工单。', ['open_count', 'closed_count']),
        ('labels', '标签覆盖核查', '统计每个标签出现次数，列出没有标签的工单；一个工单可有多个标签。', ['label_counts']),
        ('unassigned', '未分派问题筛选', '列出 open 且 assignee_count=0 的工单，统计数量。不据此推断员工可用性。', ['unassigned_count']),
        ('stale', '长期未更新问题', '以任务 asOf 为准，列出 open 且 updated_at 已超过 30 天的工单，统计数量。这是本任务筛选规则，不是项目 SLA。', ['stale_count']),
        ('no_comments', '无评论问题筛选', '列出 open 且 comments=0 的工单，统计数量；不能推断其他渠道是否已回复。', ['no_comments_count']),
        ('oldest', '最早未关闭问题', '按 created_at 升序列出最早的三条 open 工单，并列按工单 ID 升序，统计结果数量。', ['selected_count']),
        ('milestones', '里程碑覆盖核查', '列出 open 且没有 milestone 的工单，统计数量。', ['missing_milestone_count']),
        ('closure', '问题关闭周期统计', '计算有 closed_at 的 closed 工单从创建到关闭的秒数总和及数量；不推断是否解决了客户问题。列出这些 closed 工单。', ['closed_count', 'total_seconds']),
        ('bugs', '缺陷标签分诊', '列出 open 且至少一个标签名包含 bug（不区分大小写）的工单，统计数量；不自行判断无标签工单是否是缺陷。', ['bug_count']),
        ('activity', '问题讨论活跃度', '汇总评论总数及 open 工单评论总数，列出评论数最高的三条，按评论数降序并列 ID 升序。', ['comments_total', 'open_comments']),
    ],
}


def seconds(value):
    return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())


def amounts(row):
    return (sum(p['amount_cents'] for p in row['payments']), sum(i['price_cents'] for i in row['items']), sum(i['freight_cents'] for i in row['items']))


def answer(scenario, family, records, as_of):
    selected, metrics, ordered = [], {}, False
    if scenario == 'finance':
        sums = {r['id']: amounts(r) for r in records}
        if family == 'payment_totals':
            metrics = dict(zip(['paid_cents', 'items_cents', 'freight_cents'], [sum(s[i] for s in sums.values()) for i in range(3)]))
        elif family == 'reconciliation':
            selected = [r['id'] for r in records if r['payments'] and r['items'] and abs(sums[r['id']][0] - sum(sums[r['id']][1:])) > 1]
            metrics = dict(mismatch_count=len(selected), incomplete_count=sum(not r['payments'] or not r['items'] for r in records))
        elif family in ['installments', 'multiple_payments', 'freight_burden', 'cancelled_payments']:
            for row in records:
                paid, price, freight = sums[row['id']]
                keep = {'installments': any(p['installments'] >= 6 for p in row['payments']),
                        'multiple_payments': len(row['payments']) > 1, 'freight_burden': price > 0 and freight * 5 >= price,
                        'cancelled_payments': row['status'] == 'canceled' and bool(row['payments'])}[family]
                if keep:
                    selected.append(row['id'])
            key = 'freight_cents' if family == 'freight_burden' else 'paid_cents'
            metrics = {'order_count': len(selected), key: sum(sums[i][2 if key == 'freight_cents' else 0] for i in selected)}
        elif family == 'payment_methods':
            counts, values = Counter(), defaultdict(int)
            for row in records:
                for p in row['payments']:
                    counts[p['method']] += 1
                    values[p['method']] += p['amount_cents']
            metrics = dict(records_by_method=dict(counts), cents_by_method=dict(values))
        elif family == 'value_ranking':
            selected = [r['id'] for r in sorted(records, key=lambda r: (-sums[r['id']][0], r['id']))[:3]]
            metrics, ordered = dict(top_paid_cents=sum(sums[i][0] for i in selected)), True
        else:
            field = 'customer_state' if family == 'state_payments' else 'status'
            counts, values = Counter(), defaultdict(int)
            for row in records:
                counts[row[field]] += 1
                values[row[field]] += sums[row['id']][0]
            suffix = 'state' if family == 'state_payments' else 'status'
            metrics = {'orders_by_' + suffix: dict(counts), 'cents_by_' + suffix: dict(values)}
            if family == 'delivery_payments':
                selected = [r['id'] for r in records if r['status'] == 'delivered']
    elif scenario == 'support':
        fields = dict(products='product', issues='issue', responses='company_response', channels='submitted_via', companies='company')
        if family in fields:
            metrics = dict(counts=dict(Counter(r.get(fields[family]) or '(missing)' for r in records)))
        elif family == 'timeliness':
            selected = [r['id'] for r in records if r['timely'] == 'No']
            metrics = dict(timely_count=sum(r['timely'] == 'Yes' for r in records), late_count=len(selected), unknown_count=sum(r['timely'] not in ['Yes', 'No'] for r in records))
        elif family == 'forwarding':
            spans = {r['id']: seconds(r['date_sent_to_company']) - seconds(r['date_received']) for r in records if r['date_sent_to_company'] and r['date_received']}
            selected = [i for i, span in spans.items() if span > 86400]
            metrics = dict(valid_count=len(spans), total_seconds=sum(spans.values()))
        elif family == 'narratives':
            selected = [r['id'] for r in records if r['narrative'].strip()]
            metrics = dict(with_narrative=len(selected), without_narrative=len(records) - len(selected))
        elif family == 'followup':
            selected = [r['id'] for r in records if r['timely'] == 'No' and r['narrative'].strip()]
            metrics = dict(followup_count=len(selected))
        else:
            rows = sorted(records, key=lambda r: (-seconds(r['date_received']), r['id']))[:3]
            selected, metrics, ordered = [r['id'] for r in rows], dict(company_count=len({r['company'] for r in rows})), True
    else:
        opened = [r for r in records if r['state'] == 'open']
        if family == 'states':
            selected = [r['id'] for r in opened]
            metrics = dict(open_count=len(opened), closed_count=sum(r['state'] == 'closed' for r in records))
        elif family == 'labels':
            selected = [r['id'] for r in records if not r['labels']]
            metrics = dict(label_counts=dict(Counter(label for r in records for label in r['labels'])))
        elif family in ['unassigned', 'stale', 'no_comments', 'milestones', 'bugs']:
            for row in opened:
                keep = {'unassigned': row['assignee_count'] == 0, 'stale': seconds(as_of) - seconds(row['updated_at']) > 30 * 86400,
                        'no_comments': row['comments'] == 0, 'milestones': row['milestone'] is None, 'bugs': any('bug' in label.lower() for label in row['labels'])}[family]
                if keep:
                    selected.append(row['id'])
            key = dict(unassigned='unassigned_count', stale='stale_count', no_comments='no_comments_count', milestones='missing_milestone_count', bugs='bug_count')[family]
            metrics = {key: len(selected)}
        elif family == 'oldest':
            selected = [r['id'] for r in sorted(opened, key=lambda r: (r['created_at'], r['id']))[:3]]
            metrics, ordered = dict(selected_count=len(selected)), True
        elif family == 'closure':
            closed = [r for r in records if r['state'] == 'closed' and r['closed_at']]
            selected = [r['id'] for r in closed]
            metrics = dict(closed_count=len(closed), total_seconds=sum(seconds(r['closed_at']) - seconds(r['created_at']) for r in closed))
        else:
            selected = [r['id'] for r in sorted(records, key=lambda r: (-r['comments'], r['id']))[:3]]
            metrics, ordered = dict(comments_total=sum(r['comments'] for r in records), open_comments=sum(r['comments'] for r in opened)), True
    return dict(metrics=metrics, selectedIds=selected if ordered else sorted(selected), ordered=ordered)
