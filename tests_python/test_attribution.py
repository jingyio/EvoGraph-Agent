from copy import deepcopy
import json

import pytest

from backend.attribution_assets import _extended_expected
from backend.attribution_experiment import ARMS, summarize
from backend.task_runner import TaskRunRequest, TaskRunner
from backend.workspace import WorkspaceBank, WorkspaceManager


def response(tool, arguments):
    return {
        'message': {'content': None, 'tool_calls': [{'id': 'call', 'type': 'function', 'function': {'name': tool, 'arguments': json.dumps(arguments)}}]},
        'usage': {'input': 10, 'output': 5, 'reasoning': 0},
        'usageComplete': True,
        'finishReason': 'tool_calls',
    }


def test_status_extension_uses_current_rows_and_updates_union():
    expected = {'metrics': {'order_count': 2}, 'groups': {'difference': ['o1']}, 'selectedIds': ['o1']}
    inputs = {'orders': [{'order_id': 'o1', 'status': 'delivered'}, {'order_id': 'o2', 'status': 'shipped'}]}
    result = _extended_expected(inputs, expected, True)
    assert result['metrics']['status_review_count'] == 1
    assert result['groups']['status_review'] == ['o2']
    assert result['selectedIds'] == ['o1', 'o2']
    assert expected == {'metrics': {'order_count': 2}, 'groups': {'difference': ['o1']}, 'selectedIds': ['o1']}


def _run(run_id, tokens=100, passed=True, evolution=None):
    return {
        'id': run_id,
        'status': 'completed',
        'evaluation': {'status': 'passed' if passed else 'failed'},
        'metrics': {'inputTokens': tokens, 'outputTokens': 0, 'usageComplete': True, 'durationMs': tokens,
                    'modelRequests': 1, 'toolCalls': 1, 'toolErrors': 0, 'failedReportAttempts': 0},
        'evolution': evolution or {},
        'graph': {'nodeStates': {'t0': 'completed'}},
    }


def test_attribution_summary_requires_same_quality_and_records_later_use():
    manifest = [{'id': 'FA01'}, {'id': 'FA02'}]
    pairs = [
        {'status': 'completed', 'spec': {'id': 'FA01', 'position': 1, 'title': 'one', 'opportunity': 'create', 'sourceTaskId': 'F01'},
         'no_learning': _run('a1'), 'online_rsi': _run('b1', 80, evolution={'generatedVersionIds': ['g0'], 'generatedMatchVersions': []})},
        {'status': 'completed', 'spec': {'id': 'FA02', 'position': 2, 'title': 'two', 'opportunity': 'reuse', 'sourceTaskId': 'F02'},
         'no_learning': _run('a2'), 'online_rsi': _run('b2', 60, evolution={'usedVersionId': 'g0', 'generatedVersionIds': [], 'generatedMatchVersions': []})},
    ]
    result = summarize({'status': 'completed', 'manifest': manifest, 'pairs': pairs})
    assert result['learning']['revisions'] == []
    assert not result['learning']['revisionWithLaterUse']
    assert result['qualityGate'] and result['netTokenSaving'] == pytest.approx(.3)
    assert result['learning']['laterUse'] == [{'taskId': 'FA02', 'versionIds': ['g0']}]
    assert result['points'][0]['cumulativeTokenSaving'] == pytest.approx(.2)
    assert result['points'][1]['cumulativeTokenSaving'] == pytest.approx(.3)


