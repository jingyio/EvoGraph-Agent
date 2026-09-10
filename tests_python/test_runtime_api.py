import asyncio
from copy import deepcopy
import json
import pytest
from backend.models import RunRequest
from backend.runtime import create_run, execute_run
from backend.tools import Tool, object_schema

def protocol_tools():
    return [Tool('get_invoice','read','read',object_schema({'invoiceId':{'type':'string'}}),lambda a,c:{'id':a['invoiceId']}),
            Tool('list_invoices','read','read',object_schema(),lambda a,c:[]),
            Tool('list_payments','read','read',object_schema(),lambda a,c:[])]

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
    return create_run({'scenario': 'finance', 'mode': 'live', 'source': 'erpnext', 'task': 'Read only'}, 'test')

async def test_invalid_json_and_unknown_tool_become_repairable_observations():
    model = Scripted([response([call('get_invoice', '{invalid')]), response([call('send_email', '{}', 'c2')]), response([call('get_invoice', '{"invoiceId":"INV-001"}', 'c3')]), response()])
    run = await execute_run(run_state(), model, protocol_tools())
    assert run['status'] == 'completed' and run['metrics']['toolErrors'] == 2
    assert model.histories[1][-1]['tool_call_id'] == 'c1'
    assert json.loads(model.histories[3][-1]['content'])['result']['id'] == 'INV-001'
    assert run['metrics']['modelRequests'] == 4 and run['metrics']['inputTokens'] == 40

async def test_independent_tool_calls_share_one_model_request_and_return_all_observations():
    model = Scripted([
        response([call('list_invoices', key='invoices'), call('list_payments', key='payments')]),
        response(),
    ])
    run = await execute_run(run_state(), model, protocol_tools())
    assert run['status'] == 'completed'
    assert run['metrics']['modelRequests'] == 2 and run['metrics']['toolCalls'] == 2
    assert [message['tool_call_id'] for message in model.histories[1][-2:]] == ['invoices', 'payments']
    assert '一次响应中同时发出多个 tool_calls' in model.histories[0][0]['content']

@pytest.mark.parametrize('limits,expected', [({'max_steps': 1}, 1), ({'max_tools': 1}, 1), ({}, 4)])
async def test_run_budgets_and_repetition(limits, expected):
    run = await execute_run(run_state(), Scripted([response([call('list_invoices')])]), protocol_tools(), **limits)
    assert run['status'] == 'limited' and run['metrics']['toolCalls'] == expected
    assert 'evaluation' in run and run['metrics']['usageComplete'] is True

async def test_missing_usage_is_unknown():
    run = await execute_run(run_state(), Scripted([response(usage=False)]), protocol_tools())
    assert run['metrics']['inputTokens'] is None and run['metrics']['usageComplete'] is False

async def test_cancellation_aborts_model_and_prevents_mutation():
    started = asyncio.Event()
    class Slow:
        kind, model = 'live', 'test'
        async def complete(self, messages, tools):
            started.set()
            await asyncio.sleep(10)
    run = run_state()
    task = asyncio.create_task(execute_run(run, Slow(), protocol_tools()))
    await started.wait()
    task.cancel()
    await task
    assert run['status'] == 'cancelled' and run['metrics']['toolCalls'] == 0

async def test_total_timeout_is_bounded():
    class Slow:
        kind, model = 'live', 'test'
        async def complete(self, messages, tools):
            await asyncio.sleep(5)
    run = await execute_run(run_state(), Slow(), protocol_tools(), timeout=.01)
    assert run['status'] == 'limited'

def test_request_scope_validation():
    with pytest.raises(ValueError):
        RunRequest.model_validate({'scenario': 'finance', 'mode': 'live', 'source': 'zammad', 'task': 'read'})
    with pytest.raises(ValueError):
        RunRequest.model_validate({'scenario': 'finance', 'mode': 'live', 'source': 'erpnext', 'task': 'read', 'snapshot': 'changed'})
