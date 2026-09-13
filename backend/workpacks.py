"""Frozen, source-traceable workspace work packs built from public taskbank records.

The files installed by this module are passed through ``WorkspaceManager``'s
normal upload parser.  They do not use the taskbank-only tools at execution
time.  Private validation stays in the local workspace task and is never sent
to the agent or returned by public APIs.
"""
from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
from typing import Any

from .workspace import WorkspaceManager


MANIFEST = Path('benchmarks/workpacks-v1.json')

# A workpack may contain reference tables that are useful for an interactive
# user, but not required to answer this particular frozen request.  The
# declared set drives the bounded graph prefix and private evidence scope; it
# never contains record values, an answer, or a task-specific filter.
WORKFLOW_SOURCES = {
    'finance-reconciliation': ('orders.csv', 'payments.json', 'items.csv'),
    'finance-cancel-installments': ('orders.csv', 'payments.json'),
    'finance-freight-contribution': ('payments.json', 'items.csv'),
    'finance-link-completeness': ('orders.csv', 'payments.json', 'items.csv'),
    'support-health-rollup': ('complaints.csv',),
    'support-escalation-queue': ('complaints.csv', 'narratives.json', 'responses_dates.csv'),
    'support-policy-draft': ('complaints.csv', 'narratives.json', 'responses_dates.csv', 'policy.txt'),
    'support-period-comparison': ('complaints.csv', 'responses_dates.csv'),
    'tickets-triage': ('issues.csv', 'activity.csv'),
    'tickets-blocker-summary': ('issues.csv', 'labels.json', 'issue_body.json'),
    'tickets-activity-followup': ('issues.csv', 'activity.csv'),
    'tickets-export-comparison': ('issues.csv', 'previous_export.csv'),
}

