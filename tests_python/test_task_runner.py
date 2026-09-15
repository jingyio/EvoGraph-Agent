import asyncio
from copy import deepcopy
import json
import time
import pytest
import httpx
from backend.app import create_app
from backend.service import RunService
from backend.task_runner import TaskRunner, TaskRunRequest
from backend.tools import Tool, object_schema


class Bank:
    def __init__(self, root):
        self.root = root
    def load(self):
        pass
    def task(self, key):
        return dict(id=key, scenario='finance', split='train', task='读取记录并发布结果', suggestedBudget={'toolCalls': 80})
    def tools(self, key):
        def listing(args, ctx):
            time.sleep(.015)
            ctx.evidence.add(key)
            return {'records': [{'id': key}], 'mayHaveMore': False}
        def publish(args, ctx):
            ctx.run['evaluation'] = {'status': 'passed' if ctx.evidence == {key} else 'failed', 'issues': []}
            return {'saved': True}
        return [Tool('finance_list_orders', '分页列出订单 ID', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), listing),
                Tool('finance_publish_report', '发布报告', 'artifact', object_schema(), publish)]


def result(name=None, args=None):
    msg = {'role': 'assistant', 'content': 'done'}
    if name:
        msg['tool_calls'] = [{'id': name, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]
    return {'message': msg, 'usage': {'input': 10, 'output': 2, 'reasoning': 0}, 'finishReason': 'stop'}


class Model:
    def __init__(self, role, histories):
        self.model, self.role, self.histories = role, role, histories
    async def complete(self, messages, tools):
        self.histories.append(deepcopy(messages))
        await asyncio.sleep(.005)
        if self.role == 'planner':
            return result('submit_plan', {'steps': [{'id': 'list', 'intent': '分页列出订单 ID', 'dependencies': []}]})
        if tools[0].name == 'submit_graph':
            return result('submit_graph', {'nodes': [{'id': 'list', 'tool': 'finance_list_orders'}]})
        if not any(m.get('tool_call_id') == 'finance_publish_report' for m in messages):
            return result('finance_publish_report', {})
        return result()


async def test_phase_routing_queue_isolation_and_bounded_concurrency(tmp_path):
    histories = []
    runner = TaskRunner(Bank(tmp_path), lambda role: Model(role, histories), run_limit=2, model_limit=1, read_limit=1)
    jobs = [await runner.start(TaskRunRequest(taskId='task-' + str(i))) for i in range(5)]
    await asyncio.gather(*list(runner.tasks.values()))
    assert all(r['status'] == 'completed' and r['evaluation']['status'] == 'passed' for r in jobs)
    assert runner.peaks == dict(runs=2, models=1, reads=1)
    assert jobs[-1]['metrics']['queueMs'] > 0
    for run in jobs:
        assert run['phaseMetrics']['plan']['requests'] == 1 and run['phaseMetrics']['graph']['requests'] == 0
        assert run['metrics']['modelRequests'] == 2 and run['metrics']['inputTokens'] == 20
        assert run['models']['distinctModels'] and run['graph']['status'] == 'done'
        assert run['metrics']['toolCalls'] == 2
        assert run['metrics']['reportSelectionCanonicalizations'] == 0
        assert run['graphSelection'][0]['selection'] == 'local-retrieval-and-contract'
    assert not runner.tasks
    restored = TaskRunner(Bank(tmp_path), lambda role: Model(role, []))
    restored.restore()
    assert len(restored.runs) == 5


async def test_bad_plan_falls_back_and_counts_planner_request(tmp_path):
    class Invalid(Model):
        async def complete(self, messages, tools):
            if self.role == 'planner':
                return result()
            if not any(m.get('role') == 'tool' for m in messages):
                return result('finance_list_orders', {'page': 1, 'pageSize': 50})
            return await super().complete(messages, tools)
    runner = TaskRunner(Bank(tmp_path), lambda role: Invalid(role, []))
    run = await runner.start(TaskRunRequest(taskId='x'))
    await runner.tasks[run['id']]
    assert run['evaluation']['status'] == 'passed' and run['fallback']
    assert run['phaseMetrics']['plan']['requests'] == 1


async def test_transport_retry_is_accounted_as_provider_attempt_and_marks_usage_incomplete(tmp_path):
    class RetriedExecutor(Model):
        async def complete(self, messages, tools):
            response = await super().complete(messages, tools)
            if self.role == 'executor':
                response['transportRetries'] = 1
                response['usageComplete'] = False
            return response

    runner = TaskRunner(Bank(tmp_path), lambda role: RetriedExecutor(role, []), learning_enabled=False)
    run = await runner.start(TaskRunRequest(taskId='retry'))
    await runner.tasks[run['id']]
    assert run['status'] == 'completed'
    assert run['metrics']['modelRequests'] == 2
    assert run['metrics']['modelProviderAttempts'] == 3
    assert run['metrics']['modelTransportRetries'] == 1
    assert run['metrics']['usageComplete'] is False
    assert any(event['type'] == 'model_retry' and event['detail']['outcome'] == 'recovered' for event in run['events'])


async def test_current_intent_can_refresh_tool_candidates(tmp_path):
    class Rediscover(Model):
        async def complete(self, messages, tools):
            if self.role == 'executor' and tools[0].name != 'submit_graph' and not any(m.get('tool_call_id') == 'request_tools' for m in messages):
                return result('request_tools', {'intent': '分页列出订单 ID'})
            return await super().complete(messages, tools)
    runner = TaskRunner(Bank(tmp_path), lambda role: Rediscover(role, []))
    run = await runner.start(TaskRunRequest(taskId='x'))
    await runner.tasks[run['id']]
    assert run['evaluation']['status'] == 'passed' and run['metrics']['retrievalCalls'] == 1
    assert any(e['type'] == 'retrieval' for e in run['events'])


async def test_failed_publish_recovery_is_bounded_and_shared_with_baseline(tmp_path):
    histories = []
    class FailedReportBank(Bank):
        def tools(self, key):
            def publish(args, ctx):
                ctx.run['evaluation'] = dict(status='failed', issues=['evidence_coverage'])
                return {'saved': True, 'evaluation': ctx.run['evaluation']}
            return [Tool('finance_publish_report', '发布报告', 'artifact', object_schema(), publish)]
    class FailedReportModel(Model):
        async def complete(self, messages, tools):
            histories.append([tool.name for tool in tools])
            return result('finance_publish_report', {})
    runner = TaskRunner(FailedReportBank(tmp_path), lambda role: FailedReportModel(role, []))
    run = await runner.start(TaskRunRequest(taskId='bounded', strategy='react'))
    await runner.tasks[run['id']]
    assert run['status'] == 'limited' and run['evaluation']['status'] == 'failed'
    assert run['metrics']['reportAttempts'] == run['metrics']['failedReportAttempts'] == 2
    assert run['reportRecovery']['termination'] in ['repeated_signature', 'max_failed_publish_attempts']
    assert histories == [['finance_publish_report'], ['finance_publish_report']]


def test_report_evidence_canonicalization_requires_complete_observations():
    task = dict(scenario='finance', recordIds=['order-2', 'order-1'])
    supplied = dict(metrics={'count': 2}, selectedIds=['order-1'], evidenceIds=['typo'], summary='unchanged business result')
    normalized, detail = TaskRunner.canonical_report_evidence(task, 'finance_publish_report', supplied,
                                                               {'finance:order-1', 'finance:order-2'})
    assert normalized['evidenceIds'] == ['finance:order-1', 'finance:order-2']
    assert normalized['metrics'] == supplied['metrics']
    assert normalized['selectedIds'] == supplied['selectedIds']
    assert normalized['summary'] == supplied['summary']
    assert detail['suppliedEvidenceIds'] == ['typo']

    unchanged, missing = TaskRunner.canonical_report_evidence(task, 'finance_publish_report', supplied, {'finance:order-1'})
    assert unchanged == supplied
    assert missing is None


def test_report_selection_canonicalization_uses_only_submitted_groups():
    task = {'deliveryContract': {'selectedIdsPolicy': 'union_of_groups'}}
    supplied = {
        'selectedIds': ['all', 'records'],
        'groups': [
            {'name': 'a', 'selectedIds': ['two', 'one']},
            {'name': 'b', 'selectedIds': ['two', 'three']},
        ],
        'metrics': {'count': 3},
    }
    normalized, detail = TaskRunner.canonical_report_selection(
        task, 'support_publish_report', supplied,
    )
    assert normalized['selectedIds'] == ['one', 'three', 'two']
    assert normalized['groups'] == supplied['groups']
    assert normalized['metrics'] == supplied['metrics']
    assert detail['suppliedSelectedIds'] == ['all', 'records']
    unchanged, missing = TaskRunner.canonical_report_selection(
        {}, 'support_publish_report', supplied,
    )
    assert unchanged == supplied
    assert missing is None


def test_runtime_overhead_is_a_separate_non_token_ledger():
    run = dict(metrics=dict(bindingMs=.5), evolution=dict(lookupMs=1, localCompileMs=5,
                                                           compositionLocalMs=2, compositionModelWallMs=200,
                                                           compositionWallMs=202, maintenanceMs=3, persistMs=.25))
    ledger = TaskRunner.runtime_overhead(run)
    assert ledger['tokenCost'] == 0
    assert ledger['totalMs'] == 11.75
    assert ledger['coldGraphCompileMs'] == 5
    assert 'compositionModelWallMs' not in ledger


def test_pagination_guard_requires_sequential_same_size_pages():
    assert TaskRunner.pagination_violation(None, {'page': 1, 'pageSize': 50}) is None
    first = dict(page=1, pageSize=50, mayHaveMore=True)
    assert TaskRunner.pagination_violation(first, {'page': 2, 'pageSize': 10}) == '分页 continuation 必须沿用上一页 pageSize'
    assert TaskRunner.pagination_violation(first, {'page': 3, 'pageSize': 50}) == '分页 continuation 必须紧接上一页 page'
    assert TaskRunner.pagination_violation(first, {'page': 2, 'pageSize': 50}) is None
    assert TaskRunner.pagination_violation(dict(page=2, pageSize=50, mayHaveMore=False), {'page': 3, 'pageSize': 50}) == '上一页已声明没有更多记录，拒绝不必要的分页读取'


async def test_complete_report_evidence_is_canonicalized_for_baseline_and_graph_rsi(tmp_path):
    class EvidenceBank(Bank):
        def task(self, key):
            return dict(id=key, scenario='finance', family='evidence', split='train', recordIds=['one', 'two'],
                        task='读取全部记录并发布结果', suggestedBudget={'toolCalls': 80})
        def tools(self, key):
            def listing(args, ctx):
                ctx.evidence.update({'finance:one', 'finance:two'})
                return {'records': [{'id': 'one'}, {'id': 'two'}], 'mayHaveMore': False}
            def publish(args, ctx):
                ctx.run['submission'] = deepcopy(args)
                ctx.run['evaluation'] = dict(status='passed' if args['evidenceIds'] == ['finance:one', 'finance:two'] else 'failed', issues=[])
                return {'saved': True, 'evaluation': ctx.run['evaluation']}
            return [Tool('finance_list_orders', '分页列出订单 ID', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), listing,
                         outputs=['id']),
                    Tool('finance_publish_report', '发布报告', 'artifact', object_schema({
                        'metrics': object_schema({'count': {'type': 'integer'}}),
                        'selectedIds': {'type': 'array', 'items': {'type': 'string'}},
                        'evidenceIds': {'type': 'array', 'items': {'type': 'string'}},
                        'summary': {'type': 'string'},
                    }), publish)]

    class EvidenceModel(Model):
        async def complete(self, messages, tools):
            if self.role == 'planner':
                return await super().complete(messages, tools)
            if any(message.get('tool_call_id') == 'finance_publish_report' for message in messages):
                return result()
            if not any(message.get('role') == 'tool' for message in messages):
                return result('finance_list_orders', {'page': 1, 'pageSize': 50})
            return result('finance_publish_report', dict(metrics={'count': 2}, selectedIds=['one'], evidenceIds=['mistyped'], summary='kept'))

    for strategy in ['plan_react', 'graph_rsi']:
        runner = TaskRunner(EvidenceBank(tmp_path / strategy), lambda role: EvidenceModel(role, []), learning_enabled=False)
        run = await runner.start(TaskRunRequest(taskId='evidence', strategy=strategy))
        await runner.tasks[run['id']]
        assert run['evaluation']['status'] == 'passed'
        assert run['submission'] == dict(metrics={'count': 2}, selectedIds=['one'],
                                         evidenceIds=['finance:one', 'finance:two'], summary='kept')
        assert run['metrics']['reportEvidenceCanonicalizations'] == 1
        assert any(event['type'] == 'report_evidence' for event in run['events'])


