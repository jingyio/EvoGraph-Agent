"""AutoTool inertia protocol tests with injected observations, not benchmark claims."""
import asyncio
import json
from backend.tools import Tool, object_schema
from backend.tool_inertia import attempt, empty, update
from backend.task_runner import TaskRunner, TaskRunRequest


def toolset():
    return [
        Tool('list_records', '列出当前记录 ID', 'read', object_schema({'page': {'type': 'integer'}}), lambda args, ctx: {'records': [{'id': 'current'}]}),
        Tool('get_record', '读取当前记录状态', 'read', object_schema({'recordId': {'type': 'string'}}), lambda args, ctx: {'id': args['recordId'], 'state': 'open'}),
        Tool('publish_report', '发布报告', 'artifact', object_schema(), lambda args, ctx: {'saved': True}),
    ]


def event(seq, kind, title, detail):
    return dict(seq=seq, type=kind, title=title, detail=detail)


def model_run():
    return dict(id='train-run', evaluation={'status': 'passed'}, events=[
        event(1, 'action', 'list_records', {'callId': 'a', 'executor': 'model', 'arguments': '{"page": 1}'}),
        event(2, 'observation', 'list_records', {'callId': 'a', 'executor': 'model', 'ok': True, 'result': {'records': [{'id': 'current'}]}}),
        event(3, 'action', 'get_record', {'callId': 'b', 'executor': 'model', 'arguments': '{"recordId": "current"}'}),
        event(4, 'observation', 'get_record', {'callId': 'b', 'executor': 'model', 'ok': True, 'result': {'id': 'current', 'state': 'open'}}),
    ])


def runtime_run():
    return dict(toolTrace=[], events=[
        event(1, 'action', 'list_records', {'callId': 'g', 'executor': 'graph', 'arguments': '{"page": 1}'}),
        event(2, 'observation', 'list_records', {'callId': 'g', 'executor': 'graph', 'ok': True, 'result': {'records': [{'id': 'current'}]}}),
    ])


def test_train_only_model_serial_paths_and_parameter_contracts_are_learned():
    store = empty()
    info = update(store, model_run(), {'id': 'train-task', 'split': 'train'}, toolset())
    assert info['updatedPaths'] == info['updatedParameterEdges'] == 1
    assert store['toolPaths'][0]['tools'] == ['list_records', 'get_record']
    assert store['parameterEdges'][0]['sourcePath'] == ['records', '*', 'id']
    graph_only = model_run()
    for row in graph_only['events']:
        row['detail']['executor'] = 'graph'
    assert update(store, graph_only, {'id': 'train-graph', 'split': 'train'}, toolset())['updatedPaths'] == 0
    assert update(store, model_run(), {'id': 'validation-task', 'split': 'validation'}, toolset())['updatedPaths'] == 0


def test_current_observation_binding_requires_unique_type_valid_nonduplicate_value():
    store = empty()
    store['toolPaths'] = [dict(tools=['list_records', 'get_record'], support=10, sourceRunIds=['a'], sourceTaskIds=['x'])]
    store['parameterEdges'] = [dict(sourceTool='list_records', sourcePath=['records', '*', 'id'], targetTool='get_record', targetParameter='recordId', support=10, sourceRunIds=['a'], sourceTaskIds=['x'])]
    run = runtime_run()
    accepted = attempt(store, run, '读取当前记录状态', toolset())
    assert accepted['accepted'] and json.loads(accepted['call']['function']['arguments']) == {'recordId': 'current'}
    run['events'][1]['detail']['result']['records'].append({'id': 'other'})
    assert attempt(store, run, '读取当前记录状态', toolset())['reason'].startswith('parameter_missing_or_ambiguous')
    run = runtime_run()
    run['toolTrace'].append(dict(signature='["get_record",{"recordId":"current"}]', ok=True))
    assert attempt(store, run, '读取当前记录状态', toolset())['reason'] == 'duplicate_successful_call'