# This is public task specification, not a reference answer.  It declares how
# a business requester names each metric and queue so the Agent can plan the
# required joins and aggregates without guessing from labels such as
# ``priority``.  Per-instance values remain exclusively in private validation.
WORKFLOW_DELIVERY_CONTRACTS = {
    'finance-reconciliation': {
        'requiredSources': ['orders.csv', 'payments.json', 'items.csv'],
        'selectedIds': '仅列出支付总额与商品金额加运费总额相差严格大于 1 分的 order_id。',
        'metrics': {
            'paid_cents': '当前范围内按 order_id 汇总后的全部支付金额之和。',
            'line_cents': '当前范围内按 order_id 汇总后的商品金额加运费金额之和。',
            'mismatch_count': '满足金额差异规则的不同 order_id 数量。',
            'incomplete_count': '缺少支付记录或商品明细的不同 order_id 数量。',
        },
    },
    'finance-cancel-installments': {
        'requiredSources': ['orders.csv', 'payments.json'],
        'selectedIds': '列出 status 为 canceled 且有支付记录，或最大 installments 大于等于 6 的 order_id 并集。',
        'metrics': {
            'cancelled_paid_count': 'status 为 canceled 且至少有一条支付记录的不同 order_id 数量。',
            'cancelled_paid_cents': '这些取消订单的支付金额总和。',
            'installments_ge_6_count': '最大 installments 大于等于 6 的不同 order_id 数量。',
            'priority_order_count': 'selectedIds 中不同 order_id 的数量。',
        },
    },
    'finance-freight-contribution': {
        'requiredSources': ['payments.json', 'items.csv'],
        'selectedIds': '列出按 order_id 汇总后商品金额大于零且运费总额大于等于商品金额 20% 的 order_id。',
        'metrics': {
            'freight_burden_count': 'selectedIds 中不同 order_id 的数量。',
            'freight_burden_cents': 'selectedIds 对应的按订单汇总运费金额之和。',
            'payment_method_count': '当前 payments 资料中非空 method 的不同取值数。',
            'priority_order_count': 'selectedIds 中不同 order_id 的数量；不是订单状态计数。',
        },
    },
    'finance-link-completeness': {
        'requiredSources': ['orders.csv', 'payments.json', 'items.csv'],
        'selectedIds': '仅列出拥有两笔及以上 payment 记录的 order_id。',
        'metrics': {
            'missing_payment_count': '在 orders 中没有任何关联 payment 的不同 order_id 数量。',
            'missing_item_count': '在 orders 中没有任何关联 item 的不同 order_id 数量。',
            'multi_payment_count': '拥有两笔及以上 payment 的不同 order_id 数量。',
            'multi_payment_cents': '这些多笔支付订单的支付金额总和。',
        },
    },
    'support-health-rollup': {
        'requiredSources': ['complaints.csv'],
        'selectedIds': '仅列出 timely 为 No 的 complaint_id。',
        'metrics': {
            'complaint_count': '当前 complaints 记录数。',
            'late_count': 'timely 为 No 的 complaint_id 数量。',
            'channel_count': '非空 submitted_via 的不同取值数。',
            'product_count': '非空 product 的不同取值数。',
        },
    },
    'support-escalation-queue': {
        'requiredSources': ['complaints.csv', 'narratives.json', 'responses_dates.csv'],
        'selectedIds': '列出 timely 为 No 且 narrative 非空，或 date_sent_to_company 减 date_received 严格大于 86400 秒的 complaint_id 并集。',
        'metrics': {
            'late_with_narrative_count': '同时满足 timely 为 No 和 narrative 非空的 complaint_id 数量。',
            'forwarded_over_day_count': '转交时差严格大于 86400 秒的 complaint_id 数量。',
            'priority_complaint_count': 'selectedIds 中不同 complaint_id 的数量。',
            'priority_company_count': 'selectedIds 对应的非空 company 的不同取值数。',
        },
    },
    'support-policy-draft': {
        'requiredSources': ['complaints.csv', 'narratives.json', 'responses_dates.csv', 'policy.txt'],
        'selectedIds': '列出 timely 为 No 或 company_public_response 为空的 complaint_id 并集。',
        'metrics': {
            'narrative_count': 'narrative 非空的 complaint_id 数量。',
            'missing_public_response_count': 'company_public_response 为空的 complaint_id 数量。',
            'followup_count': 'selectedIds 中不同 complaint_id 的数量。',
            'policy_matches': '成功读取并使用当前随附政策资料时为 1，否则为 0。',
        },
        'deterministicFactRecovery': [{
            'tool': 'workspace_aggregate_rows',
            'tableSlots': {'tableId': 'narratives'},
            'arguments': {'operation': 'nonempty_count', 'field': 'narrative'},
            'purpose': '从当前 narratives 表确定性统计非空公开叙述数量。',
        }],
    },
    'support-period-comparison': {
        'requiredSources': ['complaints.csv', 'responses_dates.csv'],
        'selectedIds': '将当前 records 按 date_received 升序排序后分为较早与较晚两期：较早期为前 floor(n/2) 条，较晚期为其余条；仅列出较晚期 timely 为 No 的 complaint_id。',
        'metrics': {
            'prior_count': '较早半段记录数。',
            'current_count': '较晚半段记录数。',
            'prior_late_count': '较早半段 timely 为 No 的记录数。',
            'current_late_count': '较晚半段 timely 为 No 的记录数。',
        },
        'deterministicFactRecovery': [{
            'tool': 'workspace_ordered_partition',
            'tableSlots': {'primaryTableId': 'responses_dates', 'relatedTableId': 'complaints'},
            'arguments': {
                'primaryKey': 'complaint_id', 'sortField': 'date_received', 'relatedKey': 'complaint_id',
                'measures': [
                    {'name': 'prior_late_count', 'segment': 'prior', 'source': 'related',
                     'filters': [{'field': 'timely', 'operator': 'equals', 'value': 'No'}]},
                    {'name': 'current_late_count', 'segment': 'current', 'source': 'related',
                     'filters': [{'field': 'timely', 'operator': 'equals', 'value': 'No'}]},
                ],
                'selectedIds': {'segment': 'current', 'source': 'related',
                                'filters': [{'field': 'timely', 'operator': 'equals', 'value': 'No'}]},
            },
            'purpose': '按当前 date_received 排序并依公开规则确定 prior/current 分段、未及时数量与当前期清单。',
        }],
    },
    'tickets-triage': {
        'requiredSources': ['issues.csv', 'activity.csv'],
        'selectedIds': '列出 state 为 open、assignee_count 为 0，且 milestone 为空或相对参考时刻超过 30 天未更新的 issue_id；按 comments 降序、issue_id 升序。priority 是本次业务队列名称，不是输入字段。',
        'metrics': {
            'priority_issue_count': 'selectedIds 中 issue_id 数量。',
            'stale_priority_count': 'selectedIds 中超过 30 天未更新的 issue_id 数量。',
            'missing_milestone_count': 'selectedIds 中 milestone 为空的 issue_id 数量。',
            'priority_comment_total': 'selectedIds 对应 activity.comments 的总和。',
        },
    },
    'tickets-blocker-summary': {
        'requiredSources': ['issues.csv', 'labels.json', 'issue_body.json'],
        'selectedIds': '列出 state 为 open 且关联 labels 文本包含 bug 的 issue_id。',
        'metrics': {
            'open_bug_count': 'selectedIds 中 issue_id 数量。',
            'body_available_count': 'issue_body 中 body 非空的 issue_id 数量。',
            'blocker_keyword_count': 'issue_body 中 body 包含 blocker 的 issue_id 数量。',
            'priority_issue_count': 'selectedIds 中 issue_id 数量。',
        },
    },
    'tickets-activity-followup': {
        'requiredSources': ['issues.csv', 'activity.csv'],
        'selectedIds': '列出 state 为 open 且相对参考时刻超过 30 天未更新的 issue_id；按 comments 降序、issue_id 升序。',
        'metrics': {
            'open_issue_count': 'state 为 open 的 issue_id 数量。',
            'comment_total': '当前 activity.comments 的总和。',
            'stale_open_count': 'selectedIds 中 issue_id 数量。',
            'followup_issue_count': 'selectedIds 中 issue_id 数量。',
        },
    },
    'tickets-export-comparison': {
        'requiredSources': ['issues.csv', 'previous_export.csv'],
        'selectedIds': '列出相同 issue_id 上 state、assignee_count 或 milestone 任一字段与 previous_export 不同的 issue_id。',
        'metrics': {
            'changed_issue_count': 'selectedIds 中 issue_id 数量。',
            'state_change_count': 'state 发生变化的 issue_id 数量。',
            'assignee_change_count': 'assignee_count 发生变化的 issue_id 数量。',
            'milestone_change_count': 'milestone 发生变化的 issue_id 数量。',
        },
    },
}