async def test_equivalent_graph_nodes_merge_without_stale_selection_fallback(tmp_path):
    class DuplicateBank(Bank):
        def task(self, key):
            return dict(id=key, scenario='finance', family='duplicate', split='train', recordIds=['one'],
                        task='列出本任务订单并读取订单状态后发布报告', suggestedBudget={'toolCalls': 10})
        def tools(self, key):
            def listing(args, ctx):
                ctx.evidence.add('finance:one')
                return {'records': [{'id': 'one', 'status': 'canceled', '_evidenceRef': 'finance:one'}], 'page': 1, 'mayHaveMore': False}
            def detail(args, ctx):
                ctx.evidence.add('finance:one')
                return {'id': args['orderId'], 'status': 'canceled', '_evidenceRef': 'finance:one'}
            def publish(args, ctx):
                ctx.run['evaluation'] = dict(status='passed', issues=[])
                return {'saved': True, 'evaluation': ctx.run['evaluation']}
            return [
                Tool('finance_list_orders', '列出订单 ID 和状态', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), listing, outputs=['id', 'status']),
                Tool('finance_get_order', '读取订单状态', 'read', object_schema({'orderId': {'type': 'string'}}), detail, outputs=['id', 'status']),
                Tool('finance_publish_report', '发布报告', 'artifact', object_schema({'evidenceIds': {'type': 'array', 'items': {'type': 'string'}}}), publish),
            ]
    class DuplicateModel(Model):
        async def complete(self, messages, tools):
            if self.role == 'planner':
                return result('submit_plan', {'steps': [
                    {'id': 'list', 'intent': '列出订单 ID 和状态', 'dependencies': []},
                    {'id': 'first_detail', 'intent': '读取订单状态', 'dependencies': ['list']},
                    {'id': 'second_detail', 'intent': '读取订单状态', 'dependencies': ['list']},
                ]})
            if any(message.get('tool_call_id') == 'finance_publish_report' for message in messages):
                return result()
            return result('finance_publish_report', {'evidenceIds': ['finance:one']})
    runner = TaskRunner(DuplicateBank(tmp_path), lambda role: DuplicateModel(role, []))
    run = await runner.start(TaskRunRequest(taskId='duplicate', strategy='graph_rsi'))
    await runner.tasks[run['id']]
    assert run['evaluation']['status'] == 'passed'
    assert run.get('fallback') is None
    assert run['graph']['status'] == 'done'
    assert len(run['graph']['nodes']) == 2
    assert len(run['graphSelection']) == 2


