"""Persistent TinyEdge protocol tests with injected training trajectories."""
from copy import deepcopy
import pytest
from backend.tools import Tool, object_schema
from backend.tinyedge import mine, candidate_rows, compose
from backend.task_runner import TaskRunner, TaskRunRequest


def tools():
    return [
        Tool('list_orders', '读取订单列表', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), lambda a, c: None, outputs=['id', 'status']),
        Tool('get_payments', '读取支付信息', 'read', object_schema({'orderId': {'type': 'string'}}), lambda a, c: None, outputs=['id', 'payments']),
        Tool('get_items', '读取商品信息', 'read', object_schema({'orderId': {'type': 'string'}}), lambda a, c: None, outputs=['id', 'items']),
    ]


def workflow(key, detail):
    nodes = [
        dict(id='list', tool='list_orders', arguments={'page': {'kind': 'literal', 'value': 1}, 'pageSize': {'kind': 'literal', 'value': 50}}, dependencies=[]),
        dict(id=detail, tool='get_payments' if detail == 'payments' else 'get_items', arguments={'orderId': {'kind': 'item', 'path': ['id']}}, dependencies=['list'], foreach={'nodeId': 'list', 'collectionPath': ['records']}),
    ]
    return dict(id=key, sourceRunId='run-' + key, sourceTaskId='task-' + key, scenario='finance', family=key,
                sourceSplit='train', contractHash='contract', nodes=nodes,
                plan={'steps': [dict(id='list', intent='读取订单列表', dependencies=[]), dict(id=detail, intent='读取支付信息' if detail == 'payments' else '读取商品信息', dependencies=['list'])]})


def test_mines_closed_persistent_fragments_from_distinct_training_workflows_and_composes_them():
    rows = [workflow('payments-a', 'payments'), workflow('payments-b', 'payments'), workflow('items-a', 'items'), workflow('items-b', 'items')]
    # Use the same synthetic contract marker as the test workflows.
    test_tools = tools()
    for row in rows:
        from backend.graph import contract_hash
        row['contractHash'] = contract_hash(test_tools)
    edges = mine(rows, test_tools)
    assert len(edges) >= 2
    payment = next(edge for edge in edges if any(node['tool'] == 'get_payments' for node in edge['nodeTemplates']))
    item = next(edge for edge in edges if any(node['tool'] == 'get_items' for node in edge['nodeTemplates']))
    assert all(edge['support'] == 2 and edge['closed'] and edge['executable'] for edge in [payment, item])
    task = {'scenario': 'finance'}
    rows = candidate_rows(task, edges, test_tools, '读取支付信息')
    assert rows[0]['tinyEdgeId'] == payment['id'] and rows[0]['support'] == 2
    assembled = compose([payment['id'], item['id']], edges, test_tools)
    assert {node['tool'] for node in assembled['nodes']} == {'list_orders', 'get_payments', 'get_items'}
    detail_nodes = [node for node in assembled['nodes'] if node['tool'] != 'list_orders']
    assert len(detail_nodes) == 2 and all(len(node['dependencies']) == 1 for node in detail_nodes)
    assert all(origin['sourceRunIds'] for origin in assembled['origins'])


def test_boundary_and_contract_mismatch_cannot_be_mined_or_composed():
    row = workflow('one', 'payments')
    row['nodes'][1]['defer'] = True
    from backend.graph import contract_hash
    row['contractHash'] = contract_hash(tools())
    assert mine([row, deepcopy(row)], tools()) == []
    with pytest.raises(ValueError, match='two_distinct'):
        compose([], [], tools())


async def test_composition_path_selects_once_and_executes_combined_graph(tmp_path):
    class Bank:
        manifest = {'source': 'injected-composition-regression'}
        root = tmp_path
        def task(self, key):
            return dict(id=key, scenario='finance', family='reconciliation', split='train', task='读取支付信息和商品信息并发布结果', suggestedBudget={'toolCalls': 20})
        def tools(self, key):
            def listing(args, ctx):
                ctx.evidence.add(key)
                return {'records': [{'id': 'current'}], 'mayHaveMore': False}
            def detail(field):
                return lambda args, ctx: {'id': args['orderId'], field: []}
            def publish(args, ctx):
                ctx.run['evaluation'] = dict(status='passed' if key in ctx.evidence else 'failed', issues=[])
                return {'saved': True}
            return [Tool('list_orders', '读取订单列表', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), listing, outputs=['id', 'status']),
                    Tool('get_payments', '读取支付信息', 'read', object_schema({'orderId': {'type': 'string'}}), detail('payments'), outputs=['id', 'payments']),
                    Tool('get_items', '读取商品信息', 'read', object_schema({'orderId': {'type': 'string'}}), detail('items'), outputs=['id', 'items']),
                    Tool('publish_report', '发布报告', 'artifact', object_schema(), publish)]
    class Model:
        kind = 'injected'
        def __init__(self, role): self.role, self.model = role, role + '-model'
        async def complete(self, messages, available):
            def result(name=None, args=None):
                message = {'role': 'assistant', 'content': 'done'}
                if name:
                    import json
                    message['tool_calls'] = [dict(id=name, type='function', function=dict(name=name, arguments=json.dumps(args)))]
                return dict(message=message, usage={'input': 5, 'output': 1, 'reasoning': 0}, finishReason='stop')
            if self.role == 'composition':
                return result('submit_coarse_plan', {'subgoals': [dict(id='payments', intent='读取支付信息', dependencies=[]), dict(id='items', intent='读取商品信息', dependencies=[])]})
            if not any(message.get('role') == 'tool' and 'saved' in message.get('content', '') for message in messages):
                return result('publish_report', {})
            return result()
    bank = Bank()
    runner = TaskRunner(bank, lambda role: Model(role))
    source = [workflow('payments-a', 'payments'), workflow('payments-b', 'payments'), workflow('items-a', 'items'), workflow('items-b', 'items')]
    from backend.graph import contract_hash
    available = bank.tools('x')
    for row in source:
        row['contractHash'] = contract_hash(available)
    runner.evolution.workflows = source
    runner.evolution.tiny_edges = mine(source, available)
    run = await runner.start(TaskRunRequest(taskId='target', strategy='graph_rsi'))
    await runner.tasks[run['id']]
    assert run['status'] == 'completed' and run['evaluation']['status'] == 'passed'
    assert run['evolution']['planningPath'] == 'composition'
    assert len(run['compositionPlan']['selectedTinyEdgeIds']) == 2
    assert run['phaseMetrics']['composition']['requests'] == 1 and run['phaseMetrics']['plan']['requests'] == 0
    assert {item['tool'] for item in run['toolTrace'] if item['executor'] == 'graph'} == {'list_orders', 'get_payments', 'get_items'}
    assert all(item['selection'] == 'persistent-tinyedge' for item in run['graphSelection'])