def _seconds(value: str | None) -> int | None:
    if not value:
        return None
    return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())


def _csv(rows: list[dict[str, Any]]) -> bytes:
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')


def _finance_values(row: dict[str, Any]) -> tuple[int, int, int, int]:
    paid = sum(item.get('amount_cents', 0) for item in row.get('payments', []))
    price = sum(item.get('price_cents', 0) for item in row.get('items', []))
    freight = sum(item.get('freight_cents', 0) for item in row.get('items', []))
    max_installments = max((item.get('installments', 0) for item in row.get('payments', [])), default=0)
    return paid, price, freight, max_installments


def _finance_prompt(workflow: str) -> tuple[str, list[str]]:
    if workflow == 'finance-reconciliation':
        return ('请完成订单、支付与商品明细的金额核对。所有金额单位都是 BRL 分（cents）；按 order_id 汇总支付、商品与运费金额，差异严格大于 1 分时列入待复核清单。selectedIds 仅列出待复核的 order_id，不要把所有已核对订单放入清单；缺失支付或商品关联单独统计。不要将差异直接定性为欺诈、退款或会计错误。',
                ['paid_cents', 'line_cents', 'mismatch_count', 'incomplete_count'])
    if workflow == 'finance-cancel-installments':
        return ('请形成取消订单与分期支付风险队列。统计 canceled 且已有支付记录的订单及支付金额，并识别最大分期数达到 6 的订单；任一条件命中的 order_id 进入清单。达到 6 是包含式比较，不能缩窄为等于 6。不要执行退款。',
                ['cancelled_paid_count', 'cancelled_paid_cents', 'installments_ge_6_count', 'priority_order_count'])
    if workflow == 'finance-freight-contribution':
        return ('请复核运费异常贡献。识别商品金额大于零且运费达到商品金额 20% 的订单，汇总这些订单的运费金额，并统计当前订单中的支付方式数量。金额单位为 BRL 分；不要把高运费直接解释为客户损失。',
                ['freight_burden_count', 'freight_burden_cents', 'payment_method_count', 'priority_order_count'])
    return ('请核查订单关联完整性与多笔支付。统计缺失支付、缺失商品明细的订单；识别拥有两笔及以上支付记录的订单，并汇总这些订单的支付金额。输出待核查 order_id 清单；多笔支付不等于重复扣款。',
            ['missing_payment_count', 'missing_item_count', 'multi_payment_count', 'multi_payment_cents'])