async def test_plan_and_execution_receive_task_derived_inclusive_constraint(tmp_path):
    histories = []
    class InclusiveBank(Bank):
        def task(self, key):
            return dict(id=key, scenario='finance', family='installments', split='train',
                        task='找出支付记录分期数达到 6 的订单并发布结果', suggestedBudget={'toolCalls': 80})
    class InclusiveModel(Model):
        async def complete(self, messages, tools):
            histories.append(deepcopy(messages))
            if self.role == 'planner':
                return await super().complete(messages, tools)
            if any(message.get('tool_call_id') == 'finance_publish_report' for message in messages):
                return result()
            if not any(message.get('role') == 'tool' for message in messages):
                return result('finance_list_orders', {'page': 1, 'pageSize': 50})
            return result('finance_publish_report', {})
    runner = TaskRunner(InclusiveBank(tmp_path), lambda role: InclusiveModel(role, histories), learning_enabled=False)
    run = await runner.start(TaskRunRequest(taskId='inclusive', strategy='plan_react'))
    await runner.tasks[run['id']]
    assert run['evaluation']['status'] == 'passed'
    assert run['semanticConstraints'] == ['任务中的“达到 6”是包含式比较，必须按 >= 6 解释，不能缩窄为等于 6。']
    assert run['metrics']['semanticConstraintGuards'] == 1
    assert any('>= 6' in message.get('content', '') for history in histories for message in history if message.get('role') == 'user')