def test_concurrent_batch_does_not_supply_an_inertia_sequence():
    store = empty()
    store['toolPaths'] = [dict(tools=['list_records', 'get_record'], support=10, sourceRunIds=['a'], sourceTaskIds=['x'])]
    run = dict(toolTrace=[], events=[
        event(1, 'action', 'list_records', {'callId': 'a', 'executor': 'graph', 'arguments': '{"page": 1}'}),
        event(2, 'action', 'list_records', {'callId': 'b', 'executor': 'graph', 'arguments': '{"page": 2}'}),
        event(3, 'observation', 'list_records', {'callId': 'b', 'executor': 'graph', 'ok': True, 'result': {'records': [{'id': 'b'}]}}),
        event(4, 'observation', 'list_records', {'callId': 'a', 'executor': 'graph', 'ok': True, 'result': {'records': [{'id': 'a'}]}}),
    ])
    rejected = attempt(store, run, '读取当前记录状态', toolset())
    assert rejected['recentTools'] == [] and rejected['reason'] == 'no_current_tool_context'


async def test_motif_first_executes_one_inertial_read_then_returns_to_model(tmp_path):
    class Bank:
        root = tmp_path
        manifest = {'source': 'injected-inertia-regression'}
        def task(self, key):
            return dict(id=key, scenario='tickets', family='inertia', split='validation', task='读取当前记录状态并发布结果', suggestedBudget={'toolCalls': 20})
        def tools(self, key):
            def listing(args, ctx):
                ctx.evidence.add(key)
                return {'records': [{'id': 'current'}]}
            def detail(args, ctx): return {'id': args['recordId'], 'state': 'open'}
            def publish(args, ctx):
                ctx.run['evaluation'] = dict(status='passed' if key in ctx.evidence else 'failed', issues=[])
                return {'saved': True}
            return [Tool('list_records', '列出当前记录 ID', 'read', object_schema({'page': {'type': 'integer'}}), listing, outputs=['id']),
                    Tool('get_record', '读取当前记录状态', 'read', object_schema({'recordId': {'type': 'string'}}), detail, outputs=['id', 'state']),
                    Tool('publish_report', '发布报告', 'artifact', object_schema(), publish)]
    class Model:
        def __init__(self, role): self.role, self.model = role, role + '-model'
        async def complete(self, messages, available):
            seen_detail = any(message.get('role') == 'tool' and '"state": "open"' in message.get('content', '') for message in messages)
            seen_publish = any(message.get('role') == 'tool' and '"saved": true' in message.get('content', '') for message in messages)
            if seen_publish:
                return dict(message=dict(role='assistant', content='done'), usage=dict(input=5, output=1, reasoning=0), finishReason='stop')
            name, args = ('publish_report', {}) if seen_detail else ('get_record', {'recordId': 'current'})
            return dict(message=dict(role='assistant', content='done', tool_calls=[dict(id=name, type='function', function=dict(name=name, arguments=json.dumps(args)))]), usage=dict(input=5, output=1, reasoning=0), finishReason='stop')
    runner = TaskRunner(Bank(), lambda role: Model(role))
    runner.evolution.tool_inertia = dict(schemaVersion=1,
        toolPaths=[dict(tools=['list_records', 'get_record'], support=10, sourceRunIds=['train-a'], sourceTaskIds=['train-a'])],
        parameterEdges=[dict(sourceTool='list_records', sourcePath=['records', '*', 'id'], targetTool='get_record', targetParameter='recordId', support=10, sourceRunIds=['train-a'], sourceTaskIds=['train-a'])])
    graph = dict(id='frozen', generation=0, plan={'steps': [dict(id='list', intent='列出当前记录 ID', dependencies=[]), dict(id='detail', intent='读取当前记录状态', dependencies=['list'])]}, nodes=[
        dict(id='list', tool='list_records', arguments={'page': {'kind': 'literal', 'value': 1}}, dependencies=[]),
        dict(id='detail', tool='get_record', arguments={}, dependencies=['list'], defer=True),
    ])
    run = await runner.start(TaskRunRequest(taskId='case', strategy='motif_first'), evaluation_context={'graphSnapshot': graph})
    await runner.tasks[run['id']]
    assert run['evaluation']['status'] == 'passed'
    assert run['metrics']['inertiaAttempts'] == run['metrics']['inertiaAccepted'] == run['metrics']['inertiaCalls'] == 1
    # Motif Only would ask for detail, publish, then finish. The inertial detail
    # leaves the existing model loop with publish and finish only.
    assert run['metrics']['modelRequests'] == 2
    assert [row['executor'] for row in run['toolTrace']] == ['graph', 'inertia', 'model']
    assert run['toolInertia']['attempts'][0]['bindings'][0]['sourcePath'] == ['records', '*', 'id']
