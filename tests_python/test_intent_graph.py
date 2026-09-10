import asyncio
from copy import deepcopy
import pytest
from jsonschema import ValidationError
from backend.autotool import retrieve_tools
from backend.intent_graph import compile_intent_graph, execute_graph, validate_plan
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
