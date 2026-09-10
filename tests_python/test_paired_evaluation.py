import asyncio
from copy import deepcopy
import pytest
from backend.paired_evaluation import PairedEvaluation, EvaluationRequest, summarize
from backend.task_runner import TaskRunner, TaskRunRequest
from test_task_runner import Bank, Model


def row(passed, tokens):
    return dict(status='completed', evaluation={'status': 'passed' if passed else 'failed'}, evolution=None,
                metrics=dict(inputTokens=tokens, outputTokens=0, usageComplete=True, durationMs=1000,
                             modelRequests=2, toolCalls=3, toolErrors=0))


def test_failures_stay_in_cost_and_quality_regression_is_explicit():
    rows = [dict(runs=dict(strong_react=row(True, 100), graph_rsi=row(False, 300))),
            dict(runs=dict(strong_react=row(True, 100), graph_rsi=row(True, 50)))]
    out = summarize(rows)
    assert out['qualityRegressions'] == 1 and out['bothPassed'] == 1
    assert out['arms']['graph_rsi']['tokensPerSuccess'] == 350
    assert out['bothPassedTokenDifference'] == 50  # Cannot hide failed cost in headline.
    assert out['allOutcomeTokenReduction'] == -.75
    rows[0]['runs']['graph_rsi']['metrics']['usageComplete'] = False
    out = summarize(rows)
    assert out['allOutcomeTokenReduction'] is None
    assert out['arms']['graph_rsi']['tokensPerSuccess'] is None


class Corpus(Bank):
    manifest = {'source': 'injected-tests'}
    def __init__(self, root):
        super().__init__(root)
        self.tasks = {}
        for scenario in ['finance', 'support', 'tickets']:
            for family in range(10):
                for suffix in ['07', '08']:
                    key = f'{scenario}-{family}-{suffix}'
                    self.tasks[key] = dict(super().task(key), scenario=scenario, family=str(family), split='validation')
    def task(self, key):
        return self.tasks[key]


async def test_fixed_task_selection_frozen_graphs_and_all_runs_persist(tmp_path):
    bank = Corpus(tmp_path)
    # Generic test model handles all scenario labels using the injected finance tool.
    class Reading(Model):
        async def complete(self, messages, tools):
            if self.role != 'planner' and not any(m.get('role') == 'tool' for m in messages):
                from test_task_runner import result
                return result('finance_list_orders', {'page': 1, 'pageSize': 50})
            return await super().complete(messages, tools)
    runner = TaskRunner(bank, lambda role: Reading(role, []))
    evaluations = PairedEvaluation(runner)
    before = deepcopy(runner.evolution.versions)
    item = await evaluations.start(EvaluationRequest())
    await evaluations.tasks[item['id']]
    assert item['status'] == 'completed'
    assert len(item['pairs']) == 30 and all(p['taskId'].endswith('07') for p in item['pairs'])
    assert len(runner.runs) == 60
    assert runner.evolution.versions == before
    assert not runner.evolution.path.exists()
    assert item['protocol']['observedGraphCoverage'] == 0
    assert item['summary']['arms']['strong_react']['attempts'] == 30
    assert all(p['runs']['strong_react']['models'] == p['runs']['graph_rsi']['models'] for p in item['pairs'])
    restored = PairedEvaluation(runner)
    restored.restore()
    assert restored.items[item['id']]['summary'] == item['summary']


async def test_strong_prompt_is_shared_with_rsi_and_skips_planner(tmp_path):
    histories = []
    runner = TaskRunner(Bank(tmp_path), lambda role: Model(role, histories))
    run = await runner.start(TaskRunRequest(taskId='x', strategy='strong_react'))
    await runner.tasks[run['id']]
    assert run['phaseMetrics']['plan']['requests'] == 0
    assert '避免重复读取' in histories[0][0]['content']
    run = await runner.start(TaskRunRequest(taskId='x', strategy='graph_rsi'), evaluation_context={'graphSnapshot': None})
    await runner.tasks[run['id']]
    assert any('避免重复读取' in h[0]['content'] for h in histories)
    assert runner.evolution.versions == []


async def test_cancel_retains_attempts_and_stops_child_jobs(tmp_path):
    entered = asyncio.Event()
    class Waiting(Model):
        async def complete(self, messages, tools):
            entered.set()
            await asyncio.Event().wait()
    runner = TaskRunner(Corpus(tmp_path), lambda role: Waiting(role, []))
    service = PairedEvaluation(runner)
    item = await service.start(EvaluationRequest())
    await entered.wait()
    await service.shutdown()
    assert item['status'] == 'cancelled' and not runner.tasks
    assert sum(len(p['runIds']) for p in item['pairs']) > 0
    for pair in item['pairs']:
        for run in pair['runs'].values():
            assert run['status'] == 'cancelled'
            assert not run['metrics']['usageComplete'] or run['metrics']['modelRequests'] == 0


async def test_cancel_before_worker_starts_releases_experiment_slot(tmp_path):
    runner = TaskRunner(Corpus(tmp_path), lambda role: Model(role, []))
    service = PairedEvaluation(runner)
    item = await service.start(EvaluationRequest())
    await service.shutdown()
    assert item['status'] == 'cancelled' and not service.tasks
    assert not runner.tasks
