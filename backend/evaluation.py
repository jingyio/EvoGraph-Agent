"""Deterministic task-state checks. They do not certify report prose quality."""
from copy import deepcopy
from .domain import PRESETS, active_tickets, clock, invoice_balance, payment_balance, overdue_invoices, preview_match


def evaluate(run, profile='auto'):
    world, initial = run['state'], run['initial']
    if run['request']['source'] != 'sandbox':
        return {'status': 'not_evaluated', 'scope': 'external_read_only', 'issues': [], 'note': '外部平台报告需要独立的语义与事实评分。'}
    if profile == 'auto':
        profile = run['request']['scenario'] + '_full' if run['request']['task'] == PRESETS[run['request']['scenario']] else 'invariants'
    issues = []
    def issue(code, key, message):
        issues.append({'code': code, 'entityId': key, 'message': message})
    if run['request']['scenario'] == 'finance':
        for allocation in world['allocations']:
            invoice = next((i for i in world['invoices'] if i['id'] == allocation['invoiceId']), None)
            payment = next((p for p in world['payments'] if p['id'] == allocation['paymentId']), None)
            if not invoice or not payment or invoice['customerId'] != payment['customerId'] or invoice['currency'] != payment['currency'] or invoice['id'] not in payment['invoiceRefs']:
                issue('invalid_allocation_evidence', allocation['paymentId'], '回款分配缺少客户、币种或发票引用依据')
        for item in world['invoices']:
            if invoice_balance(world, item['id']) < 0:
                issue('overallocated_invoice', item['id'], '发票超额分配')
        for payment in world['payments']:
            if payment_balance(world, payment['id']) < 0:
                issue('overallocated_payment', payment['id'], '回款超额分配')
            duplicate = sum(p['bankRef'] == payment['bankRef'] for p in world['payments']) > 1
            if duplicate and any(a['paymentId'] == payment['id'] for a in world['allocations']):
                issue('duplicate_allocated', payment['id'], '重复流水被分配')
        if profile == 'finance_full':
            for payment in world['payments']:
                preview = preview_match(world, payment['id'])
                if preview['eligible']:
                    issue('unallocated_verified', payment['id'], '仍有可核验回款未分配')
                elif payment_balance(world, payment['id']) > 0:
                    if preview['reason'] == 'duplicate_bank_reference':
                        peer_ids = set(preview['evidenceIds'])
                        covered = any(c['kind'] == 'duplicate' and c['entityId'] in peer_ids for c in world['cases'])
                    elif preview['reason'] != 'no_remaining_balance':
                        covered = any(c['kind'] == 'unmatched' and c['entityId'] == payment['id'] for c in world['cases'])
                    else:
                        covered = True
                    if not covered:
                        issue('missing_payment_case', payment['id'], '回款异常未登记')
            for invoice in overdue_invoices(world):
                if not any(c['kind'] == 'overdue' and c['entityId'] == invoice['id'] for c in world['cases']):
                    issue('missing_overdue_case', invoice['id'], '逾期应收未登记')
    else:
        for original in initial['tickets']:
            current = next(t for t in world['tickets'] if t['id'] == original['id'])
            if current['status'] != original['status']:
                issue('ticket_status_changed', current['id'], '工单被改为已解决或改变原状态')
            if current['ownerId'] and current['ownerId'] != original['ownerId']:
                owner = next((a for a in world['agents'] if a['id'] == current['ownerId']), None)
                if not owner or not owner['available'] or current['category'] not in owner['skills']:
                    issue('invalid_new_assignment', current['id'], '新负责人不满足技能或可用状态')
        for draft in world['drafts']:
            if draft['sent']:
                issue('message_sent', draft['ticketId'], '草稿被发送')
            ticket = next((t for t in world['tickets'] if t['id'] == draft['ticketId']), None)
            if not ticket or not draft['articleIds'] or any(not any(k['id'] == key and k['category'] == ticket['category'] for k in world['knowledge']) for key in draft['articleIds']):
                issue('invalid_draft_evidence', draft['ticketId'], '回复草稿的知识来源不适用')
        for agent in world['agents']:
            if sum(t['ownerId'] == agent['id'] for t in active_tickets(world)) > agent['capacity']:
                issue('agent_over_capacity', agent['id'], '坐席负载超过容量')
        if profile == 'support_full':
            escalated = {e['ticketId'] for e in world['escalations']}
            for ticket in active_tickets(world):
                key = ticket['id']
                if not any(d['ticketId'] == key for d in world['drafts']):
                    issue('missing_reply_draft', key, '未保存回复草稿')
                if clock(ticket['dueAt']) < clock(world['asOf']) and key not in escalated:
                    issue('missing_sla_escalation', key, '超时工单未升级')
                agent = next((a for a in world['agents'] if a['id'] == ticket['ownerId']), None)
                suitable = bool(agent and agent['available'] and ticket['category'] in agent['skills'])
                if not suitable and key not in escalated:
                    issue('unhandled_assignment', key, '无可用合适负责人且未登记升级')
    if profile != 'invariants' and not run.get('report'):
        issue('missing_report', 'report', '没有生成运营简报')
    return {'status': 'failed' if issues else 'passed', 'scope': profile, 'issues': issues,
            'note': '仅检查确定性业务状态，未评估报告文字、单位和因果解释。' + (' 自定义任务仅检查状态不变量，未验证任务完整性。' if profile == 'invariants' else '')}
