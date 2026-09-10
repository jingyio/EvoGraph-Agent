"""Protocol tests with injected tools/models, not real-data benchmark results."""
from copy import deepcopy
import json
import pytest
from backend.tools import Tool, object_schema
from backend.task_runner import TaskRunner, TaskRunRequest
from backend.intent_graph import execute_graph
from backend.graph import ordered_nodes


class Bank:
    manifest = {'source': 'injected-regression-only'}

    def __init__(self, root):
        self.root = root
        self.missing = False
        self.invalid_list_id = False

    def task(self, key):
        return dict(id=key, scenario='tickets', family='states', split='test' if key.startswith('test') else 'validation' if key.startswith('val') else 'train',
                    task='读取 state 并发布结果', suggestedBudget={'toolCalls': 80})

    def tools(self, key):
        def listing(args, ctx):
            ctx.evidence.add(key)
            row = {'id': key}
            if not self.missing:
                row['state'] = 'open'
            if self.invalid_list_id:
                row['id'] = 123
            return {'records': [row], 'mayHaveMore': False}
        def detail(args, ctx):
            return {'id': args['issueId'], 'state': 'open'}
        def publish(args, ctx):
            ctx.run['evaluation'] = dict(status='passed' if key in ctx.evidence else 'failed', issues=[])
            return {'saved': True}
        return [Tool('tickets_list_issues', '分页列出工单', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), listing, outputs=['id', 'state']),
                Tool('tickets_get_issue', '读取 state', 'read', object_schema({'issueId': {'type': 'string'}}), detail, outputs=['id', 'state']),
                Tool('tickets_publish_report', '发布', 'artifact', object_schema(), publish)]


class Model:
    model = 'injected-test-model'
    def __init__(self, role):
        self.role = role
    async def complete(self, messages, tools):
        def response(name=None, args=None):
            msg = dict(role='assistant', content='done')
            if name:
                msg['tool_calls'] = [dict(id='call-' + str(len(messages)), type='function', function=dict(name=name, arguments=json.dumps(args)))]
            return dict(message=msg, usage=dict(input=10, output=2, reasoning=0), finishReason='stop')
        if self.role == 'planner':
            return response('submit_plan', {'steps': [dict(id='list', intent='分页列出工单', dependencies=[]), dict(id='state', intent='读取 state', dependencies=['list'])]})
        observations = [json.loads(m['content']) for m in messages if m['role'] == 'tool']
        handoff = any('以下读取子图已交给模型' in str(m.get('content')) for m in messages)
        has_detail = any(o.get('result', {}).get('id') == '123' for o in observations)
        if (observations and observations[-1].get('ok') is False) or (handoff and not has_detail):
            return response('tickets_get_issue', {'issueId': '123'})
        if not any(o.get('result', {}).get('saved') for o in observations):
            return response('tickets_publish_report', {})
        return response()


async def run(runner, key):
    r = await runner.start(TaskRunRequest(taskId=key, strategy='graph_rsi'))
    await runner.tasks[r['id']]
    assert 'maintenanceError' not in r.get('evolution', {})
    return r


async def test_natural_tasks_generate_child_reuse_skip_plan_and_freeze_test(tmp_path):
    bank = Bank(tmp_path)
    runner = TaskRunner(bank, lambda role: Model(role))
    first = await run(runner, 'train-1')
    versions = runner.evolution.versions
    assert len(versions) == 1
    child = versions[0]
    assert child['nodes'][1]['reuse']['onMissing'] == 'detail'
    assert first['metrics']['toolCalls'] == 2
    second = await run(runner, 'train-2')
    assert second['evolution']['usedVersionId'] == child['id']
    assert second['phaseMetrics']['plan']['requests'] == 0
    assert second['metrics']['toolCalls'] == 2 and second['metrics']['elidedToolCalls'] == 1
    assert len(versions) == 1  # No fabricated generation from unchanged structure.
    bank.missing = True
    third = await run(runner, 'train-3')
    assert third['metrics']['recoveryToolCalls'] == 1 and third['metrics']['elidedToolCalls'] == 0
    assert third['evaluation']['status'] == 'passed'
    fourth = await run(runner, 'val-1')
    assert child['status'] == 'family-supported'
    frozen = deepcopy(versions)
    frozen_bytes = runner.evolution.path.read_bytes()
    test_run = await run(runner, 'test-1')
    assert test_run['phaseMetrics']['plan']['requests'] == 0
    assert versions == frozen and runner.evolution.path.read_bytes() == frozen_bytes
    assert all(r['evolution']['shadowRollouts'] == r['evolution']['extraModelRequests'] == r['evolution']['extraToolCalls'] == 0 for r in [first, second, third, fourth, test_run])
    restored = TaskRunner(bank, lambda role: Model(role))
    restored.restore()
    assert restored.evolution.versions == versions
    bank.manifest = {'source': 'changed'}
    assert restored.evolution.select(bank.task('train-4'), bank.tools('train-4')) is None