async def test_ratio_task_cannot_publish_without_a_successful_weighted_reconciliation(tmp_path):
    class RatioBank(Bank):
        def task(self, key):
            return dict(id=key, scenario='finance', split='train',
                        task='找出运费达到商品金额 20% 的订单并发布结果', suggestedBudget={'toolCalls': 80})

        def tools(self, key):
            def reconcile(args, ctx):
                assert args['comparisons'][0]['rightTerms'] == [{'alias': 'price', 'multiplier': .2}]
                ctx.evidence.add('finance:ratio')
                return {'comparisons': [{'keys': ['one']}]}

            def publish(args, ctx):
                passed = ctx.evidence == {'finance:ratio'}
                ctx.run['evaluation'] = {'status': 'passed' if passed else 'failed',
                                         'issues': [] if passed else ['metrics']}
                return {'saved': True, 'evaluation': ctx.run['evaluation']}

            return [
                Tool('workspace_reconcile_keyed_sums', '按键确定性对账', 'compute', object_schema({
                    'anchorTableId': {'type': 'string'}, 'keyField': {'type': 'string'},
                    'aggregates': {'type': 'array'}, 'comparisons': {'type': 'array'},
                }), reconcile),
                Tool('workspace_publish_report', '发布报告', 'artifact', object_schema({
                    'metrics': {'type': 'object'}, 'selectedIds': {'type': 'array'},
                    'evidenceIds': {'type': 'array'}, 'summary': {'type': 'string'},
                }), publish),
            ]

    class RatioModel(Model):
        async def complete(self, messages, tools):
            if self.role == 'planner':
                return result('submit_plan', {'steps': []})
            if any('比例条件发布前校验拒绝' in event.get('title', '') for event in []):
                raise AssertionError('events are not model messages')
            prior = [call['function']['name'] for message in messages for call in message.get('tool_calls') or []]
            if 'workspace_reconcile_keyed_sums' not in prior and 'workspace_publish_report' not in prior:
                return result('workspace_publish_report', {'metrics': {}, 'selectedIds': [], 'evidenceIds': [], 'summary': '先提交'})
            if 'workspace_reconcile_keyed_sums' not in prior:
                return result('workspace_reconcile_keyed_sums', {
                    'anchorTableId': 'orders', 'keyField': 'order_id', 'aggregates': [],
                    'comparisons': [{'leftAlias': 'freight', 'rightTerms': [{'alias': 'price', 'multiplier': .2}]}],
                })
            return result('workspace_publish_report', {'metrics': {}, 'selectedIds': [], 'evidenceIds': [], 'summary': '已对账'})

    runner = TaskRunner(RatioBank(tmp_path), lambda role: RatioModel(role, []), learning_enabled=False)
    run = await runner.start(TaskRunRequest(taskId='ratio', strategy='plan_react'))
    await runner.tasks[run['id']]
    assert run['evaluation']['status'] == 'passed'
    assert run['metrics']['semanticConstraintGuards'] >= 1
    assert any(event['type'] == 'semantic_guard' and '比例条件' in event['title'] for event in run['events'])


async def test_missing_evidence_recovers_by_reading_next_page_not_by_inventing_references(tmp_path):
    class PagedBank(Bank):
        def task(self, key):
            return dict(id=key, scenario='finance', family='paged', split='train', recordIds=['one', 'two'],
                        task='读取本任务全部记录并发布结果', suggestedBudget={'toolCalls': 80})
        def tools(self, key):
            def listing(args, ctx):
                record = 'one' if args['page'] == 1 else 'two'
                ctx.evidence.add('finance:' + record)
                return {'records': [{'id': record}], 'page': args['page'], 'mayHaveMore': args['page'] == 1}
            def publish(args, ctx):
                ctx.run['evaluation'] = dict(status='passed' if args['evidenceIds'] == ['finance:one', 'finance:two'] else 'failed',
                                              issues=[] if args['evidenceIds'] == ['finance:one', 'finance:two'] else ['evidence_coverage'])
                return {'saved': True, 'evaluation': ctx.run['evaluation']}
            return [Tool('finance_list_orders', '分页列出订单 ID', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), listing,
                         outputs=['id']),
                    Tool('finance_publish_report', '发布报告', 'artifact', object_schema({
                        'metrics': object_schema({'count': {'type': 'integer'}}),
                        'selectedIds': {'type': 'array', 'items': {'type': 'string'}},
                        'evidenceIds': {'type': 'array', 'items': {'type': 'string'}},
                        'summary': {'type': 'string'},
                    }), publish)]
    class PagedModel(Model):
        async def complete(self, messages, tools):
            if self.role == 'planner':
                return await super().complete(messages, tools)
            if any(message.get('tool_call_id') == 'finance_publish_report' and '"status": "passed"' in message.get('content', '')
                   for message in messages):
                return result()
            list_calls = [call for message in messages for call in message.get('tool_calls') or []
                          if call['function']['name'] == 'finance_list_orders']
            recovering_missing = any('当前实际观察缺少部分本任务记录' in message.get('content', '') for message in messages)
            if not list_calls:
                return result('finance_list_orders', {'page': 1, 'pageSize': 50})
            if recovering_missing and len(list_calls) == 1:
                return result('finance_list_orders', {'page': 2, 'pageSize': 50})
            return result('finance_publish_report', dict(metrics={'count': 2}, selectedIds=[], evidenceIds=['finance:one'], summary='complete scope'))
    runner = TaskRunner(PagedBank(tmp_path), lambda role: PagedModel(role, []), learning_enabled=False)
    run = await runner.start(TaskRunRequest(taskId='paged', strategy='plan_react'))
    await runner.tasks[run['id']]
    assert run['evaluation']['status'] == 'passed'
    assert run['metrics']['reportEvidenceCoverageGaps'] == 1
    assert run['metrics']['reportEvidenceFormatFailures'] == 0
    assert run['metrics']['reportEvidenceCanonicalizations'] == 1
    assert [trace['arguments']['page'] for trace in run['toolTrace'] if trace['tool'] == 'finance_list_orders'] == [1, 2]
    assert run['reportRecovery']['attempts'][0]['kind'] == 'missing_evidence'
    assert run['reportRecovery']['attempts'][0]['missingObservedEvidenceRefs'] == ['finance:two']


