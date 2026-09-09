"""Explicit offline program, not a model or RSI learning source."""
import json
from uuid import uuid4


def action(name, **args):
    return name, args


def finance_plan():
    _, _, payments = yield [action('get_business_clock'), action('list_invoices'), action('list_payments')]
    duplicates = set()
    for payment in payments:
        preview, = yield [action('preview_payment_match', paymentId=payment['id'])]
        if preview['eligible']:
            yield [action('allocate_payment', paymentId=payment['id'], allocations=preview['allocations'])]
        elif preview['reason'] == 'duplicate_bank_reference':
            if payment['bankRef'] in duplicates:
                continue
            duplicates.add(payment['bankRef'])
            yield [action('create_finance_case', kind='duplicate', entityId=payment['id'], evidenceIds=preview['evidenceIds'], summary=payment['bankRef'] + ' 出现重复记录，核实前不分配。')]
        elif preview['reason'] != 'no_remaining_balance':
            yield [action('create_finance_case', kind='unmatched', entityId=payment['id'], evidenceIds=preview['evidenceIds'], summary=payment['id'] + ' 缺少可核验发票引用，待确认用途。')]
    overdue, = yield [action('list_overdue_invoices')]
    if overdue:
        yield [action('create_finance_case', kind='overdue', entityId=i['id'], evidenceIds=[i['id']], summary=i['id'] + ' 超过到期日，仍有余额待跟进。') for i in overdue]
    yield [action('publish_report', summary='已完成有依据的回款分配，登记重复流水、未匹配回款及剩余逾期应收。')]
    return '离线固定流程结束，本次未调用 LLM。'


def support_plan():
    tickets, agents, _ = yield [action('list_tickets', scope='active'), action('list_agents'), action('get_business_clock')]
    risks, = yield [action('get_sla_risks')]
    rank = {'urgent': 0, 'high': 1, 'normal': 2, 'low': 3}
    for ticket in sorted(tickets, key=lambda t: (rank[t['priority']], t['dueAt'])):
        if not ticket['ownerId']:
            available = [a for a in agents if a['available'] and ticket['category'] in a['skills'] and a['activeCount'] < a['capacity']]
            available.sort(key=lambda a: (a['activeCount'], a['id']))
            if available:
                agent = available[0]
                yield [action('assign_ticket', ticketId=ticket['id'], agentId=agent['id'], expectedVersion=ticket['version'])]
                agent['activeCount'] += 1
            else:
                yield [action('escalate_ticket', ticketId=ticket['id'], reason='没有具备技能和剩余容量的可用坐席。')]
        articles, = yield [action('search_knowledge', category=ticket['category'], query=ticket['subject'])]
        if articles:
            yield [action('save_reply_draft', ticketId=ticket['id'], body='您好，已记录问题。' + articles[0]['body'] + ' 目前尚未确认问题解决。', articleIds=[articles[0]['id']])]
    if any(r['overdue'] for r in risks):
        yield [action('escalate_ticket', ticketId=r['ticketId'], reason='超过业务快照时刻的 SLA 截止时间。') for r in risks if r['overdue']]
    yield [action('publish_report', summary='已按技能容量分派，保存带知识来源的回复草稿，登记超时升级。没有发送消息或关闭工单。')]
    return '离线固定流程结束，本次未调用 LLM。'


class FixtureProvider:
    kind, model = 'fixture', None

    def __init__(self, scenario):
        self.plan = finance_plan() if scenario == 'finance' else support_plan()
        self.started = False

    async def complete(self, messages, tools):
        observations = []
        if self.started:
            for message in reversed(messages):
                if message['role'] != 'tool':
                    break
                observation = json.loads(message['content'])
                if not observation['ok']:
                    raise ValueError('离线流程工具失败：' + observation['error'])
                observations.insert(0, observation['result'])
        try:
            operations = self.plan.send(observations) if self.started else next(self.plan)
            self.started = True
        except StopIteration as done:
            return {'message': {'role': 'assistant', 'content': done.value}, 'finishReason': 'stop'}
        return {'message': {'role': 'assistant', 'content': '离线固定流程步骤', 'tool_calls': [
            {'id': 'fixture_' + str(uuid4()), 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}} for name, args in operations]}, 'finishReason': 'tool_calls'}
