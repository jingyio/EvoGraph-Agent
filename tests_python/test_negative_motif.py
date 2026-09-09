from copy import deepcopy
import json
import pytest
import httpx
from backend.app import create_app
from backend.service import RunService
from backend.domain import PRESETS
from backend.runtime import create_run, execute_run
from backend.tools import sandbox_tools, ToolContext
from backend.negative_motif import compile_negative_motifs, NegativeMotifStore, matched_rows
from backend.graph import compile_read_graph
from backend.models import RunRequest


def case(entity='BANK-1004', evidence=None):
    return dict(kind='duplicate', entityId=entity, evidenceIds=evidence or ['PAY-004', 'PAY-005'], summary='核查重复流水')


async def source_trace(repair=True):
    run = create_run(dict(scenario='finance', source='sandbox', mode='live', task=PRESETS['finance']))
    tools = {t.name: t for t in sandbox_tools('finance')}
    operations = [('list_payments', {}), ('create_finance_case', case())]
    if repair:
        operations.append(('create_finance_case', case('PAY-004')))
    for name, args in operations:
        run['events'].append(dict(seq=len(run['events']) + 1, type='action', title=name, detail={'arguments': json.dumps(args)}))
        try:
            result = dict(ok=True, result=await tools[name].execute(args, ToolContext(run)))
        except ValueError as error:
            result = dict(ok=False, error=str(error))
        run['events'].append(dict(seq=len(run['events']) + 1, type='observation', title=name, detail=result))
    run.update(status='limited', finishedAt='test', evaluation={'status': 'failed'})
    run['metrics']['modelRequests'] = 3
    return run


async def test_failed_task_can_yield_local_negative_but_not_positive_graph(tmp_path):
    run = await source_trace()
    before = deepcopy(run)
    store = NegativeMotifStore(tmp_path)
    result = await store.learn(run, sandbox_tools('finance'))
    assert len(result['motifs']) == 1 and not result['unexplainedFailures']
    motif = result['motifs'][0]
    assert motif['sourceRunStatus'] == 'limited'
    assert motif['nodes'][3]['dependencies'] == ['read', 'reject']
    assert 'BANK-1004' not in json.dumps(motif)
    assert run == before
    assert motif['validation']['toolCalls'] == 3
    with pytest.raises(ValueError):
        compile_read_graph(run, sandbox_tools('finance'))
    assert (await store.learn(run, sandbox_tools('finance')))['motifs'][0]['id'] == motif['id']
    restored = NegativeMotifStore(tmp_path)
    restored.restore()
    assert restored.select(run['request'], sandbox_tools('finance'))[0]['id'] == motif['id']


async def test_requires_repair_dataflow_and_same_entity_group():
    run = await source_trace(False)
    result = await compile_negative_motifs(run, sandbox_tools('finance'))
    assert not result['motifs'] and len(result['unexplainedFailures']) == 1
    run = await source_trace()
    run['events'][4]['detail']['arguments'] = json.dumps(case('PAY-002', ['PAY-002']))
    assert not (await compile_negative_motifs(run, sandbox_tools('finance')))['motifs']
    run = await source_trace()
    run['events'][1]['detail']['result'] = []
    assert not (await compile_negative_motifs(run, sandbox_tools('finance')))['motifs']


async def test_recorded_success_must_replay_successfully():
    run = await source_trace()
    tools = sandbox_tools('finance')
    tool = next(t for t in tools if t.name == 'create_finance_case')
    original = tool.handler
    def reject(args, context):
        if args['entityId'] == 'PAY-004':
            raise ValueError('changed implementation')
        return original(args, context)
    tool.handler = reject
    assert not (await compile_negative_motifs(run, tools))['motifs']


class Sequence:
    kind, model = 'live', 'test-only-script'
    def __init__(self, operations):
        self.operations, self.index, self.histories = operations, 0, []
    async def complete(self, messages, tools):
        self.histories.append(deepcopy(messages))
        if self.index < len(self.operations):
            name, args = self.operations[self.index]
            self.index += 1
            message = dict(role='assistant', content=None, tool_calls=[dict(id='c' + str(self.index), type='function', function=dict(name=name, arguments=json.dumps(args)))])
        else:
            message = dict(role='assistant', content='Done')
        return dict(message=message, finishReason='stop', usage=dict(input=10, output=5))


@pytest.mark.parametrize('enabled', [True, False])
async def test_guard_rebinds_new_ids_and_keeps_rejected_attempt_in_metrics(enabled):
    motif = (await compile_negative_motifs(await source_trace(), sandbox_tools('finance')))['motifs'][0]
    run = create_run(dict(scenario='finance', source='sandbox', mode='live', task='登记重复事项', negativeMotifs=enabled))
    # Unseen identifiers; the guard must use this run's observations.
    for p in run['state']['payments']:
        p['id'] = 'fresh-' + p['id']
        p['bankRef'] = 'fresh-' + p['bankRef']
    run['initial'] = deepcopy(run['state'])
    bad = case('fresh-BANK-1004', ['fresh-PAY-004', 'fresh-PAY-005'])
    good = dict(bad, entityId='fresh-PAY-004')
    provider = Sequence([('list_payments', {}), ('create_finance_case', bad), ('create_finance_case', good)])
    await execute_run(run, provider, sandbox_tools('finance'), negative_motifs=[motif])
    assert run['status'] == 'completed' and len(run['state']['cases']) == 1
    assert run['metrics']['toolCalls'] == 3 and run['metrics']['toolErrors'] == 1
    assert bool([e for e in run['events'] if e['type'] == 'motif']) == enabled
    assert run.get('negativeMotif', {}).get('guardHits', 0) == int(enabled)
    assert bool('历史负 motif' in provider.histories[0][0]['content']) == enabled


async def test_guard_needs_observation_and_matching_contract():
    motif = (await compile_negative_motifs(await source_trace(), sandbox_tools('finance')))['motifs'][0]
    for stale, with_read in [(False, False), (True, True)]:
        changed = deepcopy(motif)
        if stale:
            changed['contractHash'] = 'stale'
        run = create_run(dict(scenario='finance', source='sandbox', mode='live', task='核查', negativeMotifs=True))
        ops = ([('list_payments', {})] if with_read else []) + [('create_finance_case', case())]
        await execute_run(run, Sequence(ops), sandbox_tools('finance'), negative_motifs=[changed])
        assert run['negativeMotif']['guardHits'] == 0
    assert not matched_rows(case('PAY-004'), (await source_trace())['state']['payments'])
    with pytest.raises(ValueError):
        RunRequest(scenario='support', source='zammad', mode='live', task='read', negativeMotifs=True)


async def test_reflection_api_learns_from_failed_run_without_promoting_it(tmp_path):
    source = await source_trace()
    original = deepcopy(source)
    service = RunService(tmp_path)
    service.runs[source['id']] = source
    app = create_app(service)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/runs/' + source['id'] + '/reflect', json={})
            assert response.status_code == 200 and len(response.json()['motifs']) == 1
            assert len((await client.get('/api/negative-motifs')).json()) == 1
            assert not (await client.get('/api/graphs')).json()
            assert source == original
            assert (await client.post('/api/runs/unknown/reflect', json={})).status_code == 404
            source['status'] = 'running'
            assert (await client.post('/api/runs/' + source['id'] + '/reflect', json={})).status_code == 422