async def test_public_delivery_scope_recovery_resubmits_without_another_model_turn(tmp_path):
    """Both arms may repair public workspace scope without seeing private rows.

    The first report contains correct business fields but only the first page's
    observation.  The runtime may read the publicly declared table slot and
    re-submit that unchanged report.  It must not ask the model to infer which
    hidden evidence row was missing.
    """
    histories = []

    class ScopeRecoveryBank(Bank):
        def task(self, key):
            return {
                'id': key, 'scenario': 'finance', 'family': 'scope_recovery', 'split': 'train',
                'task': '核对当前订单资料并提交完整报告', 'tableBindings': {'orders': 'orders-table'},
                'deliveryContract': {
                    'requiredSources': ['orders.csv'], 'requiredTableSlots': ['orders'],
                    'metrics': {'count': '当前订单数量。'},
                },
                'privateValidation': {
                    'metrics': {'count': 2}, 'selectedIds': [], 'ordered': False,
                    'requiredEvidenceIds': ['workspace:scope:one', 'workspace:scope:two'],
                },
                'suggestedBudget': {'toolCalls': 80},
            }

        def tools(self, key):
            def preview(args, ctx):
                rows = [
                    {'id': 'one', '_evidenceRef': 'workspace:scope:one'},
                    {'id': 'two', '_evidenceRef': 'workspace:scope:two'},
                ]
                start = (args['page'] - 1) * args['pageSize']
                page = rows[start:start + args['pageSize']]
                ctx.evidence.update(row['_evidenceRef'] for row in page)
                return {'tableId': args['tableId'], 'records': page, 'page': args['page'],
                        'mayHaveMore': start + args['pageSize'] < len(rows)}

            def publish(args, ctx):
                ctx.run['submission'] = deepcopy(args)
                passed = (args.get('metrics') == {'count': 2} and args.get('selectedIds') == []
                          and args.get('evidenceIds') == ['workspace:scope:one', 'workspace:scope:two'])
                ctx.run['evaluation'] = {'status': 'passed' if passed else 'failed',
                                         'issues': [] if passed else ['evidence_coverage']}
                return {'saved': True, 'evaluation': ctx.run['evaluation']}

            return [
                Tool('workspace_preview_rows', '分页预览当前资料行', 'read', object_schema({
                    'tableId': {'type': 'string'}, 'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'},
                }), preview, outputs=['records', 'page', 'mayHaveMore']),
                Tool('workspace_publish_report', '提交完整业务报告', 'artifact', object_schema({
                    'metrics': object_schema({'count': {'type': 'integer'}}),
                    'selectedIds': {'type': 'array', 'items': {'type': 'string'}},
                    'evidenceIds': {'type': 'array', 'items': {'type': 'string'}},
                    'summary': {'type': 'string'},
                }), publish),
            ]

    class ScopeRecoveryModel(Model):
        async def complete(self, messages, tools):
            histories.append(deepcopy(messages))
            if self.role == 'planner':
                return result('submit_plan', {'steps': [
                    {'id': 'preview', 'intent': '分页预览当前资料行', 'dependencies': []},
                ]})
            if tools and tools[0].name == 'submit_graph':
                return result('submit_graph', {'nodes': [{'id': 'preview', 'tool': 'workspace_preview_rows'}]})
            calls = [call for message in messages for call in message.get('tool_calls') or []]
            names = [call['function']['name'] for call in calls]
            if 'workspace_preview_rows' not in names:
                return result('workspace_preview_rows', {'tableId': 'orders-table', 'page': 1, 'pageSize': 1})
            if 'workspace_publish_report' not in names:
                return result('workspace_publish_report', {
                    'metrics': {'count': 2}, 'selectedIds': [],
                    'evidenceIds': ['workspace:scope:one'], 'summary': '已完成当前订单核对。',
                })
            return result()

    for strategy in ['plan_react', 'graph_rsi']:
        histories.clear()
        runner = TaskRunner(ScopeRecoveryBank(tmp_path / strategy),
                            lambda role: ScopeRecoveryModel(role, histories), learning_enabled=False)
        run = await runner.start(TaskRunRequest(taskId='scope-recovery', strategy=strategy))
        await runner.tasks[run['id']]

        assert run['status'] == 'completed'
        assert run['evaluation']['status'] == 'passed'
        assert run['submission']['metrics'] == {'count': 2}
        assert run['metrics']['reportAttempts'] == 2
        assert run['metrics']['failedReportAttempts'] == 1
        assert run['metrics']['deterministicScopeRecoveryReads'] == 1
        assert run['metrics']['deterministicReportResubmits'] == 1
        assert run['metrics']['recoveryToolCalls'] == 1
        recovery_index = next(index for index, event in enumerate(run['events'])
                              if event['type'] == 'report_recovery')
        assert not any(event['type'] == 'model_start' for event in run['events'][recovery_index + 1:])
        assert any(event['type'] == 'evidence_scope_recovery' and '重提原报告' in event['title']
                   for event in run['events'])
        model_text = json.dumps(histories, ensure_ascii=False)
        assert 'privateValidation' not in model_text
    assert 'workspace:scope:two' not in model_text


