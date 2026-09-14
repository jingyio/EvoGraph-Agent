"""Export fresh public-source inputs; never run agents or update experience."""
import hashlib
import json
from pathlib import Path
import sqlite3

from backend import build_taskbank as sources
from backend.trajectory_assets import request_for


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'test'


def cached_only(url, path):
    return path.read_bytes()


sources.fetch = cached_only
db = sqlite3.connect(f'file:{ROOT}/artifacts/taskbank/records.sqlite3?mode=ro', uri=True)
excluded = {role: {row[0] for row in db.execute('SELECT id FROM records WHERE scenario = ?', (role,))}
            for role in ('finance', 'support', 'tickets')}
db.close()
for path in (ROOT / 'artifacts/workspaces').glob('**/tables.json'):
    tables = json.loads(path.read_text())
    for table in tables.values():
        for row in table.get('rows', []):
            values = row.get('values', {})
            for role, field in [('finance', 'order_id'), ('support', 'complaint_id'), ('tickets', 'issue_id')]:
                if values.get(field) is not None:
                    excluded[role].add(str(values[field]))


def tables_for(role, rows):
    if role == 'finance':
        return {
            'orders': [dict(order_id=r['id'], status=r['status'], purchased_at=r['purchased_at'],
                            purchased_month=(r['purchased_at'] or '')[:7]) for r in rows],
            'payments': [dict(order_id=r['id'], **p) for r in rows for p in r['payments']],
            'items': [dict(order_id=r['id'], sequence=p['sequence'], price_cents=p['price_cents'],
                           freight_cents=p['freight_cents']) for r in rows for p in r['items']],
        }
    if role == 'support':
        return {
            'complaints': [dict(complaint_id=r['id'], company=r['company'], product=r['product'],
                                issue=r['issue'], submitted_via=r['submitted_via'], timely=r['timely']) for r in rows],
            'responses': [dict(complaint_id=r['id'], date_received=r['date_received'],
                               date_sent_to_company=r['date_sent_to_company'], company_response=r['company_response'],
                               company_public_response=r['company_public_response']) for r in rows],
            'narratives': [dict(complaint_id=r['id'], narrative_excerpt=r['narrative'][:1200],
                                excerpt_truncated=len(r['narrative']) > 1200) for r in rows],
        }
    return {
        'issues': [dict(issue_id=r['id'], title=r['title'], state=r['state'],
                        milestone=(r['milestone'] or {}).get('title'), url=r['url']) for r in rows],
        'activity': [dict(issue_id=r['id'], comments=r['comments'], updated_at=r['updated_at'],
                          assignee_count=r['assignee_count'], labels=', '.join(r['labels'])) for r in rows],
    }


books, audit = [], {}
for role, folder, loader in [('finance', '财务', sources.olist), ('support', '客服', sources.complaints),
                             ('tickets', '技术工单', sources.issues)]:
    records, provenance = loader()
    eligible = [r for r in records if r['id'] not in excluded[role] and sources.partition(r, role) == 'train']
    eligible.sort(key=lambda r: hashlib.sha256(('manual-inputs-2026-09-14:' + role + ':' + r['id']).encode()).hexdigest())
    if len(eligible) < 16:
        raise ValueError(f'Not enough previously unused train-source records: {role}: {len(eligible)}')
    selected = eligible[:16]
    projections = {
        'finance': {'sourceFields': ['id', 'status', 'purchased_at', 'payments', 'items'],
                    'derivedFields': {'purchased_month': 'first seven characters of source purchased_at'}},
        'support': {'sourceFields': ['id', 'company', 'product', 'issue', 'submitted_via', 'timely',
                                     'date_received', 'date_sent_to_company', 'company_response',
                                     'company_public_response', 'narrative'],
                    'derivedFields': {'narrative_excerpt': 'first 1200 source characters',
                                      'excerpt_truncated': 'source narrative length greater than 1200'}},
        'tickets': {'sourceFields': ['id', 'title', 'state', 'milestone', 'url', 'comments',
                                     'updated_at', 'assignee_count', 'labels'], 'derivedFields': {}},
    }
    audit[role] = dict(source=provenance, projection=projections[role], excludedRecordCount=len(excluded[role]),
                       eligibleCount=len(eligible), recordIds=[r['id'] for r in selected],
                       baseCount=12, extendedCount=16, selection='fixed hash ordering; no outcome-based selection')
    for count, filename in [(12, '输入附件.xlsx'), (16, '输入附件-扩展版.xlsx')]:
        books.append(dict(path=f'{folder}/{filename}', tables=tables_for(role, selected[:count])))
    print(role, 'fresh records', len(selected), 'eligible', len(eligible))

(OUT / '.rsi/data.json').write_text(json.dumps(books, ensure_ascii=False), encoding='utf-8')
(OUT / '.rsi/provenance.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
manual = {'finance': ('财务', 'reconciliation', 'payment_structure'),
          'support': ('客服', 'transfer_timing', 'response_coverage'),
          'tickets': ('技术工单', 'activity_triage', 'release_readiness')}
for role, (folder, primary, secondary) in manual.items():
    (OUT / folder / '问题.txt').write_text(request_for(role, primary, 1) + '\n', encoding='utf-8')
    (OUT / folder / '问题-小幅变化.txt').write_text(request_for(role, secondary, 1) + '\n', encoding='utf-8')