@pytest.mark.asyncio
async def test_group_failure_replays_current_compute_without_private_truth(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance')
    manager.add_source(workspace['id'], 'input.json', json.dumps({
        'orders': [{'order_id': 'o1'}],
        'payments': [{'order_id': 'o1', 'amount_cents': 100, 'installments': 1}],
        'items': [{'order_id': 'o1', 'price_cents': 100, 'freight_cents': 0}],
    }).encode())
    public, questions = manager.create_task(workspace['id'], '复核差额严格超过0.05 BRL，空原因也要说明。', split='train')
    assert not questions
    task = manager.tasks[public['id']]
    task['deliveryContract'] = {
        'requiredMetricKeys': ['order_count', 'difference_count'],
        'requiredGroupNames': ['difference', 'missing_payment'],
        'selectedIdField': 'order_id',
    }
    task['privateValidation'] = {
        'metrics': {'order_count': 1, 'difference_count': 0},
        'groups': {'difference': [], 'missing_payment': []},
        'selectedIds': [],
    }
    manager._persist(manager.workspace(workspace['id']))
    bindings = task['tableBindings']
    seen_messages = []

    class Model:
        model = 'injected'
        settings = {}

        async def complete(self, messages, tools):
            seen_messages.append(deepcopy(messages))
            names = {tool.name for tool in tools}
            receipts = [trace for trace in messages if trace.get('role') == 'tool' and '"totals"' in trace.get('content', '')]
            replayed = any('确定性计算收据' in trace.get('content', '') for trace in messages if trace.get('role') == 'user')
            if not receipts and not replayed:
                return response('workspace_reconcile_keyed_sums', {
                    'anchorTableId': bindings['orders'], 'keyField': 'order_id',
                    'aggregates': [
                        {'tableId': bindings['payments'], 'keyField': 'order_id', 'field': 'amount_cents', 'alias': 'paid'},
                        {'tableId': bindings['items'], 'keyField': 'order_id', 'field': 'price_cents', 'alias': 'price'},
                        {'tableId': bindings['items'], 'keyField': 'order_id', 'field': 'freight_cents', 'alias': 'freight'},
                    ],
                    'derivedTotals': [{'name': 'line', 'aliases': ['price', 'freight']}],
                    'comparisons': [{'name': 'difference', 'leftAlias': 'paid', 'rightAliases': ['line'], 'operator': 'abs_gt', 'threshold': 5}],
                })
            evidence = sorted({
                ref
                for history in seen_messages
                for message in history
                if message.get('role') == 'tool'
                for ref in json.loads(message['content']).get('result', {}).get('evidenceByKey', {}).get('o1', [])
            })
            report = {
                'metrics': {'order_count': 1, 'difference_count': 0}, 'selectedIds': [],
                'evidenceIds': evidence, 'summary': '当前资料复核完成。',
                'groups': [{'name': 'difference', 'reason': '差额', 'condition': '>5 cents', 'count': 0, 'selectedIds': [], 'evidenceIds': []}],
            }
            if replayed:
                report['groups'].append({'name': 'missing_payment', 'reason': '缺支付', 'condition': 'missing', 'count': 0, 'selectedIds': [], 'evidenceIds': []})
            assert 'workspace_publish_report' in names
            return response('workspace_publish_report', report)

    runner = TaskRunner(WorkspaceBank(manager), lambda _: Model(), learning_enabled=False, run_directory=tmp_path / 'runs')
    run = await runner.start(TaskRunRequest(taskId=task['id'], strategy='graph_rsi'))
    await runner.tasks[run['id']]
    await runner.shutdown()
    assert run['status'] == 'completed' and run['evaluation']['status'] == 'passed'
    assert run['metrics']['deterministicFactRecoveryReplays'] == 1
    assert run['reportRecovery']['attempts'][0]['kind'] == 'business_facts'
    serialized = json.dumps(seen_messages, ensure_ascii=False)
    assert 'missing_payment' in serialized and 'privateValidation' not in serialized


def test_no_learning_arm_names_are_explicit():
    assert ARMS == ('no_learning', 'online_rsi')

@pytest.mark.asyncio
async def test_complete_trajectory_residual_enters_report_only_boundary(tmp_path):
    from backend import trajectory

    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance')
    manager.add_source(workspace['id'], 'input.json', json.dumps({
        'orders': [{'order_id': 'o1'}],
        'payments': [{'order_id': 'o1', 'amount_cents': 100}],
        'items': [{'order_id': 'o1', 'price_cents': 100}],
    }).encode())
    public, questions = manager.create_task(
        workspace['id'],
        '复核支付与商品金额差异严格超过0.05 BRL，并保存报告。',
        split='test',
    )
    assert not questions
    task = manager.tasks[public['id']]
    task['deliveryContract'] = {
        'requiredMetricKeys': ['order_count', 'difference_count'],
        'requiredGroupNames': ['difference'],
        'selectedIdField': 'order_id',
    }
    task['privateValidation'] = {
        'metrics': {'order_count': 1, 'difference_count': 0},
        'groups': {'difference': []},
        'selectedIds': [],
    }
    manager._persist(manager.workspace(workspace['id']))
    public_task = manager.task(task['id'])
    tools = manager.tools(task['id'])
    bindings = public_task['tableBindings']
    reconcile_arguments = {
        'anchorTableId': {'$table': 'orders'},
        'keyField': 'order_id',
        'aggregates': [
            {'tableId': {'$table': 'payments'}, 'keyField': 'order_id', 'field': 'amount_cents', 'alias': {'$literal': 'paid'}, 'operation': {'$literal': 'sum'}},
            {'tableId': {'$table': 'items'}, 'keyField': 'order_id', 'field': 'price_cents', 'alias': {'$literal': 'line'}, 'operation': {'$literal': 'sum'}},
        ],
        'comparisons': [{
            'name': {'$literal': 'difference'}, 'leftAlias': {'$literal': 'paid'},
            'rightAliases': [{'$literal': 'line'}], 'operator': {'$literal': 'abs_gt'},
            'threshold': {'$literal': 5},
        }],
    }
    version = {
        'id': 'g0', 'protocol': trajectory.PROTOCOL, 'contractHash': trajectory.api_hash(tools),
        'generation': 0, 'matchVersion': 0, 'reviewed': True,
        'descriptor': {'purpose': public_task['task'], 'schema': public_task['schemaContract'], 'slots': {}},
        'nodes': [{'id': 't0', 'tool': 'workspace_reconcile_keyed_sums', 'arguments': reconcile_arguments,
                   'dependencies': [], 'effect': 'compute', 'paginate': False}],
        'plan': {'steps': [{'id': 't0', 'intent': 'workspace_reconcile_keyed_sums', 'dependencies': []}]},
    }
    calls = []

    class Model:
        model = 'injected'
        settings = {}

        def __init__(self, role):
            self.role = role

        async def complete(self, messages, available):
            names = [tool.name for tool in available]
            calls.append((self.role, names))
            if 'bind_trajectory' in names:
                return response('bind_trajectory', {
                    'graphId': 'g0', 'decision': 'partial', 'nodeIds': ['t0'],
                    'bindings': [], 'reason': '当前条件与轨迹完全兼容', 'uncovered': [],
                })
            assert names == ['workspace_publish_report']
            observed = sorted(
                ref
                for message in messages if message.get('role') == 'tool'
                for ref in json.loads(message['content']).get('result', {}).get('evidenceByKey', {}).get('o1', [])
            )
            return response('workspace_publish_report', {
                'metrics': {'order_count': 1, 'difference_count': 0},
                'groups': [{'name': 'difference', 'reason': '金额一致', 'condition': '> 5 cents',
                            'count': 0, 'selectedIds': [], 'evidenceIds': []}],
                'selectedIds': [], 'evidenceIds': observed, 'summary': '本次资料金额一致。',
            })

    runner = TaskRunner(
        WorkspaceBank(manager), lambda role: Model(role), learning_enabled=False,
        run_directory=tmp_path / 'runs', evolution_path=tmp_path / 'experience.json',
    )
    runner.evolution.versions = [version]
    run = await runner.start(TaskRunRequest(taskId=task['id'], strategy='graph_rsi'))
    await runner.tasks[run['id']]
    await runner.shutdown()
    assert run['status'] == 'completed' and run['evaluation']['status'] == 'passed'
    assert run['metrics']['modelRequests'] == 2
    assert run['phaseMetrics']['match']['requests'] == 1
    assert run['phaseMetrics']['execute']['requests'] == 1
    assert any(event['type'] == 'trajectory_report_boundary' for event in run['events'])
    assert calls[-1] == ('executor', ['workspace_publish_report'])
