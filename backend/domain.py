from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRESETS = json.loads((ROOT / 'data/presets.json').read_text())


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def clock(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def seed(variant='base'):
    if variant not in ['base', 'changed', 'exception']:
        raise ValueError('Unknown snapshot')
    return json.loads((ROOT / 'data' / f'{variant}.json').read_text())


def record(items, key):
    for item in items:
        if item['id'] == key:
            return item
    raise ValueError(f'Record not found: {key}')


def invoice_balance(world, key):
    return record(world['invoices'], key)['amountCents'] - sum(a['amountCents'] for a in world['allocations'] if a['invoiceId'] == key)


def payment_balance(world, key):
    return record(world['payments'], key)['amountCents'] - sum(a['amountCents'] for a in world['allocations'] if a['paymentId'] == key)


def preview_match(world, key):
    payment = record(world['payments'], key)
    duplicates = [p for p in world['payments'] if p['bankRef'] == payment['bankRef']]
    def no(reason, evidence):
        return {'eligible': False, 'reason': reason, 'evidenceIds': evidence, 'allocations': []}
    if len(duplicates) > 1:
        return no('duplicate_bank_reference', [p['id'] for p in duplicates])
    if not payment['invoiceRefs']:
        return no('missing_invoice_reference', [key])
    if any(not any(i['id'] == ref and i['customerId'] == payment['customerId'] and i['currency'] == payment['currency']
                   for i in world['invoices']) for ref in payment['invoiceRefs']):
        return no('customer_currency_or_reference_mismatch', [key])
    available = payment_balance(world, key)
    allocations = []
    for ref in dict.fromkeys(payment['invoiceRefs']):
        amount = min(available, invoice_balance(world, ref))
        if amount > 0:
            allocations.append({'invoiceId': ref, 'amountCents': amount})
            available -= amount
    return {'eligible': bool(allocations), 'reason': 'verified_references' if allocations else 'no_remaining_balance',
            'evidenceIds': [key] + payment['invoiceRefs'], 'allocations': allocations}


def overdue_invoices(world):
    return [dict(item, outstandingCents=invoice_balance(world, item['id'])) for item in world['invoices']
            if item['dueDate'] < world['asOf'][:10] and invoice_balance(world, item['id']) > 0]


def active_tickets(world):
    return [t for t in world['tickets'] if t['status'] != 'closed']


def money(cents):
    return f'¥{cents / 100:,.2f}'


def make_report(run, summary):
    world, scenario = run['state'], run['request']['scenario']
    if scenario == 'finance':
        total = sum(i['amountCents'] for i in world['invoices'])
        allocated = sum(i['amountCents'] for i in world['allocations'])
        metrics = [{'label': '应收原始金额', 'value': money(total)}, {'label': '已分配回款', 'value': money(allocated), 'note': '沙箱匹配，不代表新增回款'},
                   {'label': '剩余应收', 'value': money(total - allocated)}, {'label': '已登记异常', 'value': str(len(world['cases']))}]
        rows = [[i['id'], i['customer'], money(i['amountCents']), money(i['amountCents'] - invoice_balance(world, i['id'])), money(invoice_balance(world, i['id'])),
                 '已匹配' if invoice_balance(world, i['id']) == 0 else '逾期未结清' if i['dueDate'] < world['asOf'][:10] else '未结清'] for i in world['invoices']]
        findings = [f"{c['id']} · {c['summary']} [{', '.join(c['evidenceIds'])}]" for c in world['cases']]
        findings.append(f"共有 {sum(invoice_balance(world, i['id']) > 0 for i in world['invoices'])} 张发票尚未结清。异常金额不等同于已确认损失；重复流水记录不合并计作新增回款。")
        title, columns = '回款核对 · 运营简报', ['发票', '客户', '原始金额', '已分配', '剩余应收', '状态']
    else:
        active = active_tickets(world)
        overdue = [t for t in active if clock(t['dueAt']) < clock(world['asOf'])]
        metrics = [{'label': '未关闭工单', 'value': str(len(active))}, {'label': '已分派', 'value': str(sum(bool(t['ownerId']) for t in active))},
                   {'label': 'SLA 已超时', 'value': str(len(overdue)), 'note': '分派后仍然计为超时'}, {'label': '回复草稿', 'value': str(len(world['drafts'])), 'note': '已保存，未发送'}]
        rows = [[t['id'], t['subject'], t['priority'], next((a['name'] for a in world['agents'] if a['id'] == t['ownerId']), '待分派'),
                 '已超时' if t in overdue else '时限内', '已保存' if any(d['ticketId'] == t['id'] for d in world['drafts']) else '未生成'] for t in active]
        findings = [f"{e['ticketId']} · {e['reason']}" for e in world['escalations']]
        findings.append(f'当前 {len(overdue)} 个工单超时；分派和回复草稿不代表问题已经解决。')
        title, columns = '工单巡检 · 服务简报', ['工单', '主题', '优先级', '负责人', 'SLA', '草稿']
    return {'title': title, 'summary': summary, 'metrics': metrics, 'columns': columns, 'rows': rows,
            'findings': findings, 'source': run['request']['source'], 'createdAt': now()}


def markdown(run):
    report = run.get('report')
    text = f"# {report['title'] if report else 'Agent 执行记录'}\n\n运行：{run['id']}\n\n模式：{run['request']['mode']} / {run['request'].get('strategy', 'react')}；数据源：{run['request']['source']}；状态：{run['status']}\n\n"
    if report:
        def cell(value):
            return str(value).replace('|', '\\|').replace('\n', ' ')
        text += report['summary'] + '\n\n'
        text += '\n'.join(f"- {m['label']}：{m['value']}" for m in report['metrics']) + '\n\n'
        text += '| ' + ' | '.join(map(cell, report['columns'])) + ' |\n| ' + ' | '.join('---' for _ in report['columns']) + ' |\n'
        text += '\n'.join('| ' + ' | '.join(map(cell, row)) + ' |' for row in report['rows']) + '\n\n'
        text += '\n'.join('- ' + finding for finding in report['findings']) + '\n\n'
    else:
        text += run.get('finalText', run.get('error', '尚未生成报告')) + '\n\n'
    text += '执行计量：' + json.dumps(run['metrics'], ensure_ascii=False) + '\n\n'
    if run.get('modelSettings'):
        text += '模型设置：' + json.dumps(run['modelSettings']) + '\n\n'
    if run.get('graph'):
        text += '图执行与学习（学习成本单列）：' + json.dumps(run['graph'], ensure_ascii=False) + '\n\n'
    if run.get('evaluation'):
        text += '任务结果校验：' + json.dumps(run['evaluation'], ensure_ascii=False) + '\n'
    return text
