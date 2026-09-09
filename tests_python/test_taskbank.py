from copy import deepcopy
import json
import sqlite3
import pytest
import httpx
from backend.app import create_app
from backend.service import RunService
from backend.task_definitions import answer
from backend.taskbank import TaskBank, compare
from backend.build_taskbank import cents, partition


def order(key, payments, status='delivered'):
    return dict(id=key, status=status, customer_unique_id='customer-' + key, customer_state='SP',
                payments=[dict(amount_cents=n, installments=1, method='card') for n in payments],
                items=[dict(price_cents=1000, freight_cents=100)], reviews=[])


def test_finance_gold_does_not_double_count_or_treat_missing_data_as_mismatch():
    rows = [order('a', [600, 500]), order('b', [1101]), order('c', [900]), order('d', [])]
    result = answer('finance', 'payment_totals', rows, '')
    assert result['metrics'] == dict(paid_cents=3101, items_cents=4000, freight_cents=400)
    result = answer('finance', 'reconciliation', rows, '')
    assert result['selectedIds'] == ['c'] and result['metrics'] == dict(mismatch_count=1, incomplete_count=1)
    result = answer('finance', 'multiple_payments', rows, '')
    assert result['selectedIds'] == ['a'] and result['metrics']['paid_cents'] == 1100
    assert cents('12.34') == 1234
    assert partition(dict(id='order-1', customer_unique_id='same'), 'finance') == partition(dict(id='order-2', customer_unique_id='same'), 'finance')


def test_support_unknown_timeliness_and_transfer_latency():
    rows = [dict(id='1', timely='No', date_received='2024-01-01T00:00:00Z', date_sent_to_company='2024-01-03T00:00:00Z'),
            dict(id='2', timely=None, date_received='2024-01-01T00:00:00Z', date_sent_to_company=None)]
    assert answer('support', 'timeliness', rows, '')['metrics'] == dict(timely_count=0, late_count=1, unknown_count=1)
    result = answer('support', 'forwarding', rows, '')
    assert result['metrics'] == dict(valid_count=1, total_seconds=172800) and result['selectedIds'] == ['1']


def test_ticket_stale_boundary_and_closed_issue_exclusion():
    row = dict(id='1', state='open', updated_at='2024-01-01T00:00:00Z', labels=['bug'], comments=0, milestone=None, assignee_count=0)
    assert answer('tickets', 'stale', [row], '2024-01-31T00:00:00Z')['selectedIds'] == []
    assert answer('tickets', 'stale', [row], '2024-01-31T00:00:01Z')['selectedIds'] == ['1']
    assert answer('tickets', 'bugs', [dict(row, state='closed')], '')['selectedIds'] == []


def small_bank(root):
    (root / 'benchmarks').mkdir()
    (root / 'artifacts/taskbank').mkdir(parents=True)
    task = dict(id='test-task', scenario='finance', family='payment_totals', asOf='', recordCount=1, recordIds=['a'], acceptance={'metricKeys': ['paid_cents', 'items_cents', 'freight_cents']})
    (root / 'benchmarks/tasks.jsonl').write_text(json.dumps(task) + '\n')
    (root / 'benchmarks/manifest.json').write_text('{}')
    expected = dict(metrics=dict(paid_cents=1100, items_cents=1000, freight_cents=100), selectedIds=[], ordered=False)
    (root / 'artifacts/taskbank/gold.json').write_text(json.dumps({'test-task': expected}))
    with sqlite3.connect(root / 'artifacts/taskbank/records.sqlite3') as db:
        db.execute('CREATE TABLE records (scenario TEXT, id TEXT, payload TEXT)')
        for row in [order('a', [1100]), order('outside', [999999])]:
            db.execute('INSERT INTO records VALUES (?,?,?)', ('finance', row['id'], json.dumps(row)))
    bank = TaskBank(root)
    bank.load()
    return bank, task, expected


async def test_scoped_tools_schema_evidence_and_no_gold_leak(tmp_path):
    bank, task, expected = small_bank(tmp_path)
    session = bank.start(task['id'])
    result = await bank.call(session['id'], 'finance_get_order_payments', {'orderId': 'outside'})
    assert result['ok'] is False and 'outside this task' in result['error']
    assert '999999' not in json.dumps(result)
    result = await bank.call(session['id'], 'finance_list_orders', {'page': True, 'pageSize': 10})
    assert not result['ok']
    result = await bank.call(session['id'], 'finance_list_orders', {'page': 1, 'pageSize': 10})
    assert result['result']['records'][0]['id'] == 'a' and not result['result']['mayHaveMore']
    assert '1100' not in json.dumps(result)
    report = dict(metrics=expected['metrics'], selectedIds=[], evidenceIds=['finance:a'], summary='unit test')
    other_session = bank.start(task['id'])
    assert (await bank.call(other_session['id'], 'finance_publish_report', report))['evaluation']['status'] == 'failed'
    assert (await bank.call(session['id'], 'finance_publish_report', report))['evaluation']['status'] == 'passed'
    before = bank.record(task, 'a')
    report['metrics'] = dict(paid_cents=1, items_cents=1000, freight_cents=100)
    bad = await bank.call(session['id'], 'finance_publish_report', report)
    assert bad['evaluation']['status'] == 'failed' and '1100' not in json.dumps(bad)
    assert bank.record(task, 'a') == before
    assert bank.task(task['id']) == task and 'metrics' not in task
    with pytest.raises(ValueError):
        await bank.call(session['id'], 'tickets_get_body', {'issueId': 'a'})


def test_scoring_rejects_bool_duplicates_and_wrong_rank_order(tmp_path):
    bank, task, expected = small_bank(tmp_path)
    expected = dict(metrics={'count': 1}, selectedIds=['b', 'a'], ordered=True)
    task['recordIds'] = ['a', 'b']
    submitted = dict(metrics={'count': True}, selectedIds=['a', 'b'], evidenceIds=['finance:a', 'finance:b'])
    result = compare(task, expected, submitted, set(submitted['evidenceIds']))
    assert 'metric:count' in result['issues'] and 'selectedIds' in result['issues']
    submitted.update(metrics={'count': 1}, selectedIds=['b', 'a'])
    assert compare(task, expected, submitted, set(submitted['evidenceIds']))['status'] == 'passed'
    submitted['selectedIds'] = ['b', 'a', 'a']
    assert compare(task, expected, submitted, set(submitted['evidenceIds']))['status'] == 'failed'


async def test_http_catalog_and_tool_session_hide_answers(tmp_path, monkeypatch):
    bank, task, _ = small_bank(tmp_path)
    monkeypatch.setattr('backend.app.TaskBank', lambda: bank)
    app = create_app(RunService(tmp_path / 'runs'))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get('/api/taskbank/manifest')).json()['ready']
            listed = (await client.get('/api/taskbank/tasks?scenario=finance')).json()
            assert len(listed) == 1 and 'gold' not in listed[0] and 'metrics' not in listed[0]
            tools = (await client.get('/api/taskbank/tasks/test-task/tools')).json()
            assert len(tools) == 11 and '1100' not in json.dumps(tools)
            session = (await client.post('/api/taskbank/sessions', json={'taskId': task['id']})).json()
            response = await client.post('/api/taskbank/sessions/' + session['id'] + '/call', json={'tool': 'finance_get_order_payments', 'arguments': {'orderId': 'a'}})
            assert response.status_code == 200 and response.json()['result']['payments'][0]['amount_cents'] == 1100
            assert (await client.get('/api/taskbank/tasks?scenario=unknown')).status_code == 400
