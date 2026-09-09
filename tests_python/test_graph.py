from copy import deepcopy
import json
import pytest
from backend.domain import PRESETS
from backend.runtime import create_run, execute_run
from backend.tools import Tool, ToolContext, object_schema, sandbox_tools
from backend.graph import compile_read_graph, run_read_graph, ordered_nodes, task_key, contract_hash, applicable
from backend.graph_store import GraphStore, environment_hash
from backend.gagent import retrieve, select_workflow


async def trace(tools, operations):
    run = create_run({'scenario': 'finance', 'mode': 'live', 'source': 'sandbox', 'task': PRESETS['finance']}, 'protocol-test')
    for name, args in operations:
        run['events'].append({'seq': len(run['events']) + 1, 'at': '', 'type': 'action', 'title': name, 'detail': {'arguments': json.dumps(args)}})
        result = await next(t for t in tools if t.name == name).execute(args, ToolContext(run))
        run['events'].append({'seq': len(run['events']) + 1, 'at': '', 'type': 'observation', 'title': name, 'detail': {'ok': True, 'result': result}})
    run['status'] = 'completed'
    run['metrics'].update(modelRequests=3, inputTokens=150, outputTokens=40)
    return run


OPS = [('list_invoices', {}), ('list_payments', {})] + [('preview_payment_match', {'paymentId': key}) for key in ['PAY-001', 'PAY-002', 'PAY-003']]


class FinalModel:
    kind, model = 'live', 'test-model'
    def __init__(self):
        self.messages = []
    async def complete(self, messages, tools):
        self.messages = deepcopy(messages)
        return {'message': {'role': 'assistant', 'content': '读取完毕'}, 'finishReason': 'stop', 'usage': {'input': 20, 'output': 5}}


async def test_dataflow_inference_stops_before_writes():
    tools = sandbox_tools('finance')
    source = await trace(tools, OPS + [('allocate_payment', {'paymentId': 'PAY-001', 'allocations': [{'invoiceId': 'INV-001', 'amountCents': 1200000}]}), ('get_invoice', {'invoiceId': 'INV-001'})])
    nodes = compile_read_graph(source, tools)
    assert len(nodes) == 3 and nodes[2]['foreach'] == {'nodeId': 'n2', 'collectionPath': []}
    assert nodes[2]['arguments']['paymentId'] == {'kind': 'item', 'path': ['id']}
    assert len(nodes[2]['sourceEventSeqs']) == 3 and 'PAY-001' not in json.dumps(nodes)


@pytest.mark.parametrize('variant', ['changed', 'exception'])
async def test_new_ids_amounts_records_and_exceptions_are_read_fresh(tmp_path, variant):
    tools = sandbox_tools('finance')
    source = await trace(tools, OPS)
    graph = await GraphStore(tmp_path).learn(source, tools)
    run = create_run(dict(source['request'], strategy='graph', snapshot=variant, task='读取当前数据，不要求修改'), 'test')
    run['graph'] = {'status': 'hit', 'nodeStates': {}, 'toolCalls': 0, 'completedNodes': 0}
    model = FinalModel()
    await execute_run(run, model, tools, graph=graph)
    assert run['status'] == 'completed' and run['metrics']['modelRequests'] == 1
    calls = [json.loads(e['detail']['arguments'])['paymentId'] for e in run['events'] if e['type'] == 'action' and e['title'] == 'preview_payment_match']
    assert set(calls) == {p['id'] for p in run['state']['payments']} and len(calls) == 7
    assert run['state']['allocations'] == []
    if variant == 'exception':
        assert any('customer_currency_or_reference_mismatch' in (m.get('content') or '') for m in model.messages if m['role'] == 'tool')


async def test_shape_change_falls_back_and_never_reuses_results(tmp_path):
    tools = sandbox_tools('finance')
    source = await trace(tools, OPS)
    graph = await GraphStore(tmp_path).learn(source, tools)
    next(t for t in tools if t.name == 'list_payments').handler = lambda a, c: {'unexpected': []}
    run = create_run(dict(source['request'], task='只读'), 'test')
    run['graph'] = {'status': 'hit', 'nodeStates': {}, 'toolCalls': 0, 'completedNodes': 0}
    await execute_run(run, FinalModel(), tools, graph=graph)
    assert run['graph']['status'] == 'fallback' and '集合形状' in run['graph']['reason']
    assert run['metrics']['modelRequests'] == 1 and 'report' not in run


