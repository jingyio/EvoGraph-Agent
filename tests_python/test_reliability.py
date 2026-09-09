import asyncio
from copy import deepcopy
import pytest
import httpx
from backend.app import create_app
from backend.domain import now
from backend.reliability import ReliabilityService, ReliabilityRequest, summarize_run, totals
from backend.runtime import create_run
from backend.service import RunService
from backend.tools import sandbox_tools


def test_error_attribution_includes_invalid_json_and_guard_rejections():
    run = create_run(dict(scenario='finance', source='sandbox', mode='live', task='test'))
    run.update(status='limited', evaluation={'status': 'failed'}, negativeMotif={'guardHits': 1})
    run['events'] = [
        dict(type='action', seq=1, title='list_payments', detail={'executor': 'graph', 'arguments': '{}'}),
        dict(type='observation', seq=2, detail={'ok': True}),
        dict(type='action', seq=3, title='create_finance_case', detail={'executor': 'model', 'arguments': 'INVALID JSON'}),
        dict(type='observation', seq=4, detail={'ok': False, 'error': 'bad json'}),
        dict(type='action', seq=5, title='create_finance_case', detail={'executor': 'model', 'arguments': '{}'}),
        dict(type='motif', seq=6, detail={}),
        dict(type='observation', seq=7, detail={'ok': False, 'error': 'guard rejection'}),
    ]
    row = summarize_run(run, sandbox_tools('finance'))
    assert row['counters']['graph'] == dict(attempts=1, errors=0)
    assert row['counters']['model'] == dict(attempts=2, errors=2)
    assert len(row['errors']) == 2 and row['guardHits'] == 1 and not row['statePassed']


def fake_service(tmp_path):
    class Provider:
        model, settings = 'test-only', {'enableThinking': False, 'parallelToolCalls': True}
    runs = RunService(tmp_path, Provider)
    graph = dict(id='seed', version=1, sourceRunId='source', nodes=[dict(id='n1', tool='list_payments')])
    runs.graphs.select = lambda request, tools: {'graph': graph}
    runs.negative.select = lambda request, tools: [dict(id='negative')]
    return runs, graph


async def test_pairing_freezes_experience_and_preserves_failure_denominators(tmp_path, monkeypatch):
    runs, graph = fake_service(tmp_path)
    captured = []
    async def controlled(run, provider, tools, **kwargs):
        captured.append((deepcopy(run['request']), deepcopy(kwargs['graph'])))
        negative = run['request']['negativeMotifs']
        run.update(status='limited' if len(captured) == 2 else 'completed', finishedAt=now(), evaluation={'status': 'passed'})
        run['metrics'].update(modelRequests=2, toolCalls=1, toolErrors=0 if negative else 1,
                              inputTokens=10, outputTokens=5, usageComplete=len(captured) != 2)
    monkeypatch.setattr('backend.reliability.execute_run', controlled)
    service = ReliabilityService(runs)
    item = await service.start(ReliabilityRequest(rounds=3))
    graph['nodes'][0]['tool'] = 'changed-after-start'
    await service.tasks[item['id']]
    assert item['status'] == 'completed' and len(item['rows']) == 9
    assert [r['arm'] for r in item['rows'][:3]] == ['react', 'graph', 'graph_negative']
    assert [r['arm'] for r in item['rows'][3:6]] == ['graph', 'graph_negative', 'react']
    for index in range(1, 4):
        assert len({r['initialHash'] for r in item['rows'] if r['round'] == index}) == 1
    assert all(g['nodes'][0]['tool'] == 'list_payments' for _, g in captured if g)
    assert all((req['strategy'] == 'graph') == bool(g) for req, g in captured)
    assert not runs.graphs.graphs and not runs.negative.motifs
    summary = totals(item)
    assert summary['graph']['runs'] == 3 and summary['graph']['statePassed'] == 2
    assert summary['graph']['usageComplete'] is False
    assert summary['react']['runsWithToolErrors'] == 3 and summary['graph_negative']['runsWithToolErrors'] == 0
    restored = ReliabilityService(runs)
    restored.restore()
    assert restored.items[item['id']]['totals'] == summary


async def test_cancellation_and_missing_experience(tmp_path):
    runs, _ = fake_service(tmp_path)
    service = ReliabilityService(runs)
    item = await service.start(ReliabilityRequest(rounds=1))
    service.tasks[item['id']].cancel()
    await service.shutdown()
    await asyncio.sleep(0)
    assert item['status'] == 'cancelled' and not item['rows'] and not service.tasks
    runs.graphs.select = lambda r, t: {'graph': None}
    with pytest.raises(ValueError, match='读取图'):
        await service.start(ReliabilityRequest())


async def test_running_cancellation_preserves_partial_result(tmp_path, monkeypatch):
    runs, _ = fake_service(tmp_path)
    service = ReliabilityService(runs)
    entered = asyncio.Event()
    async def slow(run, provider, tools, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            run.update(status='cancelled', finishedAt=now(), evaluation={'status': 'failed'})
    monkeypatch.setattr('backend.reliability.execute_run', slow)
    item = await service.start(ReliabilityRequest(rounds=2))
    await entered.wait()
    await service.shutdown()
    assert item['status'] == 'cancelled' and len(item['rows']) == 1
    assert item['totals']['react']['runs'] == 1 and item['totals']['react']['statePassed'] == 0


async def test_api_exports_and_rejects_overlapping_execution(tmp_path, monkeypatch):
    runs, _ = fake_service(tmp_path)
    entered = asyncio.Event()
    async def slow(run, provider, tools, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            run.update(status='cancelled', finishedAt=now(), evaluation={'status': 'failed'})
    monkeypatch.setattr('backend.reliability.execute_run', slow)
    app = create_app(runs)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/reliability', json={'rounds': 1})
            assert response.status_code == 202
            key = response.json()['id']
            await entered.wait()
            assert (await client.post('/api/reliability', json={})).status_code == 422
            assert (await client.post('/api/evolutions', json={})).status_code == 422
            assert (await client.get('/api/reliability/' + key + '/export')).status_code == 200
            assert (await client.post('/api/reliability/' + key + '/cancel', json={})).json()['cancelled']
            await app.state.reliability.shutdown()
            result = (await client.get('/api/reliability')).json()[0]
            assert result['status'] == 'cancelled'
            assert (await client.get('/api/reliability/unknown/export')).status_code == 404