def _finance_expected(workflow: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    if workflow == 'finance-reconciliation':
        mismatches = [row['id'] for row in records if row.get('payments') and row.get('items') and abs(_finance_values(row)[0] - _finance_values(row)[1] - _finance_values(row)[2]) > 1]
        incomplete = [row for row in records if not row.get('payments') or not row.get('items')]
        return {'metrics': {'paid_cents': sum(_finance_values(row)[0] for row in records), 'line_cents': sum(_finance_values(row)[1] + _finance_values(row)[2] for row in records), 'mismatch_count': len(mismatches), 'incomplete_count': len(incomplete)}, 'selectedIds': sorted(mismatches), 'ordered': False}
    if workflow == 'finance-cancel-installments':
        cancelled = [row for row in records if row.get('status') == 'canceled' and row.get('payments')]
        installments = [row for row in records if _finance_values(row)[3] >= 6]
        selected = sorted({row['id'] for row in cancelled + installments})
        return {'metrics': {'cancelled_paid_count': len(cancelled), 'cancelled_paid_cents': sum(_finance_values(row)[0] for row in cancelled), 'installments_ge_6_count': len(installments), 'priority_order_count': len(selected)}, 'selectedIds': selected, 'ordered': False}
    if workflow == 'finance-freight-contribution':
        selected = [row for row in records if _finance_values(row)[1] > 0 and _finance_values(row)[2] * 5 >= _finance_values(row)[1]]
        methods = {payment.get('method') for row in records for payment in row.get('payments', []) if payment.get('method')}
        return {'metrics': {'freight_burden_count': len(selected), 'freight_burden_cents': sum(_finance_values(row)[2] for row in selected), 'payment_method_count': len(methods), 'priority_order_count': len(selected)}, 'selectedIds': sorted(row['id'] for row in selected), 'ordered': False}
    missing_payment = [row for row in records if not row.get('payments')]
    missing_item = [row for row in records if not row.get('items')]
    multi = [row for row in records if len(row.get('payments', [])) >= 2]
    return {'metrics': {'missing_payment_count': len(missing_payment), 'missing_item_count': len(missing_item), 'multi_payment_count': len(multi), 'multi_payment_cents': sum(_finance_values(row)[0] for row in multi)}, 'selectedIds': sorted(row['id'] for row in multi), 'ordered': False}


def _support_prompt(workflow: str) -> tuple[str, list[str]]:
    if workflow == 'support-health-rollup':
        return ('请汇总投诉渠道、产品和响应健康。统计投诉总量、timely 为 No 的数量、不同渠道数与不同产品数，并将未及时投诉列为待跟进 complaint_id。公开叙述是消费者陈述，不是已核实事实。',
                ['complaint_count', 'late_count', 'channel_count', 'product_count'])
    if workflow == 'support-escalation-queue':
        return ('请生成投诉升级队列。选出 timely 为 No 且公开叙述非空，或从 date_received 到 date_sent_to_company 超过 86400 秒的投诉；统计两个条件与合并后的队列数量。转交时差不是企业响应时长。',
                ['late_with_narrative_count', 'forwarded_over_day_count', 'priority_complaint_count', 'priority_company_count'])
    if workflow == 'support-policy-draft':
        return ('请依据当前投诉资料与随附政策资料形成内部草稿。统计有公开叙述、缺少企业公开回复和需跟进的投诉数量；清单使用 complaint_id。不要发送给消费者，政策资料仅作内部建议依据。',
                ['narrative_count', 'missing_public_response_count', 'followup_count', 'policy_matches'])
    return ('请比较当前工作区中的较早与较晚投诉资料。按 date_received 升序排序，较早期为前 floor(n/2) 条、较晚期为其余条；统计两期投诉量和未及时数量，并列出较晚期间的未及时 complaint_id。不要把观察到的变化解释为因果。',
            ['prior_count', 'current_count', 'prior_late_count', 'current_late_count'])


def _support_expected(workflow: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    late = [row for row in records if row.get('timely') == 'No']
    if workflow == 'support-health-rollup':
        return {'metrics': {'complaint_count': len(records), 'late_count': len(late), 'channel_count': len({row.get('submitted_via') for row in records if row.get('submitted_via')}), 'product_count': len({row.get('product') for row in records if row.get('product')})}, 'selectedIds': sorted(row['id'] for row in late), 'ordered': False}
    if workflow == 'support-escalation-queue':
        late_narrative = [row for row in records if row.get('timely') == 'No' and str(row.get('narrative') or '').strip()]
        forwarded = [row for row in records if (_seconds(row.get('date_sent_to_company')) or 0) - (_seconds(row.get('date_received')) or 0) > 86400]
        selected = sorted({row['id'] for row in late_narrative + forwarded})
        return {'metrics': {'late_with_narrative_count': len(late_narrative), 'forwarded_over_day_count': len(forwarded), 'priority_complaint_count': len(selected), 'priority_company_count': len({row.get('company') for row in records if row['id'] in selected and row.get('company')})}, 'selectedIds': selected, 'ordered': False}
    if workflow == 'support-policy-draft':
        narrative = [row for row in records if str(row.get('narrative') or '').strip()]
        missing = [row for row in records if not str(row.get('company_public_response') or '').strip()]
        followup = sorted({row['id'] for row in late + missing})
        return {'metrics': {'narrative_count': len(narrative), 'missing_public_response_count': len(missing), 'followup_count': len(followup), 'policy_matches': 1}, 'selectedIds': followup, 'ordered': False}
    ordered = sorted(records, key=lambda row: row.get('date_received') or '')
    prior, current = ordered[:len(ordered) // 2], ordered[len(ordered) // 2:]
    return {'metrics': {'prior_count': len(prior), 'current_count': len(current), 'prior_late_count': sum(row.get('timely') == 'No' for row in prior), 'current_late_count': sum(row.get('timely') == 'No' for row in current)}, 'selectedIds': sorted(row['id'] for row in current if row.get('timely') == 'No'), 'ordered': False}


def _tickets_prompt(workflow: str) -> tuple[str, list[str]]:
    if workflow == 'tickets-triage':
        return ('请形成工程分诊清单：选出 open、未分派，且没有 milestone 或相对参考时刻超过 30 天未更新的 issue_id。统计优先项、长期未更新项和缺少 milestone 项；不要把这些条件直接解释为严重度或人员可用性。',
                ['priority_issue_count', 'stale_priority_count', 'missing_milestone_count', 'priority_comment_total'])
    if workflow == 'tickets-blocker-summary':
        return ('请基于标签和正文形成阻塞事项摘要。统计 open 且带 bug 标签的问题、带正文的问题和正文中含 blocker 关键词的问题，并列出 bug 问题 issue_id。正文用于归纳待核查事项，不自动修改工单。',
                ['open_bug_count', 'body_available_count', 'blocker_keyword_count', 'priority_issue_count'])
    if workflow == 'tickets-activity-followup':
        return ('请根据活动记录形成跟进清单。统计 open 问题数量、评论总量以及超过 30 天未更新的 open 问题；清单按评论数降序、并列按 issue_id 升序。',
                ['open_issue_count', 'comment_total', 'stale_open_count', 'followup_issue_count'])
    return ('请比较当前与上一份工程导出，列出状态、负责人数量或里程碑发生变化的 issue_id，并统计变化总数、状态变化数和负责人变化数。上一份导出中标明的变化是工作包注入的测试异常，不能称为公开 GitHub 历史。',
            ['changed_issue_count', 'state_change_count', 'assignee_change_count', 'milestone_change_count'])


def _tickets_expected(workflow: str, records: list[dict[str, Any]], as_of: str, previous: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    reference = _seconds(as_of) or 0
    open_rows = [row for row in records if row.get('state') == 'open']
    stale = lambda row: bool(row.get('updated_at')) and reference - (_seconds(row['updated_at']) or reference) > 30 * 86400
    if workflow == 'tickets-triage':
        priority = [row for row in open_rows if row.get('assignee_count') == 0 and (row.get('milestone') is None or stale(row))]
        priority.sort(key=lambda row: (-int(row.get('comments') or 0), row['id']))
        return {'metrics': {'priority_issue_count': len(priority), 'stale_priority_count': sum(stale(row) for row in priority), 'missing_milestone_count': sum(row.get('milestone') is None for row in priority), 'priority_comment_total': sum(int(row.get('comments') or 0) for row in priority)}, 'selectedIds': [row['id'] for row in priority], 'ordered': True}
    if workflow == 'tickets-blocker-summary':
        bugs = [row for row in open_rows if any('bug' in str(label).lower() for label in row.get('labels', []))]
        body = [row for row in records if str(row.get('body') or '').strip()]
        blocker = [row for row in records if 'blocker' in str(row.get('body') or '').lower()]
        return {'metrics': {'open_bug_count': len(bugs), 'body_available_count': len(body), 'blocker_keyword_count': len(blocker), 'priority_issue_count': len(bugs)}, 'selectedIds': sorted(row['id'] for row in bugs), 'ordered': False}
    if workflow == 'tickets-activity-followup':
        followup = [row for row in open_rows if stale(row)]
        followup.sort(key=lambda row: (-int(row.get('comments') or 0), row['id']))
        return {'metrics': {'open_issue_count': len(open_rows), 'comment_total': sum(int(row.get('comments') or 0) for row in records), 'stale_open_count': len(followup), 'followup_issue_count': len(followup)}, 'selectedIds': [row['id'] for row in followup], 'ordered': True}
    before = {row['id']: row for row in previous or []}
    changed, state, assignee, milestone = [], 0, 0, 0
    for row in records:
        old = before.get(row['id'])
        if not old:
            continue
        fields = {'state': row.get('state') != old.get('state'), 'assignee_count': row.get('assignee_count') != old.get('assignee_count'), 'milestone': row.get('milestone') != old.get('milestone')}
        if any(fields.values()):
            changed.append(row['id'])
            state += fields['state']; assignee += fields['assignee_count']; milestone += fields['milestone']
    return {'metrics': {'changed_issue_count': len(changed), 'state_change_count': state, 'assignee_change_count': assignee, 'milestone_change_count': milestone}, 'selectedIds': sorted(changed), 'ordered': False}


def _prompt(spec: dict[str, Any]) -> tuple[str, list[str]]:
    return {'finance': _finance_prompt, 'support': _support_prompt, 'tickets': _tickets_prompt}[spec['scenario']](spec['id'])


def list_workpacks(bank) -> list[dict[str, Any]]:
    root = Path(bank.root)
    data = json.loads((root / MANIFEST).read_text(encoding='utf-8'))
    packs = []
    for workflow in data['workflows']:
        for position, (source_index, split) in enumerate(zip(data['instanceSourceIndexes'], data['splitByPosition']), start=1):
            source_task_id = f"{workflow['scenario']}-{workflow['sourceFamily']}-{source_index:02d}"
            source = bank.task(source_task_id)
            request, metric_keys = _prompt(workflow)
            delivery_contract = WORKFLOW_DELIVERY_CONTRACTS[workflow['id']]
            pack_id = f"{workflow['id']}-{position:02d}"
            packs.append({'id': pack_id, 'workflowType': workflow['id'], 'scenario': workflow['scenario'], 'title': workflow['title'], 'split': split,
                          'difficulty': workflow['difficulty'][position - 1], 'sourceTaskId': source_task_id, 'sourceUrl': source.get('sourceUrl'),
                          'recordCount': source['recordCount'], 'task': request + ' 返回 metrics 字段 ' + '、'.join(metric_keys) + '，selectedIds 使用当前资料中的业务 ID，并附上本次读取的证据。',
                          'deliveryContract': delivery_contract,
                          'sourceProvenance': {'sourceRecords': {'kind': 'public_historical', 'url': source.get('sourceUrl'), 'taskbankTaskId': source_task_id},
                                               'reorganizedWorkPack': True, 'authoredPolicy': bool(workflow.get('authoredPolicy')), 'injectedAnomaly': bool(workflow.get('injectedAnomaly'))}})
    return packs


def _finance_files(records: list[dict[str, Any]]) -> list[tuple[str, bytes, dict[str, Any]]]:
    orders, payments, items, customers = [], [], [], []
    for row in records:
        orders.append({'order_id': row['id'], 'status': row.get('status'), 'purchased_at': row.get('purchased_at'), 'delivered_at': row.get('delivered_at'), 'estimated_at': row.get('estimated_at')})
        customers.append({'order_id': row['id'], 'customer_id': row.get('customer_id'), 'customer_unique_id': row.get('customer_unique_id'), 'customer_state': row.get('customer_state')})
        payments.extend({'order_id': row['id'], **payment} for payment in row.get('payments', []))
        items.extend({'order_id': row['id'], **item} for item in row.get('items', []))
    provenance = {'kind': 'reorganized_public_records', 'source': 'Olist public historical ecommerce records'}
    return [('orders.csv', _csv(orders), provenance), ('payments.json', json.dumps(payments, ensure_ascii=False).encode('utf-8'), provenance), ('items.csv', _csv(items), provenance), ('customers.csv', _csv(customers), provenance)]


def _support_files(records: list[dict[str, Any]], policy: bool) -> list[tuple[str, bytes, dict[str, Any]]]:
    main = [{'complaint_id': row['id'], 'product': row.get('product'), 'sub_product': row.get('sub_product'), 'issue': row.get('issue'), 'company': row.get('company'), 'submitted_via': row.get('submitted_via'), 'timely': row.get('timely')} for row in records]
    narratives = [{'complaint_id': row['id'], 'narrative': row.get('narrative')} for row in records]
    dates = [{'complaint_id': row['id'], 'date_received': row.get('date_received'), 'date_sent_to_company': row.get('date_sent_to_company'), 'company_response': row.get('company_response'), 'company_public_response': row.get('company_public_response')} for row in records]
    provenance = {'kind': 'reorganized_public_records', 'source': 'CFPB public complaint records'}
    files = [('complaints.csv', _csv(main), provenance), ('narratives.json', json.dumps(narratives, ensure_ascii=False).encode('utf-8'), provenance), ('responses_dates.csv', _csv(dates), provenance)]
    if policy:
        files.append(('policy.txt', '内部政策草稿：公开叙述只能作为消费者陈述引用；缺少企业公开回复时应标记待核查，不向消费者发送自动答复。\n'.encode('utf-8'), {'kind': 'authored_policy', 'source': 'project-authored internal draft'}))
    return files


def _ticket_files(records: list[dict[str, Any]], inject_previous: bool) -> tuple[list[tuple[str, bytes, dict[str, Any]]], list[dict[str, Any]] | None]:
    issues = [{'issue_id': row['id'], 'title': row.get('title'), 'state': row.get('state'), 'created_at': row.get('created_at'), 'updated_at': row.get('updated_at'), 'assignee_count': row.get('assignee_count'), 'milestone': row.get('milestone')} for row in records]
    labels = [{'issue_id': row['id'], 'labels': ', '.join(row.get('labels', []))} for row in records]
    activity = [{'issue_id': row['id'], 'comments': row.get('comments'), 'updated_at': row.get('updated_at'), 'closed_at': row.get('closed_at')} for row in records]
    body = [{'issue_id': row['id'], 'body': row.get('body'), 'url': row.get('url')} for row in records]
    provenance = {'kind': 'reorganized_public_records', 'source': 'zammad/zammad GitHub Issues (public)'}
    files = [('issues.csv', _csv(issues), provenance), ('labels.json', json.dumps(labels, ensure_ascii=False).encode('utf-8'), provenance), ('activity.csv', _csv(activity), provenance), ('issue_body.json', json.dumps(body, ensure_ascii=False).encode('utf-8'), provenance)]
    previous = None
    if inject_previous:
        previous = [dict(row) for row in records]
        if previous:
            previous[0]['state'] = 'closed' if previous[0].get('state') != 'closed' else 'open'
            previous[0]['assignee_count'] = int(previous[0].get('assignee_count') or 0) + 1
            previous[0]['milestone'] = 'injected-previous-milestone'
        previous_rows = [{'issue_id': row['id'], 'state': row.get('state'), 'assignee_count': row.get('assignee_count'), 'milestone': row.get('milestone')} for row in previous]
        files.append(('previous_export.csv', _csv(previous_rows), {'kind': 'injected_anomaly', 'source': 'project-created prior-export delta; not public GitHub history'}))
    return files, previous


def install_workpack(manager: WorkspaceManager, bank, pack_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = next((item for item in list_workpacks(bank) if item['id'] == pack_id), None)
    if not spec:
        raise ValueError('工作包不存在')
    source_task = bank.task(spec['sourceTaskId'])
    records = [bank.record(source_task, record_id) for record_id in source_task['recordIds']]
    workspace = manager.create(spec['scenario'], label=spec['title'], provenance='predefined_workpack')
    workflow = spec['workflowType']
    if spec['scenario'] == 'finance':
        files = _finance_files(records)
        expected = _finance_expected(workflow, records)
    elif spec['scenario'] == 'support':
        files = _support_files(records, bool(spec['sourceProvenance']['authoredPolicy']))
        expected = _support_expected(workflow, records)
    else:
        files, previous = _ticket_files(records, bool(spec['sourceProvenance']['injectedAnomaly']))
        expected = _tickets_expected(workflow, records, source_task.get('asOf', ''), previous)
    for name, content, provenance in files:
        manager.add_source(workspace['id'], name, content, provenance=provenance)
    # ``asOf`` belongs to the public task contract, not private validation.
    # Historical ticket queues use it to make a relative age rule reproducible
    # across hosts and later replays.  Do not substitute the workspace creation
    # timestamp: that would silently change the business condition.
    delivery_contract = dict(spec['deliveryContract'])
    if spec['scenario'] == 'tickets':
        delivery_contract['referenceTime'] = source_task.get('asOf')
    required_sources = WORKFLOW_SOURCES.get(workflow)
    if not required_sources:
        raise RuntimeError('工作包缺少已声明的资料契约')
    task, questions = manager.create_task(workspace['id'], spec['task'], title=spec['title'], split=spec['split'], workpack={
        'workpackId': spec['id'], 'workflowType': workflow, 'difficulty': spec['difficulty'],
        'deliveryContract': delivery_contract, 'sourceProvenance': spec['sourceProvenance']})
    if not task or questions:
        raise RuntimeError('预定义工作包不应要求澄清')
    internal = manager.tasks[task['id']]
    internal['asOf'] = source_task.get('asOf') or internal['asOf']
    # Keep the recovery boundary public and schema-level.  It names only the
    # current table slots for sources already listed in the delivery contract;
    # it never exposes row IDs, expected metrics, or selected records.
    slot_by_table_id = {table_id: slot for slot, table_id in internal['tableBindings'].items()}
    tables = manager.workspace(workspace['id'])['tables'].values()
    slots_by_source = {
        table['sourceName']: slot_by_table_id.get(table['id'])
        for table in tables
    }
    required_slots = [slots_by_source.get(source) for source in required_sources]
    if not all(required_slots):
        raise RuntimeError('工作包资料无法绑定为公开恢复表槽')
    internal['deliveryContract']['requiredTableSlots'] = required_slots
    internal['template'] = f'workpack:{workflow}'
    available_sources = {source['name'] for source in manager.workspace(workspace['id'])['sources']}
    missing_sources = sorted(set(required_sources) - available_sources)
    if missing_sources:
        raise RuntimeError('工作包缺少任务所需资料：' + '、'.join(missing_sources))
    internal['workpackReadSources'] = list(required_sources)
    required = []
    for table in manager.workspace(workspace['id'])['tables'].values():
        if table['sourceName'] in required_sources:
            required.extend(f'workspace:{workspace["id"]}:{row["rowId"]}' for row in table['rows'])
    internal['privateValidation'] = dict(expected, requiredEvidenceIds=sorted(required), requiredSources=list(required_sources))
    manager._persist(manager.workspace(workspace['id']))
    return manager.public_workspace(workspace['id']), manager.public_task(task['id'])
