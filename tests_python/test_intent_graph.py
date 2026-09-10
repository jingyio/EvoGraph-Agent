import asyncio
from copy import deepcopy
import pytest
from jsonschema import ValidationError
from backend.autotool import retrieve_tools
from backend.intent_graph import reject_semantic_narrowing, select_retrieved_graph, compile_intent_graph, execute_graph, validate_plan
from backend.tools import Tool, object_schema


def fixture():
    tools = [Tool('list_orders', '分页列出订单 ID，返回 records', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), lambda a, c: None),
             Tool('get_payments', '读取支付金额、支付方式和分期，返回 payments', 'read', object_schema({'orderId': {'type': 'string'}}), lambda a, c: None),
             Tool('get_items', '读取商品金额与运费，返回 items', 'read', object_schema({'orderId': {'type': 'string'}}), lambda a, c: None)]
    plan = {'steps': [dict(id='list', intent='分页列出订单 ID', dependencies=[]), dict(id='pay', intent='读取支付金额和分期', dependencies=['list']), dict(id='items', intent='读取商品运费', dependencies=['list'])]}
    proposal = {'nodes': [dict(id='list', tool='list_orders'), dict(id='pay', tool='get_payments'), dict(id='items', tool='get_items')]}
    retrieval = {s['id']: retrieve_tools(s['intent'], tools) for s in plan['steps']}
    return tools, plan, proposal, retrieval


def test_intent_retrieval_uses_meaningful_short_descriptions():
    tools, _, _, _ = fixture()
    assert retrieve_tools('核对支付金额及分期', tools, 1)[0]['name'] == 'get_payments'
    assert retrieve_tools('读取商品和运费', tools, 1)[0]['name'] == 'get_items'


def test_local_graph_selection_uses_retrieval_and_contract_shape():
    tools, plan, _, retrieval = fixture()
    # A list tool can have a higher lexical score for a dependent record step.
    retrieval['pay'].insert(0, {'name': 'list_orders', 'score': 99})
    proposal, diagnostics = select_retrieved_graph(plan, retrieval, tools)
    selected = {node['id']: node['tool'] for node in proposal['nodes']}
    assert selected == {'list': 'list_orders', 'pay': 'get_payments', 'items': 'get_items'}
    assert all(row['selection'] == 'local-retrieval-and-contract' for row in diagnostics)


def test_selection_requires_list_root_and_requested_detail_capability():
    tools = [
        Tool('task_scope', '读取任务范围', 'read', object_schema(), lambda a, c: None, outputs=['id']),
        Tool('list_orders', '分页列出订单 ID', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), lambda a, c: None, outputs=['id', 'status']),
        Tool('get_order', '读取订单状态和日期', 'read', object_schema({'orderId': {'type': 'string'}}), lambda a, c: None, outputs=['id', 'status']),
        Tool('get_payments', '读取支付记录 payments', 'read', object_schema({'orderId': {'type': 'string'}}), lambda a, c: None, outputs=['id', 'payments']),
    ]
    plan = {'steps': [dict(id='orders', intent='获取订单列表及 ID', dependencies=[]), dict(id='payments', intent='获取支付信息 payments', dependencies=['orders'])]}
    retrieval = {'orders': [{'name': 'task_scope', 'score': 9}, {'name': 'list_orders', 'score': 1}],
                 'payments': [{'name': 'get_order', 'score': 9}, {'name': 'get_payments', 'score': 1}]}
    proposal, _ = select_retrieved_graph(plan, retrieval, tools)
    assert {node['id']: node['tool'] for node in proposal['nodes']} == {'orders': 'list_orders', 'payments': 'get_payments'}
    incompatible = {'nodes': [dict(id='orders', tool='list_orders'), dict(id='payments', tool='get_order')]}
    with pytest.raises(ValueError, match='output capability'):
        compile_intent_graph(plan, incompatible, retrieval, tools)


def test_task_authority_rejects_explicit_inclusive_to_exact_narrowing():
    task = '找出支付记录分期数达到 6 的订单'
    with pytest.raises(ValueError, match='narrows'):
        reject_semantic_narrowing({'steps': [dict(id='payments', intent='筛选分期数为 6 的支付记录', dependencies=[])]}, task)
    reject_semantic_narrowing({'steps': [dict(id='payments', intent='筛选分期数达到 6 的支付记录', dependencies=[])]}, task)


async def test_graph_reuses_upstream_fields_and_elides_record_calls():
    tools = [Tool('list_issues', '分页列出工单，返回 state', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}),
                  lambda a, c: None, outputs=['id', 'state']),
             Tool('get_issue', '读取工单 state', 'read', object_schema({'issueId': {'type': 'string'}}), lambda a, c: None, outputs=['id', 'state'])]
    plan = {'steps': [dict(id='list', intent='分页列出工单', dependencies=[]), dict(id='state', intent='读取每条工单的 state 字段', dependencies=['list'])]}
    proposal = {'nodes': [dict(id='list', tool='list_issues'), dict(id='state', tool='get_issue')]}
    retrieval = {step['id']: retrieve_tools(step['intent'], tools) for step in plan['steps']}
    nodes = compile_intent_graph(plan, proposal, retrieval, tools)
    assert nodes[1]['reuse']['nodeId'] == 'list' and nodes[1]['reuse']['fields'] == ['state']
    calls, elided = [], []
    async def invoke(name, args, node):
        calls.append((name, args))
        return {'records': [{'id': '1', 'state': 'open'}, {'id': '2', 'state': 'closed'}], 'mayHaveMore': False}
    await execute_graph(nodes, tools, invoke, lambda key, state: None, lambda key, count: elided.append((key, count)))
    assert calls == [('list_issues', {'page': 1, 'pageSize': 50})] and elided == [('state', 2)]