async def test_dynamic_pagination_expands_beyond_original_sample():
    rows = [{'id': 1}, {'id': 2}]
    def listing(args, context):
        page, size = args['page'], args['pageSize']
        return {'records': rows[(page-1)*size:page*size], 'mayHaveMore': page*size < len(rows)}
    tools = [Tool('list_records', 'read', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), listing),
             Tool('get_record', 'read', 'read', object_schema({'recordId': {'type': 'integer'}}), lambda args, c: {'id': args['recordId']})]
    source = await trace(tools, [('list_records', {'page': 1, 'pageSize': 2}), ('get_record', {'recordId': 1})])
    nodes = compile_read_graph(source, tools)
    rows[:] = [{'id': i} for i in range(11, 16)]
    pages, ids = [], []
    async def invoke(name, args, node):
        (pages if name == 'list_records' else ids).append(args.get('page', args.get('recordId')))
        return await next(t for t in tools if t.name == name).execute(args, ToolContext(source))
    await run_read_graph(nodes, tools, invoke)
    assert pages == [1, 2, 3] and ids == [11, 12, 13, 14, 15]


async def test_store_restore_and_quality_rejection(tmp_path):
    tools = sandbox_tools('finance')
    source = await trace(tools, OPS)
    store = GraphStore(tmp_path)
    graph = await store.learn(source, tools)
    assert graph['validation']['toolCalls'] == 8
    assert (await store.learn(source, tools))['id'] == graph['id']
    loaded = GraphStore(tmp_path)
    loaded.restore()
    assert loaded.select(source['request'], tools)['graph']['id'] == graph['id']
    bad = deepcopy(source)
    bad['id'] = '00000000-0000-4000-8000-000000000001'
    bad['evaluation'] = {'status': 'failed'}
    with pytest.raises(ValueError, match='结果校验'):
        await store.learn(bad, tools)


def test_cycles_missing_dependencies_writes_and_paths_rejected():
    tools = sandbox_tools('finance')
    node = {'id': 'a', 'tool': 'list_invoices', 'arguments': {}, 'dependencies': ['b'], 'sourceEventSeqs': [1]}
    with pytest.raises(ValueError, match='缺少'):
        ordered_nodes([node], tools)
    with pytest.raises(ValueError, match='循环'):
        ordered_nodes([node, dict(node, id='b', dependencies=['a'])], tools)
    with pytest.raises(ValueError, match='非读取'):
        ordered_nodes([dict(node, dependencies=[], tool='allocate_payment')], tools)
    with pytest.raises(ValueError, match='路径'):
        ordered_nodes([dict(node, dependencies=[], arguments={'x': {'kind': 'result', 'nodeId': 'a', 'path': ['__proto__']}})], tools)


async def test_compiler_does_not_freeze_unbound_ids_dates_or_amounts():
    tools = sandbox_tools('finance')
    source = await trace(tools, [('get_invoice', {'invoiceId': 'INV-001'})])
    with pytest.raises(ValueError, match='没有可安全'):
        compile_read_graph(source, tools)
    tool = Tool('search_date', 'read', 'read', object_schema({'date': {'type': 'string'}}), lambda a, c: a)
    source = await trace([tool], [('search_date', {'date': '2026-09-01'})])
    with pytest.raises(ValueError):
        compile_read_graph(source, [tool])


def test_task_clock_abstraction_does_not_remove_deadline_constraints():
    assert task_key('以 2026-09-09T01:00:00Z 为本次巡检时刻，读取') == task_key('以 2026-09-10T01:00:00Z 为本次巡检时刻，读取')
    assert task_key('截止 2026-09-09T01:00:00Z') != task_key('截止 2026-09-10T01:00:00Z')


async def test_gagent_selection_closes_dependencies_and_counts_cost(tmp_path):
    tools = sandbox_tools('finance')
    source = await trace(tools, OPS)
    graph = await GraphStore(tmp_path).learn(source, tools)
    calls = 0
    class Planner(FinalModel):
        async def complete(self, messages, available):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {'message': {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'plan1', 'type': 'function', 'function': {'name': 'select_workflow', 'arguments': json.dumps({'graphId': graph['id'], 'nodeIds': ['n3'], 'reason': '核查回款'})}}]}, 'finishReason': 'tool_calls', 'usage': {'input': 30, 'output': 5}}
            return await super().complete(messages, available)
    run = create_run(dict(source['request'], task='读取回款匹配依据，不执行修改'), 'test')
    run['graph'] = {'status': 'miss', 'nodeStates': {}, 'toolCalls': 0, 'completedNodes': 0}
    await execute_run(run, Planner(), tools, candidates=[graph])
    assert run['graph']['selection'] == 'adapted' and run['graph']['selectedNodeIds'] == ['n2', 'n3']
    assert run['metrics']['modelRequests'] == 2 and run['metrics']['inputTokens'] == 50