async def test_failed_graph_then_model_repair_creates_successor_not_parent_rollback(tmp_path):
    bank = Bank(tmp_path)
    runner = TaskRunner(bank, lambda role: Model(role))
    await run(runner, 'train-1')
    old = runner.evolution.versions[-1]
    bank.missing = bank.invalid_list_id = True
    failed_graph = await run(runner, 'train-2')
    assert failed_graph['fallback'] and failed_graph['evaluation']['status'] == 'passed'
    child = runner.evolution.versions[-1]
    assert len(runner.evolution.versions) == 2
    assert child['parentGraphId'] == old['id']
    assert child['patches'][0]['operation'] == 'defer_subgraph'
    assert old['status'] == 'needs-repair'
    later = await run(runner, 'train-3')
    assert later['evolution']['usedVersionId'] == child['id']
    assert later['graph']['nodeStates']['state'] == 'model-handoff'
    assert later['phaseMetrics']['plan']['requests'] == 0
    assert any(t['tool'] == 'tickets_get_issue' and t['executor'] == 'model' and t['ok'] for t in later['toolTrace'])
    # The graph preserves the successful list; it does not restart its parent.
    assert sum(t['tool'] == 'tickets_list_issues' for t in later['toolTrace']) == 1


async def test_validation_cannot_create_graph_and_unknown_failure_does_not_invent_patch(tmp_path):
    bank = Bank(tmp_path)
    runner = TaskRunner(bank, lambda role: Model(role))
    await run(runner, 'val-1')
    assert runner.evolution.versions == []
    first = await run(runner, 'train-1')
    before = len(runner.evolution.versions)
    fake = deepcopy(first)
    fake.update(id='unexplained', status='failed', evaluation=dict(status='failed', issues=['missing_report']))
    fake['evolution'] = dict(usedVersionId=runner.evolution.versions[-1]['id'])
    runner.evolution.observe(fake, bank.task('train-1'), bank.tools('train-1'))
    assert len(runner.evolution.versions) == before
    assert runner.evolution.versions[-1]['status'] == 'needs-repair'
    assert runner.evolution.select(bank.task('train-1'), bank.tools('train-1')) is None


async def test_guarded_reuse_only_reads_missing_ids_and_checks_shapes(tmp_path):
    bank = Bank(tmp_path)
    tools = bank.tools('x')
    nodes = [dict(id='list', tool='tickets_list_issues', arguments={}, dependencies=[]),
             dict(id='state', tool='tickets_get_issue', arguments={}, dependencies=['list'],
                  reuse=dict(nodeId='list', collectionPath=['records'], fields=['state'], onMissing='detail'))]
    calls, skipped = [], []
    async def invoke(name, args, node):
        calls.append((name, args))
        if node == 'list':
            return {'records': [{'id': 'a', 'state': None}, {'id': 'b'}, {'id': 'b'}]}
        return {'id': args['issueId'], 'state': 'open'}
    outputs = await execute_graph(nodes, tools, invoke, lambda *a: None, lambda node, count: skipped.append(count))
    assert calls == [('tickets_list_issues', {}), ('tickets_get_issue', {'issueId': 'b'})]
    assert skipped == [1]  # Null is a present value, not a missing field.
    assert outputs['state'][0]['records'][1]['state'] == 'open'
    assert 'state' not in outputs['list'][0]['records'][1]  # No mutation of source observations.
    nodes[1]['reuse'].pop('onMissing')
    with pytest.raises(ValueError, match='字段缺失'):
        await execute_graph(nodes, tools, invoke, lambda *a: None)
    nodes[0]['defer'] = True
    with pytest.raises(ValueError, match='全部下游'):
        ordered_nodes(nodes, tools)


async def test_observed_unoptimized_graph_can_generate_one_guarded_patch(tmp_path):
    bank = Bank(tmp_path)
    runner = TaskRunner(bank, lambda role: Model(role))
    source = await run(runner, 'train-1')
    # Explicit unit fixture for an older conservative graph; runtime does not force
    # unnecessary calls merely to manufacture an evolution curve.
    source = deepcopy(source)
    source['id'] = 'old-training-trace'
    source['evolution'] = {}
    node = source['graph']['nodes'][1]
    node.pop('reuse')
    node.update(arguments={'issueId': {'kind': 'item', 'path': ['id']}}, foreach={'nodeId': 'list', 'collectionPath': ['records']})
    runner.evolution.versions = []
    runner.evolution.observe(source, bank.task('train-1'), bank.tools('train-1'))
    parent, child = runner.evolution.versions
    assert child['parentGraphId'] == parent['id']
    assert child['patches'][0]['operation'] == 'reuse_with_fallback'
    assert child['nodes'][1]['reuse']['onMissing'] == 'detail'
    bank.missing = bank.invalid_list_id = True
    recovered = await run(runner, 'train-2')
    repaired = runner.evolution.versions[-1]
    assert recovered['evaluation']['status'] == 'passed'
    assert repaired['parentGraphId'] == child['id'] and repaired['generation'] == 2
    assert repaired['patches'][0]['operation'] == 'defer_subgraph'
    later = await run(runner, 'train-3')
    assert later['evolution']['usedVersionId'] == repaired['id']
    count = len(runner.evolution.versions)
    stale = deepcopy(recovered)
    stale['id'] = 'late-parallel-feedback'
    stale['evolution'] = dict(usedVersionId=child['id'])
    runner.evolution.observe(stale, bank.task('train-2'), bank.tools('train-2'))
    assert len(runner.evolution.versions) == count
    assert runner.evolution.select(bank.task('train-4'), bank.tools('train-4'))['id'] == repaired['id']
