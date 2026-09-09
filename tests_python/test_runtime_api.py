import asyncio
from copy import deepcopy
import json
import pytest
import httpx
from backend.app import create_app
from backend.domain import PRESETS
from backend.models import RunRequest
from backend.runtime import create_run, execute_run
from backend.service import RunService
from backend.tools import sandbox_tools
from backend.fixture_provider import FixtureProvider


def call(name, args='{}', key='c1'):
    return {'id': key, 'type': 'function', 'function': {'name': name, 'arguments': args}}


def response(calls=None, content='done', usage=True):
    result = {'message': {'role': 'assistant', 'content': content}, 'finishReason': 'tool_calls' if calls else 'stop'}
    if calls:
        result['message']['tool_calls'] = calls
    if usage:
        result['usage'] = {'input': 10, 'output': 5}
    return result


class Scripted:
    kind, model = 'live', 'protocol-test'
    def __init__(self, responses):
        self.responses, self.histories, self.index = responses, [], 0
    async def complete(self, messages, tools):
        self.histories.append(deepcopy(messages))
        value = self.responses[min(self.index, len(self.responses)-1)]
        self.index += 1
        return value


def run_state():
    return create_run({'scenario': 'finance', 'mode': 'live', 'source': 'sandbox', 'task': 'Read only'}, 'test')


async def test_invalid_json_and_unknown_tool_become_repairable_observations():
    model = Scripted([response([call('get_invoice', '{invalid')]), response([call('send_email', '{}', 'c2')]), response([call('get_invoice', '{"invoiceId":"INV-001"}', 'c3')]), response()])
    run = await execute_run(run_state(), model, sandbox_tools('finance'))
    assert run['status'] == 'completed' and run['metrics']['toolErrors'] == 2
    assert model.histories[1][-1]['tool_call_id'] == 'c1'
    assert json.loads(model.histories[3][-1]['content'])['result']['id'] == 'INV-001'
    assert run['metrics']['modelRequests'] == 4 and run['metrics']['inputTokens'] == 40


async def test_independent_tool_calls_share_one_model_request_and_return_all_observations():
    model = Scripted([
        response([call('list_invoices', key='invoices'), call('list_payments', key='payments')]),
        response(),
    ])
    run = await execute_run(run_state(), model, sandbox_tools('finance'))
    assert run['status'] == 'completed'
    assert run['metrics']['modelRequests'] == 2 and run['metrics']['toolCalls'] == 2
    assert [message['tool_call_id'] for message in model.histories[1][-2:]] == ['invoices', 'payments']
    assert '一次响应中同时发出多个 tool_calls' in model.histories[0][0]['content']


@pytest.mark.parametrize('limits,expected', [({'max_steps': 1}, 1), ({'max_tools': 1}, 1), ({}, 4)])
async def test_run_budgets_and_repetition(limits, expected):
    run = await execute_run(run_state(), Scripted([response([call('list_invoices')])]), sandbox_tools('finance'), **limits)
    assert run['status'] == 'limited' and run['metrics']['toolCalls'] == expected
    assert 'evaluation' in run and run['metrics']['usageComplete'] is True


async def test_missing_usage_is_unknown():
    run = await execute_run(run_state(), Scripted([response(usage=False)]), sandbox_tools('finance'))
    assert run['metrics']['inputTokens'] is None and run['metrics']['usageComplete'] is False


async def test_cancellation_aborts_model_and_prevents_mutation():
    started = asyncio.Event()
    class Slow:
        kind, model = 'live', 'test'
        async def complete(self, messages, tools):
            started.set()
            await asyncio.sleep(10)
    run = run_state()
    task = asyncio.create_task(execute_run(run, Slow(), sandbox_tools('finance')))
    await started.wait()
    task.cancel()
    await task
    assert run['status'] == 'cancelled' and run['metrics']['toolCalls'] == 0


async def test_total_timeout_is_bounded():
    class Slow:
        kind, model = 'live', 'test'
        async def complete(self, messages, tools):
            await asyncio.sleep(5)
    run = await execute_run(run_state(), Slow(), sandbox_tools('finance'), timeout=.01)
    assert run['status'] == 'limited'


async def test_completed_model_with_missing_sla_is_repaired_and_failure_is_visible():
    run = create_run({'scenario': 'support', 'mode': 'fixture', 'source': 'sandbox', 'task': PRESETS['support']})
    await execute_run(run, FixtureProvider('support'), sandbox_tools('support'))
    run['state']['escalations'] = []
    run['request']['mode'] = 'live'
    run['events'], run['status'] = [], 'running'
    model = Scripted([response()])
    await execute_run(run, model, sandbox_tools('support'))
    assert model.index == 3 and run['evaluation']['status'] == 'failed'
    assert any(e['type'] == 'evaluation' for e in run['events'])


async def test_api_compatibility_history_export_origin_and_fixture_validation(tmp_path):
    service = RunService(tmp_path)
    app = create_app(service)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get('/api/config')).json()['backend'] == 'python'
            assert len((await client.get('/api/tools?scenario=finance')).json()) == 9
            assert (await client.post('/api/runs', json={'scenario': 'finance', 'mode': 'fixture', 'source': 'sandbox', 'task': 'ignored prompt'})).status_code == 400
            response_ = await client.post('/api/runs', json={'scenario': 'finance', 'mode': 'fixture', 'source': 'sandbox', 'task': PRESETS['finance']})
            assert response_.status_code == 202
            key = response_.json()['id']
            if key in service.tasks:
                await service.tasks[key]
            result = (await client.get('/api/runs/' + key)).json()
            assert result['status'] == 'completed' and result['evaluation']['status'] == 'passed'
            assert (await client.get('/api/runs/' + key + '/export/md')).headers['content-disposition'].startswith('attachment')
            assert (await client.post('/api/platforms/check', json={}, headers={'Origin': 'https://untrusted.example'})).status_code == 403
            assert (await client.post('/api/platforms/check', content='plain')).status_code == 415
            assert (await client.post('/api/runs', content=' ' * 40000, headers={'Content-Type': 'application/json'})).status_code == 413
            assert (await client.get('/api/unknown')).status_code == 404
    restored = RunService(tmp_path)
    restored.restore()
    assert key in restored.runs


async def test_immediate_cancellation_does_not_leave_processing_slot_occupied(tmp_path):
    service = RunService(tmp_path)
    run = await service.start({'scenario': 'finance', 'mode': 'fixture', 'source': 'sandbox', 'task': PRESETS['finance']})
    task = service.tasks[run['id']]
    assert service.cancel(run['id'])
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    assert run['id'] not in service.tasks and run['status'] == 'cancelled'


def test_request_scope_validation():
    with pytest.raises(ValueError):
        RunRequest.model_validate({'scenario': 'finance', 'mode': 'live', 'source': 'zammad', 'task': 'read'})
    with pytest.raises(ValueError):
        RunRequest.model_validate({'scenario': 'finance', 'mode': 'live', 'source': 'erpnext', 'task': 'read', 'snapshot': 'changed'})
