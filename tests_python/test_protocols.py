import json
import pytest
import httpx
from backend.model_client import ModelClient, ModelOptions, request_body
from backend.runtime import create_run, execute_run
from backend.tools import ToolContext, Tool, object_schema
from backend.connectors import JsonConnector, platform_tools
from backend.autotool import acquire_tools


async def test_model_boundary_disables_thinking_and_returns_tool_observations():
    requests = []
    def handler(request):
        assert request.headers['Authorization'] == 'Bearer test-secret'
        body = json.loads(request.content)
        requests.append(body)
        assert body['enable_thinking'] is False and body['reasoning'] == {'enabled': False}
        assert body['parallel_tool_calls'] is True
        message = {'role': 'assistant', 'content': 'done', 'reasoning_content': 'must-not-be-exposed'}
        if len(requests) == 1:
            message['tool_calls'] = [{'id': 'call1', 'type': 'function', 'function': {'name': 'get_invoice', 'arguments': '{"invoiceId":"INV-001"}'}}]
        return httpx.Response(200, json={'choices': [{'message': message, 'finish_reason': 'tool_calls' if len(requests) == 1 else 'stop'}], 'usage': {'prompt_tokens': 42, 'completion_tokens': 7, 'completion_tokens_details': {'reasoning_tokens': 0}}})
    client = ModelClient(ModelOptions('https://openrouter.ai/api/v1', 'test-secret', 'test-model'), httpx.MockTransport(handler))
    run = create_run({'scenario': 'finance', 'mode': 'live', 'source': 'erpnext', 'task': 'Read invoice only'}, client.model)
    await execute_run(run, client, [Tool('get_invoice', 'read', 'read', object_schema({'invoiceId': {'type':'string'}}), lambda a,c: {'id':a['invoiceId']})])
    assert run['status'] == 'completed' and run['metrics']['inputTokens'] == 84 and run['metrics']['reasoningTokens'] == 0
    assert json.loads(requests[1]['messages'][-1]['content'])['result']['id'] == 'INV-001'
    assert requests[1]['messages'][-1]['tool_call_id'] == 'call1'
    assert 'must-not-be-exposed' not in json.dumps(run) and 'test-secret' not in json.dumps(run)


@pytest.mark.parametrize('status', [302, 401, 429, 500])
async def test_model_http_errors_are_not_retried_or_exposed(status):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={'error': 'sensitive-test-body'})
    client = ModelClient(ModelOptions('http://localhost/v1', 'secret', 'test'), httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match=str(status)) as error:
        await client.complete([], [])
    assert 'sensitive-test-body' not in str(error.value) and len(requests) == 1


def test_direct_qwen_uses_enable_thinking_without_router_specific_setting():
    body = request_body(ModelOptions('http://localhost:8000/v1', 'key', 'qwen'), [], [])
    assert body['enable_thinking'] is False and body['parallel_tool_calls'] is True and 'reasoning' not in body


async def test_erpnext_generated_tools_preserve_native_currency_and_encode_ids():
    requests = []
    def handler(request):
        requests.append(request)
        assert request.headers['Authorization'] == 'token test:secret'
        row = {'name': 'INV/测试', 'currency': 'USD', 'grand_total': 12.5}
        return httpx.Response(200, json={'data': [row] if request.url.params else row})
    client = JsonConnector('http://erp.test', {'Authorization': 'token test:secret'}, httpx.MockTransport(handler))
    tools = {t.name: t for t in platform_tools('erpnext', client)}
    context = ToolContext(create_run({'scenario': 'finance', 'mode': 'live', 'source': 'erpnext', 'task': 'read'}))
    rows = await tools['erpnext_list_invoices'].execute({'status': 'outstanding', 'page': 2, 'pageSize': 1}, context)
    assert requests[0].url.params['limit_start'] == '1'
    assert rows['records'][0]['grand_total'] == 12.5 and rows['mayHaveMore'] is True
    await tools['erpnext_get_invoice'].execute({'invoiceId': 'INV/测试'}, context)
    assert b'INV%2F' in requests[1].url.raw_path and 'Sales Invoice:INV/测试' in context.evidence
    assert tools['erpnext_get_invoice'].origin['kind'] == 'autotool'


async def test_zammad_dicts_and_permissions_are_not_hardcoded():
    def handler(request):
        return httpx.Response(200, json=[{'id': 501, 'state_id': 27, 'first_response_escalation_at': None}] if request.url.path == '/api/v1/tickets' else [{'id': 27, 'name': 'custom_open'}])
    tools = {t.name: t for t in platform_tools('zammad', JsonConnector('http://z.test', {}, httpx.MockTransport(handler)))}
    context = ToolContext(create_run({'scenario': 'support', 'mode': 'live', 'source': 'zammad', 'task': 'read'}))
    result = await tools['zammad_list_tickets'].execute({'page': 3, 'pageSize': 10}, context)
    assert result['records'][0]['state_id'] == 27 and result['records'][0]['first_response_escalation_at'] is None
    await tools['zammad_list_states'].execute({}, context)
    assert {'tickets:501', 'ticket_states:27'}.issubset(context.evidence)
    with pytest.raises(ValueError, match='not been observed'):
        await tools['publish_report'].execute({'title': 'report', 'summary': 'summary', 'findings': ['finding'], 'evidenceIds': ['invented']}, context)


async def test_autotool_new_spec_generates_enum_validation_without_custom_wrapper():
    spec = {'openapi': '3.0.3', 'info': {'title': 'New API', 'version': '1'}, 'paths': {'/api/new/{recordId}': {'get': {'operationId': 'get_new', 'summary': 'read', 'parameters': [
        {'name': 'recordId', 'in': 'path', 'required': True, 'schema': {'type': 'string'}},
        {'name': 'status', 'in': 'query', 'required': True, 'schema': {'type': 'string', 'enum': ['active', 'all']}}], 'x-resource': 'new', 'x-data-path': ['data']}}}}
    requests = []
    async def transport(path, query):
        requests.append((path, query))
        return {'data': {'id': 'fresh'}}
    tool = acquire_tools(spec, transport, lambda value, resource, ctx: value)[0]
    assert await tool.execute({'recordId': 'new/id', 'status': 'active'}, None) == {'id': 'fresh'}
    assert requests[0][0] == '/api/new/new%2Fid'
    for args in [{'recordId': '..', 'status': 'all'}, {'recordId': 'a', 'status': 'wrong'}, {'recordId': 'a', 'status': 'all', 'extra': 1}]:
        with pytest.raises(ValueError):
            await tool.execute(args, None)
    spec['paths']['/api/new/{recordId}']['post'] = spec['paths']['/api/new/{recordId}']['get']
    with pytest.raises(ValueError, match='GET'):
        acquire_tools(spec, transport, lambda value, r, c: value)
