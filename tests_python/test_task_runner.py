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
        assert run['phaseMetrics']['plan']['requests'] == run['phaseMetrics']['graph']['requests'] == 1
        assert run['metrics']['modelRequests'] == 4 and run['metrics']['inputTokens'] == 40
        assert run['models']['distinctModels'] and run['graph']['status'] == 'done'
        assert run['metrics']['toolCalls'] == 2
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
            assert (await client.get('/api/taskbank/runs/missing')).status_code == 404
            assert (await client.post('/api/taskbank/runs/' + key + '/cancel', json={})).json()['cancelled'] is False
