"""Fetch real public records and build 100 disjoint tasks per scenario."""
import argparse
from collections import defaultdict
import csv
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import zipfile
from .config import ROOT
from .domain import now
from .graph_store import write_private
from .task_definitions import FAMILIES, answer


RAW = ROOT / 'artifacts/taskbank-raw'
OUT = ROOT / 'artifacts/taskbank'
TASKS = ROOT / 'benchmarks/tasks.jsonl'


def fetch(url, path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        body = subprocess.run(['curl', '-L', '-f', '-sS', '--max-time', '45', url], capture_output=True, check=True).stdout
        path.write_bytes(body)
        path.chmod(0o600)
    return path.read_bytes()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def cents(value):
    return int((Decimal(value) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def olist():
    path = RAW / 'olist.zip'
    fetch('https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce', path)
    with zipfile.ZipFile(path) as archive:
        def rows(name):
            entry = next(n for n in archive.namelist() if n.split('/')[-1] == name)
            with archive.open(entry) as stream:
                yield from csv.DictReader(io.TextIOWrapper(stream, encoding='utf-8-sig'))
        customers = {r['customer_id']: r for r in rows('olist_customers_dataset.csv')}
        orders = {}
        for r in rows('olist_orders_dataset.csv'):
            customer = customers[r['customer_id']]
            orders[r['order_id']] = dict(id=r['order_id'], status=r['order_status'], customer_id=r['customer_id'],
                customer_unique_id=customer['customer_unique_id'], customer_state=customer['customer_state'],
                purchased_at=r['order_purchase_timestamp'], delivered_at=r['order_delivered_customer_date'], estimated_at=r['order_estimated_delivery_date'],
                payments=[], items=[], reviews=[])
        for r in rows('olist_order_payments_dataset.csv'):
            orders[r['order_id']]['payments'].append(dict(sequence=int(r['payment_sequential']), method=r['payment_type'], installments=int(r['payment_installments']), amount_cents=cents(r['payment_value'])))
        for r in rows('olist_order_items_dataset.csv'):
            orders[r['order_id']]['items'].append(dict(sequence=int(r['order_item_id']), product_id=r['product_id'], seller_id=r['seller_id'], price_cents=cents(r['price']), freight_cents=cents(r['freight_value'])))
        for r in rows('olist_order_reviews_dataset.csv'):
            orders[r['order_id']]['reviews'].append(dict(id=r['review_id'], score=int(r['review_score']), title=r['review_comment_title'], body=r['review_comment_message']))
    return list(orders.values()), dict(provider='Olist', url='https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce', license='CC BY-NC-SA 4.0', rawSha256={path.name: sha(path.read_bytes())}, note='真实匿名商业记录；任务由本项目设计，原始金额转换为 BRL 分。')


def complaints():
    sources, records = {}, {}
    urls = [
        ('cfpb.json', 'https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/?size=1000&no_aggs=true'),
        ('cfpb-narratives.json', 'https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/?size=1000&no_aggs=true&has_narrative=true'),
        ('cfpb-late.json', 'https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/?size=300&no_aggs=true&has_narrative=true&timely=No'),
    ]
    fields = ['product', 'sub_product', 'issue', 'sub_issue', 'company', 'company_response', 'company_public_response', 'timely', 'submitted_via', 'date_received', 'date_sent_to_company']
    for filename, url in urls:
        body = fetch(url, RAW / filename)
        sources[filename] = sha(body)
        payload = json.loads(body)
        if payload.get('timed_out'):
            raise ValueError('CFPB response incomplete')
        for hit in payload['hits']['hits']:
            r = hit['_source']
            records[str(r['complaint_id'])] = dict(id=str(r['complaint_id']), narrative=r.get('complaint_what_happened') or '', **{f: r.get(f) for f in fields})
    return list(records.values()), dict(provider='CFPB', url='https://www.consumerfinance.gov/data-research/consumer-complaints/', license='CC0 (API metadata)', requests=[u for _, u in urls], rawSha256=sources, note='真实公开投诉记录；消费者叙述未经事实核实，不包含完整客服对话。未保留邮编、地域和用户身份字段。')


def issues():
    records, hashes = {}, {}
    for page in range(1, 11):
        url = f'https://api.github.com/repos/zammad/zammad/issues?state=all&per_page=100&sort=created&direction=desc&page={page}'
        path = RAW / f'zammad-issues-{page}.json'
        body = fetch(url, path)
        hashes[path.name] = sha(body)
        for r in json.loads(body):
            if 'pull_request' in r:
                continue
            records[str(r['number'])] = dict(id=str(r['number']), url=r['html_url'], title=r['title'], body=r.get('body') or '',
                state=r['state'], created_at=r['created_at'], updated_at=r['updated_at'], closed_at=r['closed_at'], comments=r['comments'],
                labels=[label['name'] for label in r['labels']], assignee_count=len(r['assignees']),
                milestone=({'number': r['milestone']['number'], 'title': r['milestone']['title']} if r['milestone'] else None))
        if len(records) >= 500:
            break
    # The all-state feed is dominated by closed issues. Add real open issues so
    # triage families are not made entirely of empty-result cases.
    for page in range(1, 4):
        url = f'https://api.github.com/repos/zammad/zammad/issues?state=open&per_page=100&sort=created&direction=desc&page={page}'
        path = RAW / f'zammad-open-{page}.json'
        body = fetch(url, path)
        hashes[path.name] = sha(body)
        page_rows = json.loads(body)
        for r in page_rows:
            if 'pull_request' in r:
                continue
            records[str(r['number'])] = dict(id=str(r['number']), url=r['html_url'], title=r['title'], body=r.get('body') or '',
                state=r['state'], created_at=r['created_at'], updated_at=r['updated_at'], closed_at=r['closed_at'], comments=r['comments'],
                labels=[label['name'] for label in r['labels']], assignee_count=len(r['assignees']),
                milestone=({'number': r['milestone']['number'], 'title': r['milestone']['title']} if r['milestone'] else None))
        if len(page_rows) < 100:
            break
    return list(records.values()), dict(provider='Zammad GitHub Issues', url='https://github.com/zammad/zammad/issues', license='公开 Issue 内容保留原作者权利；不将仓库代码许可证推定为用户文本许可证', rawSha256=hashes,
        note='真实软件问题记录，已排除 PR；不等同于企业内部客服工单。保留指派人数，不保留作者或负责人身份。')


def partition(record, scenario):
    key = record.get('customer_unique_id') if scenario == 'finance' else record['id']
    bucket = int(sha(key.encode())[:8], 16) % 10
    return 'train' if bucket < 6 else 'validation' if bucket < 8 else 'test'


def build():
    if TASKS.exists():
        raise ValueError('任务库已冻结；请保留当前版本后显式建立新的版本，不能覆盖原基准')
    OUT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(OUT / 'records.sqlite3')
    connection.execute('CREATE TABLE IF NOT EXISTS records (scenario TEXT, id TEXT, payload TEXT, PRIMARY KEY(scenario,id))')
    connection.execute('DELETE FROM records')
    tasks, gold, provenance = [], {}, {}
    as_of = now()
    for scenario, loader in [('finance', olist), ('support', complaints), ('tickets', issues)]:
        records, source = loader()
        print(scenario + ': fetched ' + str(len(records)) + ' real records', flush=True)
        pools = {split: sorted([r for r in records if partition(r, scenario) == split], key=lambda r: sha((scenario + r['id']).encode())) for split in ['train', 'validation', 'test']}
        size = {'finance': 10, 'support': 5, 'tickets': 3}[scenario]
        used = []
        for family, title, instruction, keys in FAMILIES[scenario]:
            for index in range(10):
                split = 'train' if index < 6 else 'validation' if index < 8 else 'test'
                # Include naturally occurring positive cases, without inventing exceptions.
                filtered = family in ['reconciliation', 'installments', 'multiple_payments', 'freight_burden', 'cancelled_payments', 'timeliness', 'narratives', 'followup', 'states', 'oldest', 'unassigned', 'stale', 'no_comments', 'milestones', 'bugs', 'closure']
                if filtered and index not in [3, 8]:
                    positive = next((j for j, r in enumerate(pools[split]) if answer(scenario, family, [r], as_of)['selectedIds']), None)
                    if positive is not None:
                        pools[split].insert(0, pools[split].pop(positive))
                cohort, pools[split] = pools[split][:size], pools[split][size:]
                if len(cohort) != size:
                    raise ValueError('Insufficient real records for disjoint split: ' + scenario + '/' + split)
                task_id = f'{scenario}-{family}-{index+1:02d}'
                expected = answer(scenario, family, cohort, as_of)
                tasks.append(dict(id=task_id, scenario=scenario, family=family, title=title, split=split, asOf=as_of,
                    recordIds=[r['id'] for r in cohort], sourceUrl=source['url'], recordCount=size,
                    task=f'任务 {task_id}：只分析本任务工具可见的 {size} 条记录。{instruction} '
                         f'以 {as_of} 为参考时刻。返回 metrics 字段 {", ".join(keys)}，selectedIds 按要求列出（无需筛选的任务为空数组），并给出逐条证据引用和简短结论。不得补造缺失数据、修改原始记录或发送消息。',
                    acceptance=dict(metricKeys=keys, selectedIdsOrderMatters=expected['ordered'], evidence='引用本任务实际观察过的记录', prose='仅保存，不自动评估全部自然语言质量'),
                    suggestedBudget=dict(modelRequests=24, toolCalls=80)))
                gold[task_id] = expected
                used.extend(cohort)
        for r in used:
            connection.execute('INSERT OR REPLACE INTO records VALUES (?,?,?)', (scenario, r['id'], json.dumps(r, ensure_ascii=False)))
        provenance[scenario] = dict(source, fetchedRecords=len(records), selectedRecords=len(used), tasks=100, families=10,
                                    splits=dict(train=60, validation=20, test=20), referenceHash=sha(json.dumps(used, sort_keys=True, ensure_ascii=False).encode()))
    connection.commit()
    connection.close()
    (OUT / 'records.sqlite3').chmod(0o600)
    manifest = dict(version='public-v1', createdAt=as_of, scenarios=provenance, taskCount=len(tasks),
                    note='真实历史数据上的人工设计任务；未实际调用 LLM 执行 300 次。非企业在线写入工作流，非 IID 成功率样本。')
    write_private(OUT / 'gold.json', gold)
    write_private(ROOT / 'benchmarks/manifest.json', manifest)
    write_private(TASKS, ''.join(json.dumps(t, ensure_ascii=False) + '\n' for t in tasks))
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


def restore():
    """Restore ignored runtime data against committed definitions, failing on source drift."""
    tasks = [json.loads(line) for line in TASKS.read_text().splitlines()]
    manifest = json.loads((ROOT / 'benchmarks/manifest.json').read_text())
    selected, gold = [], {}
    for scenario, loader in [('finance', olist), ('support', complaints), ('tickets', issues)]:
        records, source = loader()
        lookup = {r['id']: r for r in records}
        used = []
        for task in [t for t in tasks if t['scenario'] == scenario]:
            cohort = [lookup[key] for key in task['recordIds']]
            used.extend(cohort)
            gold[task['id']] = answer(scenario, task['family'], cohort, task['asOf'])
        if sha(json.dumps(used, sort_keys=True, ensure_ascii=False).encode()) != manifest['scenarios'][scenario]['referenceHash']:
            raise ValueError('Source records changed; restore the frozen raw cache: ' + scenario)
        selected.extend((scenario, r['id'], json.dumps(r, ensure_ascii=False)) for r in used)
    OUT.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(OUT / 'records.sqlite3') as db:
        db.execute('CREATE TABLE IF NOT EXISTS records (scenario TEXT, id TEXT, payload TEXT, PRIMARY KEY(scenario,id))')
        db.execute('DELETE FROM records')
        db.executemany('INSERT OR REPLACE INTO records VALUES (?,?,?)', selected)
    (OUT / 'records.sqlite3').chmod(0o600)
    write_private(OUT / 'gold.json', gold)
    print('Restored 300 frozen tasks without changing definitions.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    restore() if TASKS.exists() else build()
