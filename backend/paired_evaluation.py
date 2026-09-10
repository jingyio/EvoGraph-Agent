"""Frozen, all-outcome paired evaluation; separate from online graph evolution."""
import asyncio
from collections import defaultdict
from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from . import config
from .domain import now
from .autotool import digest
from .graph import contract_hash
from .graph_store import write_private
from .task_runner import TaskRunRequest


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    split: Literal['validation', 'test'] = 'validation'
    repeats: int = Field(default=1, ge=1, le=3)


def success(run):
    return run.get('status') == 'completed' and run.get('evaluation', {}).get('status') == 'passed'


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * q) - 1)]


def summarize(rows):
    arms = {}
    for arm in ['strong_react', 'graph_rsi']:
        runs = [row['runs'][arm] for row in rows if arm in row.get('runs', {})]
        complete_usage = all(r['metrics'].get('usageComplete') for r in runs)
        tokens = sum((r['metrics'].get('inputTokens') or 0) + (r['metrics'].get('outputTokens') or 0) for r in runs)
        passed = sum(success(r) for r in runs)
        elapsed = [r['metrics']['durationMs'] for r in runs]
        arms[arm] = dict(attempts=len(runs), passed=passed, successRate=passed / len(runs) if runs else None,
            inputTokens=sum(r['metrics'].get('inputTokens') or 0 for r in runs),
            outputTokens=sum(r['metrics'].get('outputTokens') or 0 for r in runs), totalTokens=tokens,
            usageComplete=complete_usage, tokensPerSuccess=tokens / passed if passed and complete_usage else None,
            modelRequests=sum(r['metrics']['modelRequests'] for r in runs), toolCalls=sum(r['metrics']['toolCalls'] for r in runs),
            toolErrors=sum(r['metrics']['toolErrors'] for r in runs),
            meanLatencyMs=sum(elapsed) / len(elapsed) if elapsed else None, p50Ms=percentile(elapsed, .5), p95Ms=percentile(elapsed, .95),
            limited=sum(r['status'] == 'limited' for r in runs),
            graphFallbacks=sum(bool(r.get('fallback')) for r in runs),
            warmRuns=sum(bool((r.get('evolution') or {}).get('usedVersionId')) for r in runs),
            coldRuns=sum((r.get('evolution') or {}).get('execution') == 'cold-plan' for r in runs))
    both = [row for row in rows if all(arm in row.get('runs', {}) and success(row['runs'][arm]) and row['runs'][arm]['metrics'].get('usageComplete') for arm in arms)]
    a, b = arms['strong_react'], arms['graph_rsi']
    regression = sum(success(row['runs']['strong_react']) and not success(row['runs']['graph_rsi']) for row in rows if all(arm in row.get('runs', {}) for arm in arms))
    improvement = sum(not success(row['runs']['strong_react']) and success(row['runs']['graph_rsi']) for row in rows if all(arm in row.get('runs', {}) for arm in arms))
    reduction = (a['totalTokens'] - b['totalTokens']) / a['totalTokens'] if a['totalTokens'] and a['usageComplete'] and b['usageComplete'] else None
    paired_saving = sum(sum(row['runs']['strong_react']['metrics'][k] - row['runs']['graph_rsi']['metrics'][k] for k in ['inputTokens', 'outputTokens']) for row in both)
    return dict(arms=arms, bothPassed=len(both), qualityRegressions=regression, qualityImprovements=improvement,
                allOutcomeTokenReduction=reduction, bothPassedTokenDifference=paired_saving,
                note='全部尝试计入总成本；每成功任务 token 包含失败开销。双方通过子集另列，不用成功筛选掩盖失败。报告文字未评分。')