async def test_duplicate_deterministic_compute_is_rejected_for_both_arms(tmp_path):
    """A repeated pure computation must not consume the whole agent budget."""
    compute_calls = []

    class ComputeBank(Bank):
        def tools(self, key):
            def aggregate(args, ctx):
                compute_calls.append(deepcopy(args))
                return {'count': 10}

            def publish(args, ctx):
                ctx.run['evaluation'] = {'status': 'passed', 'issues': []}
                return {'saved': True, 'evaluation': ctx.run['evaluation']}

            return [
                Tool('workspace_aggregate_rows', '确定性计数', 'compute', object_schema({
                    'tableId': {'type': 'string'}, 'operation': {'type': 'string'},
                }), aggregate),
                Tool('workspace_publish_report', '提交报告', 'artifact', object_schema({
                    'metrics': {'type': 'object'}, 'selectedIds': {'type': 'array'},
                    'evidenceIds': {'type': 'array'}, 'summary': {'type': 'string'},
                }), publish),
            ]

    class RepeatComputeModel(Model):
        async def complete(self, messages, tools):
            if self.role == 'planner':
                return result('submit_plan', {'steps': []})
            calls = [call['function']['name'] for message in messages for call in message.get('tool_calls') or []]
            saw_guard = any('相同确定性计算结果' in message.get('content', '') for message in messages)
            if 'workspace_aggregate_rows' not in calls or not saw_guard:
                return result('workspace_aggregate_rows', {'tableId': 'current', 'operation': 'count'})
            return result('workspace_publish_report', {
                'metrics': {'count': 10}, 'selectedIds': [], 'evidenceIds': [], 'summary': '已复用确定性计算结果。',
            })

    for strategy in ['plan_react', 'graph_rsi']:
        compute_calls.clear()
        runner = TaskRunner(ComputeBank(tmp_path / strategy), lambda role: RepeatComputeModel(role, []), learning_enabled=False)
        run = await runner.start(TaskRunRequest(taskId='compute-repeat', strategy=strategy))
        await runner.tasks[run['id']]

        assert run['evaluation']['status'] == 'passed'
        assert len(compute_calls) == 1
        assert run['metrics']['duplicateComputeGuardRejects'] == 1
        assert any(event['type'] == 'compute_guard' for event in run['events'])


def test_actual_tool_call_difference_uses_exact_signatures(tmp_path):
    runner = TaskRunner(Bank(tmp_path), lambda role: Model(role, []))
    baseline = dict(id='baseline', taskId='same', strategy='react', status='completed', createdAt='2026-09-10T01:00:00Z',
                    evaluation={'status': 'passed'}, toolTrace=[
                        dict(tool='read', arguments={'id': 'a'}, effect='read', signature='a'),
                        dict(tool='read', arguments={'id': 'b'}, effect='read', signature='b'),
                        dict(tool='publish', arguments={}, effect='artifact', signature='p')])
    candidate = dict(id='candidate', taskId='same', strategy='autotool', status='completed', createdAt='2026-09-10T02:00:00Z',
                     evaluation={'status': 'passed'}, toolTrace=[
                         dict(tool='read', arguments={'id': 'a'}, effect='read', signature='a'),
                         dict(tool='publish', arguments={}, effect='artifact', signature='p')])
    runner.runs = {'baseline': baseline, 'candidate': candidate}
    comparison = runner.compare_with_baseline(candidate)
    assert comparison['skippedToolCalls'] == comparison['fewerReadCalls'] == comparison['netToolCallReduction'] == 1
    assert comparison['fewerByTool'] == [{'tool': 'read', 'effect': 'read', 'count': 1}]
    assert comparison['modelRequestReduction'] == comparison['inputTokenReduction'] == 0
    assert comparison['sharedToolCalls'] == 2 and comparison['skipped'][0]['arguments'] == {'id': 'b'}


async def test_cancel_queued_and_running_jobs(tmp_path):
    entered = asyncio.Event()
    class Slow(Model):
        async def complete(self, messages, tools):
            entered.set()
            await asyncio.Event().wait()
    runner = TaskRunner(Bank(tmp_path), lambda role: Slow(role, []), run_limit=1)
    first = await runner.start(TaskRunRequest(taskId='a'))
    await entered.wait()
    queued = await runner.start(TaskRunRequest(taskId='b'))
    await runner.shutdown()
    await asyncio.sleep(0)
    assert first['status'] == queued['status'] == 'cancelled'
    assert queued['metrics']['modelRequests'] == 0
    assert first['metrics']['usageComplete'] is False and not runner.tasks


async def test_http_run_endpoints_and_unknown_run(tmp_path, monkeypatch):
    bank = Bank(tmp_path)
    monkeypatch.setattr('backend.app.TaskBank', lambda: bank)
    app = create_app(RunService(tmp_path / 'legacy'))
    app.state.task_runner.provider_factory = lambda role: Model(role, [])
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/taskbank/runs', json={'taskId': 'sample'})
            assert response.status_code == 202
            key = response.json()['id']
            job = app.state.task_runner.tasks.get(key)
            if job:
                await job
            detail = (await client.get('/api/taskbank/runs/' + key)).json()
            assert detail['evaluation']['status'] == 'passed' and detail['graph']['status'] == 'done'
            assert (await client.get('/api/taskbank/runs')).json()['scheduler']['active']['runs'] == 0
            online = await client.get('/api/taskbank/evolution')
            assert online.status_code == 200 and online.json()['protocol']['shadowRollouts'] == 0
            assert online.json()['versions'] == []
            assert (await client.get('/api/taskbank/runs/missing')).status_code == 404
            assert (await client.post('/api/taskbank/runs/' + key + '/cancel', json={})).json()['cancelled'] is False


