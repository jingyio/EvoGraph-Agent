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
        assert run['metrics']['modelRequests'] == 3 and run['metrics']['inputTokens'] == 30
        assert run['models']['distinctModels'] and run['graph']['status'] == 'done'
        assert run['metrics']['toolCalls'] == 2
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
    assert run['metrics']['modelRequests'] == 3 and run['metrics']['toolCalls'] == 2