class PairedEvaluation:
    def __init__(self, runner):
        self.runner = runner
        self.directory = runner.bank.root / 'artifacts/paired-evaluations'
        self.items, self.tasks = {}, {}

    def save(self, item):
        item['summary'] = summarize(item['pairs'])
        item['byScenario'] = {scenario: summarize([p for p in item['pairs'] if p['scenario'] == scenario]) for scenario in ['finance', 'support', 'tickets']}
        write_private(self.directory / (item['id'] + '.json'), item)

    def restore(self):
        for path in self.directory.glob('*.json'):
            item = json.loads(path.read_text())
            if item['status'] == 'running':
                item.update(status='interrupted', finishedAt=now())
                # Retain completed and interrupted child runs even after a process crash.
                for pair in item['pairs']:
                    for arm, key in pair['runIds'].items():
                        if key in self.runner.runs:
                            pair['runs'][arm] = self.compact(self.runner.runs[key])
                self.save(item)
            self.items[item['id']] = item

    @staticmethod
    def compact(run):
        return deepcopy({k: run.get(k) for k in ['id', 'status', 'models', 'modelSettings', 'metrics', 'evaluation', 'evolution', 'fallback', 'error']})

    def choose_tasks(self, split):
        families = defaultdict(list)
        for task in self.runner.bank.tasks.values():
            if task['split'] == split:
                families[(task['scenario'], task['family'])].append(task)
        return [sorted(tasks, key=lambda t: t['id'])[0] for _, tasks in sorted(families.items())]

    async def start(self, request):
        if self.tasks or self.runner.tasks:
            raise ValueError('请等待当前任务结束后开始冻结评测，避免混入其他流量')
        selected = self.choose_tasks(request.split)
        if len(selected) != 30 or any(sum(t['scenario'] == s for t in selected) != 10 for s in ['finance', 'support', 'tickets']):
            raise ValueError('每场景需有 10 个任务类型')
        planner, executor = self.runner.providers()  # Fail before accepting work if configuration is absent.
        graphs = {t['id']: self.runner.evolution.select(t, self.runner.bank.tools(t['id'])) for t in selected}
        parent_ids = {g['id'] for g in graphs.values() if g}
        source_runs = {v['sourceRunId'] for v in self.runner.evolution.versions if v['id'] in parent_ids}
        setup = [self.compact(self.runner.runs[k]) for k in sorted(source_runs) if k in self.runner.runs]
        try:
            revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.runner.bank.root, text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            revision = None
        source = {str(p.relative_to(config.ROOT)): p.read_text() for p in (config.ROOT / 'backend').glob('*.py')}
        pairs = [dict(index=i, taskId=t['id'], scenario=t['scenario'], family=t['family'], repeat=r + 1, status='pending', runIds={}, runs={})
                 for i, (r, t) in enumerate((r, t) for r in range(request.repeats) for t in selected)]
        item = dict(id=str(uuid4()), status='running', createdAt=now(), split=request.split, pairs=pairs,
                    protocol=dict(arms=['strong_react', 'graph_rsi'], tasksPerScenario=10, repeats=request.repeats, selection='每类型按 ID 排序的首个所选划分任务，结果产生前确定',
                        revision=revision, sourceHash=digest(source), corpusHash=digest(self.runner.bank.manifest), taskHash=digest(selected),
                        toolHashes={t['id']: contract_hash(self.runner.bank.tools(t['id'])) for t in selected},
                        planner=planner.model, executor=executor.model, maxSteps=config.MAX_STEPS, timeout=config.RUN_TIMEOUT,
                        scheduler=self.runner.status()['limits'], pairConcurrency=2, learning=False, observedGraphCoverage=sum(g is not None for g in graphs.values()),
                        scoring='structured-facts-and-evidence; prose-not-evaluated', graphHash=digest(graphs)),
                    graphSnapshots=graphs, historicalSetupRuns=setup,
                    historicalSetupTokens=sum(r['metrics']['inputTokens'] + r['metrics']['outputTokens'] for r in setup),
                    setupNote='仅列入已保存图的可追溯来源任务；不代表完整研发/学习总成本。成对评测期间图冻结、无更新。')
        write_private(self.directory / 'sources' / (item['id'] + '.json'), source)
        self.items[item['id']] = item
        self.save(item)
        job = asyncio.create_task(self.work(item))
        self.tasks[item['id']] = job
        def cleanup(done):
            if done.cancelled() and item['status'] == 'running':
                item.update(status='cancelled', finishedAt=now())
                self.save(item)
            self.tasks.pop(item['id'], None)
        job.add_done_callback(cleanup)
        return item

    async def work(self, item):
        slots = asyncio.Semaphore(2)
        async def pair_job(pair):
            async with slots:
                pair['status'] = 'running'
                order = ['strong_react', 'graph_rsi'] if pair['index'] % 2 == 0 else ['graph_rsi', 'strong_react']
                pair['launchOrder'] = order
                try:
                    for arm in order:
                        context = dict(experimentId=item['id'], pairIndex=pair['index'], graphSnapshot=item['graphSnapshots'][pair['taskId']] if arm == 'graph_rsi' else None)
                        run = await self.runner.start(TaskRunRequest(taskId=pair['taskId'], strategy=arm), evaluation_context=context)
                        pair['runIds'][arm] = run['id']
                    self.save(item)
                    jobs = [self.runner.tasks[k] for k in pair['runIds'].values() if k in self.runner.tasks]
                    await asyncio.gather(*jobs, return_exceptions=True)
                    pair['status'] = 'completed'
                except asyncio.CancelledError:
                    pair['status'] = 'cancelled'
                    for key in pair['runIds'].values():
                        if key in self.runner.tasks:
                            self.runner.tasks[key].cancel()
                    await asyncio.gather(*(self.runner.tasks[k] for k in pair['runIds'].values() if k in self.runner.tasks), return_exceptions=True)
                    raise
                except Exception as error:
                    pair.update(status='failed', error=str(error)[:500])
                    await asyncio.gather(*(self.runner.tasks[k] for k in pair['runIds'].values() if k in self.runner.tasks), return_exceptions=True)
                finally:
                    for arm, key in pair['runIds'].items():
                        pair['runs'][arm] = self.compact(self.runner.runs[key])
                    self.save(item)
        try:
            await asyncio.gather(*(pair_job(p) for p in item['pairs']))
            item['status'] = 'completed' if all(p['status'] == 'completed' for p in item['pairs']) else 'failed'
        except asyncio.CancelledError:
            item['status'] = 'cancelled'
        except Exception as error:
            item.update(status='failed', error=str(error)[:500])
        finally:
            item['finishedAt'] = now()
            self.save(item)
            self.tasks.pop(item['id'], None)

    async def shutdown(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