async def test_graph_waits_for_pagination_then_overlaps_independent_reads():
    tools, plan, proposal, retrieval = fixture()
    nodes = compile_intent_graph(plan, proposal, retrieval, tools)
    calls, active, peak = [], 0, 0
    gate = asyncio.Event()
    async def invoke(name, args, node):
        nonlocal active, peak
        calls.append((name, args))
        if name == 'list_orders':
            return {'records': [{'id': 'new-a'}, {'id': 'new-b'}] if args['page'] == 1 else [{'id': 'new-c'}], 'mayHaveMore': args['page'] == 1}
        assert len([c for c in calls if c[0] == 'list_orders']) == 2
        active += 1
        peak = max(peak, active)
        if active >= 2:
            gate.set()
        await asyncio.wait_for(gate.wait(), 1)
        active -= 1
        return {'id': args['orderId']}
    outputs = await execute_graph(nodes, tools, invoke, lambda key, state: None)
    assert peak >= 2 and len(outputs['pay']) == len(outputs['items']) == 3
    assert {a['orderId'] for n, a in calls if n == 'get_payments'} == {'new-a', 'new-b', 'new-c'}


async def test_filter_then_enrich_binds_plan_semantics_and_only_reads_selected_records():
    tools = [Tool('list_orders', '分页列出订单 ID 和状态', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), lambda a, c: None, outputs=['id', 'status']),
             Tool('get_payments', '读取支付记录', 'read', object_schema({'orderId': {'type': 'string'}}), lambda a, c: None, outputs=['id', 'payments'])]
    plan = {'steps': [
        dict(id='list', intent='分页列出订单 ID 和 status', dependencies=[]),
        dict(id='payments', intent='读取 payments', dependencies=['list'], selection=dict(kind='match', sourceStepId='list', field='status', operator='equals', value='canceled')),
    ]}
    proposal = {'nodes': [dict(id='list', tool='list_orders'), dict(id='payments', tool='get_payments')]}
    retrieval = {step['id']: retrieve_tools(step['intent'], tools) for step in plan['steps']}
    nodes = compile_intent_graph(plan, proposal, retrieval, tools)
    assert nodes[1]['foreach']['filter'] == {'field': 'status', 'operator': 'equals', 'value': 'canceled'}
    calls, filters = [], []
    async def invoke(name, args, node):
        calls.append((name, args))
        if name == 'list_orders':
            return {'records': [{'id': 'a', 'status': 'canceled'}, {'id': 'b', 'status': 'delivered'}], 'mayHaveMore': False}
        return {'id': args['orderId'], 'payments': []}
    await execute_graph(nodes, tools, invoke, lambda *args: None, on_filter=lambda node, detail: filters.append((node, detail)))
    assert calls == [('list_orders', {'page': 1, 'pageSize': 50}), ('get_payments', {'orderId': 'a'})]
    assert filters == [('payments', {'sourceNodeId': 'list', 'condition': {'field': 'status', 'operator': 'equals', 'value': 'canceled'}, 'totalRecords': 2, 'selectedRecords': 1, 'filteredOutRecords': 1})]


async def test_uncertain_condition_defers_detail_subgraph_and_invalid_current_binding_fails_closed():
    tools = [Tool('list_orders', '分页列出订单 ID 和状态', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), lambda a, c: None, outputs=['id', 'status']),
             Tool('get_payments', '读取支付记录', 'read', object_schema({'orderId': {'type': 'string'}}), lambda a, c: None, outputs=['id', 'payments'])]
    proposal = {'nodes': [dict(id='list', tool='list_orders'), dict(id='payments', tool='get_payments')]}
    deferred = {'steps': [dict(id='list', intent='分页列出订单 ID 和 status', dependencies=[]),
                          dict(id='payments', intent='读取 payments', dependencies=['list'], selection=dict(kind='model', reason='列表字段不足以判断支付条件'))]}
    retrieval = {step['id']: retrieve_tools(step['intent'], tools) for step in deferred['steps']}
    nodes = compile_intent_graph(deferred, proposal, retrieval, tools)
    assert nodes[1]['defer'] is True
    matched = deepcopy(deferred)
    matched['steps'][1]['selection'] = dict(kind='match', sourceStepId='list', field='status', operator='equals', value='canceled')
    nodes = compile_intent_graph(matched, proposal, retrieval, tools)
    async def invoke(name, args, node):
        if name == 'list_orders':
            return {'records': [{'id': 'a', 'status': 1}], 'mayHaveMore': False}
        return {'id': args['orderId'], 'payments': []}
    with pytest.raises(ValueError, match='value type changed'):
        await execute_graph(nodes, tools, invoke, lambda *args: None)


def test_cycles_hardcoded_ids_wrong_candidate_and_missing_dependency_rejected():
    tools, plan, proposal, retrieval = fixture()
    cyclic = deepcopy(plan)
    cyclic['steps'][0]['dependencies'] = ['pay']
    with pytest.raises(ValueError):
        validate_plan(cyclic)
    wrong = deepcopy(proposal)
    wrong['nodes'][1]['arguments'] = {'orderId': {'kind': 'literal', 'value': 'old-id'}}
    with pytest.raises(ValidationError, match='Additional properties'):
        compile_intent_graph(plan, wrong, retrieval, tools)
    removed = deepcopy(retrieval)
    removed['pay'] = [{'name': 'get_items', 'score': 1}]
    with pytest.raises(ValueError, match='retrieved'):
        compile_intent_graph(plan, proposal, removed, tools)
    plan['steps'][1]['dependencies'] = []
    with pytest.raises(ValueError, match='upstream'):
        compile_intent_graph(plan, proposal, retrieval, tools)