async def test_trace_captures_pending_model_and_concurrent_tool_correlation(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    class Gated(Model):
        async def complete(self, messages, tools):
            if self.role == 'planner':
                entered.set()
                await release.wait()
            return await super().complete(messages, tools)
    runner = TaskRunner(Bank(tmp_path), lambda role: Gated(role, []))
    run = await runner.start(TaskRunRequest(taskId='trace'))
    await entered.wait()
    assert run['traceVersion'] == 2 and run['startedAt']
    start = next(e for e in run['events'] if e['type'] == 'model_start')
    assert start['detail']['availableTools'] == ['submit_plan']
    assert start['metrics']['modelRequests'] == 1
    assert not any(e['type'] == 'model' for e in run['events'])
    release.set()
    await runner.tasks[run['id']]
    response = next(e for e in run['events'] if e['type'] == 'model')
    assert response['detail']['requestId'] == start['detail']['requestId']
    assert response['detail']['toolCalls'][0]['function']['name'] == 'submit_plan'
    assert start['metrics']['inputTokens'] == 0  # Snapshot did not mutate.
    actions = {e['detail']['callId']: e for e in run['events'] if e['type'] == 'action'}
    for e in run['events']:
        if e['type'] == 'observation':
            assert e['detail']['callId'] in actions
            assert e['elapsedMs'] >= actions[e['detail']['callId']]['elapsedMs']
    graph_event = next(e for e in run['events'] if e['type'] == 'graph_created')
    assert graph_event['detail']['nodes'] == run['graph']['nodes']
    assert run['events'][-1]['type'] == 'finished'
    assert run['events'][-1]['metrics'] == run['metrics']
    assert run['events'][-1]['detail']['evaluation']['status'] == 'passed'
    assert run['metrics']['modelRequests'] == 2 and run['metrics']['toolCalls'] == 2


async def test_optional_null_plan_selection_is_normalized_without_a_planner_retry(tmp_path):
    class NullSelectionModel(Model):
        async def complete(self, messages, tools):
            if self.role == 'planner':
                return result('submit_plan', {'steps': [
                    {'id': 'list', 'intent': '分页列出订单 ID', 'dependencies': [], 'selection': None},
                ]})
            if not any(message.get('role') == 'tool' for message in messages):
                return result('finance_list_orders', {'page': 1, 'pageSize': 50})
            return result('finance_publish_report', {})

    runner = TaskRunner(Bank(tmp_path), lambda role: NullSelectionModel(role, []), learning_enabled=False)
    run = await runner.start(TaskRunRequest(taskId='null-selection', strategy='plan_react'))
    await runner.tasks[run['id']]

    assert run['evaluation']['status'] == 'passed'
    assert run['phaseMetrics']['plan']['requests'] == 1
    assert run['metrics']['controlErrors'] == 0
    assert run['plan']['steps'][0].get('selection') is None
    normalized = next(event for event in run['events'] if event['type'] == 'normalization')
    assert normalized['detail']['stepIds'] == ['list']


async def test_completed_scope_prevents_evidence_rereads_without_leaking_private_validation(tmp_path):
    read_calls, histories = [], []

    class ScopeBank(Bank):
        def task(self, key):
            return {
                'id': key, 'scenario': 'finance', 'family': 'scope', 'split': 'train',
                'task': '读取本任务全部订单并发布核对结果',
                'deliveryContract': {'requiredSources': ['orders.csv'], 'metrics': {'count': '当前订单数。'}},
                'privateValidation': {'metrics': {'count': 1}, 'selectedIds': [], 'ordered': False,
                                      'requiredEvidenceIds': ['finance:one']},
                'suggestedBudget': {'toolCalls': 80},
            }

        def tools(self, key):
            def listing(args, ctx):
                read_calls.append(deepcopy(args))
                ctx.evidence.add('finance:one')
                return {'records': [{'id': 'one', '_evidenceRef': 'finance:one'}], 'page': 1, 'mayHaveMore': False}

            def publish(args, ctx):
                ctx.run['evaluation'] = {
                    'status': 'passed' if args == {'metrics': {'count': 1}, 'selectedIds': [],
                                                    'evidenceIds': ['finance:one'], 'summary': '已完成'} else 'failed',
                    'issues': [],
                }
                return {'saved': True, 'evaluation': ctx.run['evaluation']}

            return [
                Tool('finance_list_orders', '分页列出订单 ID', 'read',
                     object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), listing, outputs=['id']),
                Tool('finance_publish_report', '发布报告', 'artifact', object_schema({
                    'metrics': object_schema({'count': {'type': 'integer'}}),
                    'selectedIds': {'type': 'array', 'items': {'type': 'string'}},
                    'evidenceIds': {'type': 'array', 'items': {'type': 'string'}},
                    'summary': {'type': 'string'},
                }), publish),
            ]

    class ScopeModel(Model):
        async def complete(self, messages, tools):
            histories.append(deepcopy(messages))
            if self.role == 'planner':
                return result('submit_plan', {'steps': [
                    {'id': 'list', 'intent': '分页列出订单 ID', 'dependencies': [], 'selection': None},
                ]})
            tool_calls = [call for message in messages for call in message.get('tool_calls') or []
                          if call['function']['name'] == 'finance_list_orders']
            saw_guard = any('当前运行已成功获得相同只读观察' in message.get('content', '') for message in messages)
            if not tool_calls or not saw_guard:
                return result('finance_list_orders', {'page': 1, 'pageSize': 50})
            return result('finance_publish_report', {
                'metrics': {'count': 1}, 'selectedIds': [], 'evidenceIds': ['mistyped'], 'summary': '已完成',
            })

    for strategy in ['plan_react', 'graph_rsi']:
        read_calls.clear()
        runner = TaskRunner(ScopeBank(tmp_path / strategy), lambda role: ScopeModel(role, histories), learning_enabled=False)
        run = await runner.start(TaskRunRequest(taskId='scope', strategy=strategy))
        await runner.tasks[run['id']]

        assert run['evaluation']['status'] == 'passed'
        assert len(read_calls) == 1
        assert run['metrics']['duplicateReadGuardRejects'] == 1
        assert run['metrics']['observedScopeCompletions'] == 1
        assert run['metrics']['reportEvidenceCanonicalizations'] == 1
        assert any(event['type'] == 'evidence_scope' for event in run['events'])

    model_text = json.dumps(histories, ensure_ascii=False)
    assert 'privateValidation' not in model_text
    assert 'requiredEvidenceIds' not in model_text
    assert '_evidenceRef' not in model_text


