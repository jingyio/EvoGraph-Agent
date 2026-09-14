"""Versioned public-source trajectory tasks and shared manual trial requests."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path

from . import build_taskbank as sources
from .graph_store import write_private
from .workspace import WorkspaceManager


VERSION = 'trajectory-review-v2'
ROLE_LABELS = {'finance': '财务', 'support': '客服', 'tickets': '技术工单'}
GROUPS = {
    'finance': (('reconciliation', '订单金额与分期复核'), ('payment_structure', '支付结构与期间复核')),
    'support': (('transfer_timing', '投诉时效与转交复核'), ('response_coverage', '投诉响应完整性复核')),
    'tickets': (('activity_triage', '问题活动分诊'), ('release_readiness', '问题排期与指派复核')),
}
DELIVERY_CONTRACTS = {
    ('finance', 'reconciliation'): (
        ['order_count', 'paid_cents', 'line_cents', 'difference_count', 'installments_count', 'missing_payment_count', 'missing_items_count'],
        ['difference', 'installments', 'missing_payment', 'missing_items'],
    ),
    ('finance', 'payment_structure'): (
        ['order_count', 'payment_record_count', 'paid_cents', 'period_count', 'multiple_payment_count', 'high_installment_count', 'canceled_paid_count', 'missing_payment_count', 'missing_items_count'],
        ['multiple_payment', 'high_installment', 'canceled_paid', 'missing_payment', 'missing_items'],
    ),
    ('support', 'transfer_timing'): (
        ['complaint_count', 'company_count', 'late_count', 'delayed_transfer_count', 'date_review_count'],
        ['late', 'delayed_transfer', 'date_review'],
    ),
    ('support', 'response_coverage'): (
        ['complaint_count', 'channel_count', 'missing_public_response_count', 'missing_company_response_count', 'narrative_followup_count', 'missing_link_count'],
        ['missing_public_response', 'missing_company_response', 'narrative_followup', 'missing_link'],
    ),
    ('tickets', 'activity_triage'): (
        ['issue_count', 'open_count', 'closed_count', 'open_comment_total', 'focus_count', 'unassigned_focus_count', 'missing_activity_count'],
        ['focus', 'unassigned_focus', 'missing_activity'],
    ),
    ('tickets', 'release_readiness'): (
        ['issue_count', 'open_count', 'no_milestone_count', 'unassigned_count', 'bug_label_count', 'missing_activity_count'],
        ['no_milestone', 'unassigned', 'bug_label', 'missing_activity'],
    ),
}


def task_plan():
    """Controller labels stay outside tasks and graph matching."""
    rows = []
    for role, groups in GROUPS.items():
        for group_index, (group, label) in enumerate(groups):
            for split, count in [('train', 8), ('validation', 1), ('test', 1)]:
                for position in range(1, count + 1):
                    rows.append({'scenario': role, 'group': group, 'groupLabel': label, 'split': split,
                                 'position': position,
                                 'precheck': group_index == 0 and split == 'train' and position <= 3})
    return rows


def _output_contract(request, metric_keys, group_names):
    return (request.strip() + '\n输出 metrics 精确包含以下键：' + '、'.join(metric_keys) +
            '。groups 使用以下 name，逐组给 reason、condition、count、selectedIds、evidenceIds：' +
            '、'.join(group_names) + '。selectedIds 是各组业务ID的去重并集，所有ID使用字符串；空组也必须提交。')


def request_for(role, group, position=1):
    if role == 'finance' and group == 'reconciliation':
        delta = [5, 10, 5, 10, 5, 10, 10, 5][(position - 1) % 8]
        terms = [8, 10, 8, 12, 10, 8, 12, 8][(position - 1) % 8]
        request = f'''请根据本次订单、支付和商品明细做财务复核简报，范围只限附件。
按 order_id 汇总支付金额、商品金额及运费，保留多笔支付和多条商品明细。分别列出支付总额与商品加运费总额相差严格大于{delta}分的订单、最大分期数达到{terms}期的订单、缺支付记录和缺商品明细的订单。原因允许重叠，缺失一侧不能当作0完成对账。
给出订单数、可见支付总额、商品加运费总额、各组数量、业务ID和证据。金额显示为BRL并注明原始字段为分。给内部复核建议，不执行退款或改账。'''
        return _output_contract(request, *DELIVERY_CONTRACTS[(role, group)])
    if role == 'finance' and group == 'payment_structure':
        terms = [8, 10, 12, 8, 10, 12, 8, 10][(position - 1) % 8]
        request = f'''请根据本次订单和支付明细制作支付结构与期间复核简报，范围只限附件。
按 order_id 关联订单与支付，按 purchased_month 汇总订单数。分别列出存在多笔支付的订单、最大分期数达到{terms}期的订单、状态为 canceled 且确有支付记录的订单，以及缺支付或缺商品明细的订单。各原因独立并允许重叠。
给出订单数、支付记录数、可见支付总额、期间数、各组数量、业务ID和证据。说明公开历史资料的范围和金额单位，不执行退款或改账。'''
        return _output_contract(request, *DELIVERY_CONTRACTS[(role, group)])
    if role == 'support' and group == 'transfer_timing':
        hours = [48, 72, 48, 72, 48, 96, 72, 48][(position - 1) % 8]
        request = f'''请根据本次投诉和企业响应资料整理客服主管内部简报，按 complaint_id 关联，范围只限附件。
分别列出 timely 为 No 的投诉、从 date_received 到 date_sent_to_company 严格超过{hours}小时的投诉，以及日期缺失、日期倒置或缺响应关联的待核查投诉。原因允许重叠，恰好{hours}小时不入选。
给出投诉总数、不同公司数、各组数量、业务ID、公司、产品、响应状态和证据。缺失信息不能写成已解决，不发送客户消息。'''
        return _output_contract(request, *DELIVERY_CONTRACTS[(role, group)])
    if role == 'support' and group == 'response_coverage':
        request = '''请根据本次公开投诉、企业响应和消费者叙述摘录，整理内部响应完整性复核简报，按 complaint_id 关联，范围只限附件。
分别列出缺少 company_public_response 的投诉、缺少 company_response 的投诉，以及有消费者叙述摘录但缺少公开响应、需要人工跟进的投诉。缺关联记录单列待核查。消费者叙述只能标为消费者陈述，不能当成已核实企业事实。
给出投诉总数、渠道数、各组数量、业务ID、公司、产品、渠道和证据。可给内部跟进建议，不发送消息或承诺处理结果。'''
        return _output_contract(request, *DELIVERY_CONTRACTS[(role, group)])
    if role == 'tickets' and group == 'activity_triage':
        comments = [3, 5, 3, 5, 8, 5, 3, 8][(position - 1) % 8]
        request = f'''请根据本次公开软件问题与活动资料生成研发负责人内部跟进简报，按 issue_id 关联，范围只限附件。
将 state 为 open 且 comments 达到{comments}条的问题列入重点跟进；再单列其中尚未指派的问题，以及缺活动关联或评论数缺失的待核查项。已关闭问题不进入重点清单，评论多不等于已确认严重故障。
给出全部问题数、open和closed数量、open问题评论总数、各组数量、业务ID、标题、链接、里程碑和证据。只生成简报，不修改工单。'''
        return _output_contract(request, *DELIVERY_CONTRACTS[(role, group)])
    if role == 'tickets' and group == 'release_readiness':
        request = '''请根据本次公开软件问题与活动资料制作排期和指派复核简报，按 issue_id 关联，范围只限附件。
对 open 问题分别列出未指定 milestone、未指派负责人、标签包含 bug 的事项；缺活动关联或关键字段缺失的单列待核查。三类原因独立并允许重叠，不根据标签或评论数推断故障严重程度。
给出问题总数、open数量、各组数量、业务ID、标题、链接、标签、更新时间和证据。只提供内部交接建议，不修改指派、里程碑或状态。'''
        return _output_contract(request, *DELIVERY_CONTRACTS[(role, group)])
    raise ValueError(f'unknown trajectory task contract: {role}/{group}')


def _hours(start, end):
    try:
        return (datetime.fromisoformat(end.replace('Z', '+00:00')) - datetime.fromisoformat(start.replace('Z', '+00:00'))).total_seconds() / 3600
    except (AttributeError, TypeError, ValueError):
        return None


def material(role, group, records, position):
    request = request_for(role, group, position)
    if role == 'finance':
        tables = {
            'orders': [{'order_id': r['id'], 'status': r['status'], 'purchased_at': r['purchased_at'],
                        'purchased_month': (r['purchased_at'] or '')[:7]} for r in records],
            'payments': [dict(order_id=r['id'], **p) for r in records for p in r['payments']],
            'items': [{'order_id': r['id'], 'sequence': p['sequence'], 'price_cents': p['price_cents'],
                       'freight_cents': p['freight_cents']} for r in records for p in r['items']],
        }
        paid_total = sum(p['amount_cents'] for r in records for p in r['payments'])
        if group == 'reconciliation':
            delta = [5, 10, 5, 10, 5, 10, 10, 5][(position - 1) % 8]
            terms = [8, 10, 8, 12, 10, 8, 12, 8][(position - 1) % 8]
            line_total = sum(p['price_cents'] + p['freight_cents'] for r in records for p in r['items'])
            groups = {
                'difference': [r['id'] for r in records if r['payments'] and r['items'] and abs(sum(p['amount_cents'] for p in r['payments']) - sum(p['price_cents'] + p['freight_cents'] for p in r['items'])) > delta],
                'installments': [r['id'] for r in records if r['payments'] and max(p['installments'] for p in r['payments']) >= terms],
                'missing_payment': [r['id'] for r in records if not r['payments']],
                'missing_items': [r['id'] for r in records if not r['items']],
            }
            metrics = {'order_count': len(records), 'paid_cents': paid_total, 'line_cents': line_total,
                       **{name + '_count': len(ids) for name, ids in groups.items()}}
        else:
            terms = [8, 10, 12, 8, 10, 12, 8, 10][(position - 1) % 8]
            groups = {
                'multiple_payment': [r['id'] for r in records if len(r['payments']) >= 2],
                'high_installment': [r['id'] for r in records if r['payments'] and max(p['installments'] for p in r['payments']) >= terms],
                'canceled_paid': [r['id'] for r in records if r['status'] == 'canceled' and r['payments']],
                'missing_payment': [r['id'] for r in records if not r['payments']],
                'missing_items': [r['id'] for r in records if not r['items']],
            }
            metrics = {'order_count': len(records), 'payment_record_count': sum(len(r['payments']) for r in records),
                       'paid_cents': paid_total, 'period_count': len({(r['purchased_at'] or '')[:7] for r in records}),
                       **{name + '_count': len(ids) for name, ids in groups.items()}}
    elif role == 'support':
        tables = {
            'complaints': [{'complaint_id': r['id'], 'company': r['company'], 'product': r['product'], 'issue': r['issue'],
                            'timely': r['timely'], 'submitted_via': r['submitted_via']} for r in records],
            'responses': [{'complaint_id': r['id'], 'company_public_response': r['company_public_response'],
                           'company_response': r['company_response'], 'date_received': r['date_received'],
                           'date_sent_to_company': r['date_sent_to_company']} for r in records],
            'narratives': [{'complaint_id': r['id'], 'narrative_excerpt': r['narrative'][:1200],
                            'excerpt_truncated': len(r['narrative']) > 1200} for r in records],
        }
        if group == 'transfer_timing':
            limit = [48, 72, 48, 72, 48, 96, 72, 48][(position - 1) % 8]
            deltas = {r['id']: _hours(r['date_received'], r['date_sent_to_company']) for r in records}
            groups = {'late': [r['id'] for r in records if r['timely'] == 'No'],
                      'delayed_transfer': [r['id'] for r in records if deltas[r['id']] is not None and deltas[r['id']] > limit],
                      'date_review': [r['id'] for r in records if deltas[r['id']] is None or deltas[r['id']] < 0]}
            metrics = {'complaint_count': len(records), 'company_count': len({r['company'] for r in records}),
                       **{name + '_count': len(ids) for name, ids in groups.items()}}
        else:
            groups = {'missing_public_response': [r['id'] for r in records if not (r['company_public_response'] or '').strip()],
                      'missing_company_response': [r['id'] for r in records if not (r['company_response'] or '').strip()],
                      'narrative_followup': [r['id'] for r in records if r['narrative'].strip() and not (r['company_public_response'] or '').strip()],
                      'missing_link': []}
            metrics = {'complaint_count': len(records), 'channel_count': len({r['submitted_via'] for r in records}),
                       **{name + '_count': len(ids) for name, ids in groups.items()}}
    else:
        tables = {'issues': [{'issue_id': r['id'], 'title': r['title'], 'state': r['state'],
                              'milestone': (r['milestone'] or {}).get('title') or '', 'url': r['url']} for r in records],
                  'activity': [{'issue_id': r['id'], 'comments': r['comments'], 'assignee_count': r['assignee_count'],
                                'updated_at': r['updated_at'], 'labels': ', '.join(r['labels'])} for r in records]}
        if group == 'activity_triage':
            limit = [3, 5, 3, 5, 8, 5, 3, 8][(position - 1) % 8]
            focus = [r['id'] for r in records if r['state'] == 'open' and r['comments'] >= limit]
            groups = {'focus': focus, 'unassigned_focus': [r['id'] for r in records if r['id'] in focus and r['assignee_count'] == 0], 'missing_activity': []}
            metrics = {'issue_count': len(records), 'open_count': sum(r['state'] == 'open' for r in records),
                       'closed_count': sum(r['state'] == 'closed' for r in records),
                       'open_comment_total': sum(r['comments'] for r in records if r['state'] == 'open'),
                       **{name + '_count': len(ids) for name, ids in groups.items()}}
        else:
            groups = {'no_milestone': [r['id'] for r in records if r['state'] == 'open' and not r['milestone']],
                      'unassigned': [r['id'] for r in records if r['state'] == 'open' and r['assignee_count'] == 0],
                      'bug_label': [r['id'] for r in records if r['state'] == 'open' and any(label.lower() == 'bug' for label in r['labels'])],
                      'missing_activity': []}
            metrics = {'issue_count': len(records), 'open_count': sum(r['state'] == 'open' for r in records),
                       **{name + '_count': len(ids) for name, ids in groups.items()}}
    expected = {'metrics': metrics, 'groups': {k: sorted(v) for k, v in groups.items()},
                'selectedIds': sorted({item for values in groups.values() for item in values})}
    return tables, request, expected


def build(root):
    root = Path(root)
    out = root / 'artifacts' / VERSION
    if (out / 'manifest.json').exists():
        manifest = json.loads((out / 'manifest.json').read_text())
        write_private(root / 'benchmarks' / f'{VERSION}.json', manifest)
        return manifest
    original = sources.fetch
    sources.fetch = lambda url, path: path.read_bytes()
    manifest = {'version': VERSION, 'taskDesignVersion': 'shared-six-contracts-v1',
                'taskDesign': 'six project-authored business contracts over public historical records; no injected failures',
                'splitPolicy': 'train only learning; validation/test frozen and unrun',
                'protocol': {'trainPairs': 48, 'validationPairs': 6, 'testPairs': 6, 'precheckPairs': 9,
                             'organization': 'three scenarios x two business contracts x eight train arrivals'},
                'tasks': [], 'sources': {}}
    try:
        loaded = {}
        for role, loader in [('finance', sources.olist), ('support', sources.complaints), ('tickets', sources.issues)]:
            loaded[role], manifest['sources'][role] = loader()
        offsets = Counter()
        for spec in task_plan():
            role, split = spec['scenario'], spec['split']
            pool = [r for r in loaded[role] if sources.partition(r, role) == split]
            pool.sort(key=lambda r: hashlib.sha256((VERSION + role + split + r['id']).encode()).hexdigest())
            size = 12 if role == 'finance' else 10
            start = offsets[(role, split)] * size
            records = pool[start:start + size]
            offsets[(role, split)] += 1
            if len(records) != size:
                raise ValueError(f'insufficient disjoint source records: {role}/{split}')
            tables, request, expected = material(role, spec['group'], records, spec['position'])
            key = f"{role}-{spec['group']}-{split}-{spec['position']:02d}"
            directory = out / key
            write_private(directory / 'inputs.json', tables)
            write_private(directory / 'request.txt', request)
            write_private(directory / 'private.json', expected)
            features = {'primaryRecords': size, 'rowsByTable': {k: len(v) for k, v in tables.items()},
                        'tables': len(tables), 'deliveryGroups': len(expected['groups']),
                        'textCharacters': len(json.dumps(tables, ensure_ascii=False)),
                        'unit': 'BRL cents' if role == 'finance' else 'records',
                        'association': 'one-to-many' if role == 'finance' else 'one-to-one',
                        'missingCells': sum(v in (None, '') for rows in tables.values() for row in rows for v in row.values())}
            manifest['tasks'].append({**spec, 'id': key, 'title': ROLE_LABELS[role] + spec['groupLabel'] + f" {spec['position']}",
                                      'recordIds': [r['id'] for r in records], 'features': features,
                                      'requestHash': hashlib.sha256(request.encode()).hexdigest(),
                                      'inputHash': hashlib.sha256((directory / 'inputs.json').read_bytes()).hexdigest()})
        write_private(out / 'manifest.json', manifest)
        write_private(root / 'benchmarks' / f'{VERSION}.json', manifest)
        return manifest
    finally:
        sources.fetch = original


def install(manager: WorkspaceManager, root, spec):
    directory = Path(root) / 'artifacts' / VERSION / spec['id']
    workspace = manager.create(spec['scenario'], label=spec['title'], provenance='public_historical_trajectory_v2')
    manager.add_source(workspace['id'], 'inputs.json', (directory / 'inputs.json').read_bytes(),
                       provenance={'source': ROLE_LABELS[spec['scenario']] + '公开历史资料；任务由项目编写'})
    task, questions = manager.create_task(workspace['id'], (directory / 'request.txt').read_text(), title=spec['title'], split=spec['split'])
    if questions:
        raise ValueError(questions)
    internal = manager.tasks[task['id']]
    required = sorted(f'workspace:{workspace["id"]}:{row["rowId"]}' for table in manager.workspace(workspace['id'])['tables'].values() for row in table['rows'])
    internal['publicScopeEvidenceIds'] = required
    internal['privateValidation'] = dict(json.loads((directory / 'private.json').read_text()), requiredEvidenceIds=required)
    metric_keys, group_names = DELIVERY_CONTRACTS[(spec['scenario'], spec['group'])]
    internal['deliveryContract'] = {
        'requiredTableSlots': list(internal['tableBindings']),
        'requiredMetricKeys': list(metric_keys),
        'requiredGroupNames': list(group_names),
        'evidenceScope': 'current attachment rows; no outside records',
    }
    manager._persist(manager.workspace(workspace['id']))
    return workspace, manager.public_task(task['id'])


if __name__ == '__main__':
    from .config import ROOT
    result = build(ROOT)
    print(json.dumps({'version': result['version'], 'tasks': len(result['tasks']),
                      'splits': dict(Counter(task['split'] for task in result['tasks']))}, ensure_ascii=False))