async def test_run_level_providers_allow_all_three_live_comparison_arms_to_request_together(tmp_path):
    active_lanes, reached, release = set(), asyncio.Event(), asyncio.Event()
    created = []

    class ThreeArmModel(Model):
        def __init__(self, lane, role):
            super().__init__(role, [])
            self.lane = lane
            self.model = f'{lane}-{role}-qwen/qwen3.5-27b'

        async def complete(self, messages, tools):
            if self.role == 'planner' and self.lane not in active_lanes:
                active_lanes.add(self.lane)
                if len(active_lanes) == 3:
                    reached.set()
                await asyncio.wait_for(release.wait(), timeout=2)
            return await super().complete(messages, tools)

    def factory(lane):
        def create(role):
            created.append((lane, role))
            return ThreeArmModel(lane, role)
        return create

    runner = TaskRunner(Bank(tmp_path), lambda _role: (_ for _ in ()).throw(AssertionError('runner default provider used')),
                        run_limit=3, model_limit=3, read_limit=3, learning_enabled=False)
    observed = []
    runner.evolution.observe = lambda run, task, tools: observed.append((run['id'], task['id']))

    plan = await runner.start(
        TaskRunRequest(taskId='shared', strategy='plan_react'),
        provider_factory=factory('primary-plan'), learning_enabled=False, learning_write_enabled=False,
        comparison_context={'id': 'comparison', 'arm': 'plan_react', 'providerProfile': 'primary'},
        experience_context={'mode': 'not_applicable', 'versionCount': 0, 'readOnly': True},
    )
    no_learning = await runner.start(
        TaskRunRequest(taskId='shared', strategy='graph_rsi'),
        provider_factory=factory('primary-graph'), learning_enabled=False, learning_write_enabled=False,
        comparison_context={'id': 'comparison', 'arm': 'no_learning', 'providerProfile': 'primary'},
        experience_context={'mode': 'empty_isolated', 'versionCount': 0, 'readOnly': True},
    )
    graph = await runner.start(
        TaskRunRequest(taskId='shared', strategy='graph_rsi'),
        provider_factory=factory('secondary'), learning_enabled=True, learning_write_enabled=False,
        comparison_context={'id': 'comparison', 'arm': 'online_rsi', 'providerProfile': 'secondary'},
        experience_context={'mode': 'frozen_finance_release', 'versionCount': 3, 'readOnly': True},
    )
    await asyncio.wait_for(reached.wait(), timeout=2)
    assert runner.active_runs == 3 and runner.active_models == 3
    release.set()
    await asyncio.gather(*list(runner.tasks.values()))

    assert runner.peaks['runs'] == 3 and runner.peaks['models'] == 3
    assert plan['strategy'] == 'plan_react'
    assert no_learning['strategy'] == graph['strategy'] == 'graph_rsi'
    assert plan['models']['planner'].startswith('primary-plan-')
    assert no_learning['models']['planner'].startswith('primary-graph-')
    assert graph['models']['planner'].startswith('secondary-')
    assert plan['learningEnabled'] is False and no_learning['learningEnabled'] is False and graph['learningEnabled'] is True
    assert plan['learningWriteEnabled'] is False and no_learning['learningWriteEnabled'] is False and graph['learningWriteEnabled'] is False
    assert graph['workspaceOnlineLearning'] is False
    assert observed == []
    assert sorted(created) == sorted([
        ('primary-plan', 'planner'), ('primary-plan', 'executor'), ('primary-plan', 'composition'),
        ('primary-graph', 'planner'), ('primary-graph', 'executor'), ('primary-graph', 'composition'),
        ('secondary', 'planner'), ('secondary', 'executor'), ('secondary', 'composition'),
    ])
    await runner.shutdown()


async def test_comparison_metadata_is_in_first_saved_run_and_invalid_learning_mode_fails_closed(tmp_path):
    runner = TaskRunner(Bank(tmp_path), lambda role: Model(role, []), run_limit=1, learning_enabled=False)
    runner.run_slots = asyncio.Semaphore(0)
    run = await runner.start(
        TaskRunRequest(taskId='queued', strategy='plan_react'),
        comparison_context={'id': 'pair-1', 'arm': 'plan_react', 'providerProfile': 'primary'},
    )
    saved = json.loads((tmp_path / 'artifacts/taskbank-runs' / f"{run['id']}.json").read_text())
    assert saved['comparison'] == {'id': 'pair-1', 'arm': 'plan_react', 'providerProfile': 'primary'}
    assert saved['learningEnabled'] is False
    with pytest.raises(ValueError, match='只允许'):
        await runner.start(TaskRunRequest(taskId='bad', strategy='plan_react'),
                           learning_enabled=True, workspace_online_learning=True)
    await runner.shutdown()
