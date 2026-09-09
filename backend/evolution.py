"""Isolated, measured generations of read-graph experience."""
import asyncio
from copy import deepcopy
import json
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from . import config
from .domain import PRESETS, now
from .graph_store import GraphStore, write_private
from .model_client import ModelClient, ModelOptions
from .runtime import create_run, execute_run
from .tools import sandbox_tools
from .negative_motif import NegativeMotifStore


class EvolutionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    scenario: Literal['finance', 'support'] = 'support'
    rounds: int = Field(default=3, ge=1, le=5)


def structure(graph):
    return [{k: v for k, v in n.items() if k != 'sourceEventSeqs'} for n in graph['nodes']] if graph else []


def acceptable(parent, child):
    def passed(run):
        return run['status'] == 'completed' and run['evaluation']['status'] == 'passed' and run['metrics']['usageComplete']
    if not passed(parent) or not passed(child):
        return False
    p, c = parent['metrics'], child['metrics']
    return (c['modelRequests'] < p['modelRequests'] and c['toolErrors'] <= p['toolErrors']
            and c['inputTokens'] + c['outputTokens'] <= p['inputTokens'] + p['outputTokens'])


class EvolutionService:
    def __init__(self, runs):
        self.runs = runs
        self.directory = runs.directory / 'evolutions'
        self.items, self.tasks = {}, {}

    def save(self, item):
        write_private(self.directory / (item['id'] + '.json'), item)

    def restore(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in self.directory.glob('*.json'):
            item = json.loads(path.read_text())
            if item['status'] == 'running':
                item.update(status='interrupted', phase='服务中断，保留已有证据')
                self.save(item)
            self.items[item['id']] = item

    async def start(self, request):
        if self.tasks:
            raise ValueError('已有进化实验正在运行')
        # Validate credentials before accepting background work.
        if not self.runs.provider_factory:
            ModelClient(ModelOptions(config.BASE_URL, config.API_KEY, config.MODEL, config.MODEL_TIMEOUT))
        item = dict(id=str(uuid4()), createdAt=now(), status='running', phase='冷启动',
                    scenario=request.scenario, rounds=[], maxRounds=request.rounds,
                    activeGraph=None, runIds=[], totalModelRequests=0, totalTokens=0)
        self.items[item['id']] = item
        self.save(item)
        task = asyncio.create_task(self.work(item))
        self.tasks[item['id']] = task
        def cleanup(done):
            if item['status'] == 'running' and done.cancelled():
                item.update(status='cancelled', phase='已取消')
                self.save(item)
            self.tasks.pop(item['id'], None)
        task.add_done_callback(cleanup)
        return item

    async def execute(self, item, snapshot, graph, phase):
        item['phase'] = phase
        self.save(item)
        provider = self.runs.provider_factory() if self.runs.provider_factory else ModelClient(ModelOptions(config.BASE_URL, config.API_KEY, config.MODEL, config.MODEL_TIMEOUT))
        request = dict(scenario=item['scenario'], mode='live', source='sandbox', task=PRESETS[item['scenario']],
                       strategy='graph' if graph else 'react', snapshot=snapshot, evaluationProfile=item['scenario'] + '_full')
        run = create_run(request, provider.model)
        if graph:
            run['graph'] = dict(status='hit', selection='exact', plannerRequests=0, graphId=graph['id'], version=graph['version'],
                                sourceRunId=graph['sourceRunId'], nodeStates={n['id']: 'pending' for n in graph['nodes']}, toolCalls=0, completedNodes=0)
        self.runs.runs[run['id']] = run
        item['runIds'].append(run['id'])
        self.save(item)
        try:
            await execute_run(run, provider, sandbox_tools(item['scenario']), graph=graph,
                              max_steps=config.MAX_STEPS, max_tools=config.MAX_TOOLS, timeout=config.RUN_TIMEOUT)
        finally:
            self.runs.persist(run)
            item['totalModelRequests'] += run['metrics']['modelRequests']
            item['totalTokens'] += (run['metrics']['inputTokens'] or 0) + (run['metrics']['outputTokens'] or 0)
            self.save(item)
        if run['status'] == 'cancelled':
            raise asyncio.CancelledError()
        return run

    async def work(self, item):
        store = GraphStore(self.directory / item['id'] / 'candidates')
        negative = NegativeMotifStore(self.directory / item['id'] / 'negative-motifs')
        parent = None
        try:
            for index in range(item['maxRounds']):
                row = dict(generation=index + 1, parentGraphId=parent['id'] if parent else None, status='learning')
                item['rounds'].append(row)
                training = await self.execute(item, 'base' if index == 0 else 'changed', parent, '执行当前版本并采集轨迹')
                row['sourceRunId'] = training['id']
                row['sourceReflection'] = await negative.learn(training, sandbox_tools(item['scenario']))
                if training['evaluation']['status'] != 'passed' or training['status'] != 'completed':
                    row.update(status='rejected', reason='来源任务未通过完整状态校验')
                    break
                candidate = await store.learn(training, sandbox_tools(item['scenario']))
                candidate['parentGraphId'] = row['parentGraphId']
                write_private(store.directory / (candidate['id'] + '.json'), candidate)
                row.update(candidate=candidate, learning=candidate['validation'])
                if structure(candidate) == structure(parent):
                    row.update(status='stagnated', reason='候选结构与父版本相同，停止进化；不虚增版本')
                    break
                validation = 'changed' if index == 0 else 'exception'
                baseline = await self.execute(item, validation, parent, '验证快照：运行父版本')
                trial = await self.execute(item, validation, candidate, '验证快照：运行候选版本')
                row['candidateReflection'] = await negative.learn(trial, sandbox_tools(item['scenario']))
                row.update(baselineRunId=baseline['id'], candidateRunId=trial['id'],
                           baselineMetrics=baseline['metrics'], candidateMetrics=trial['metrics'],
                           baselineEvaluation=baseline['evaluation'], candidateEvaluation=trial['evaluation'], validationSnapshot=validation)
                if acceptable(baseline, trial):
                    parent = candidate
                    item['activeGraph'] = deepcopy(candidate)
                    row.update(status='promoted', reason='完整状态校验通过，请求数下降，token 和工具错误未增加；单次配对暂定晋升')
                else:
                    row.update(status='rejected', reason='未满足质量与成本晋升门槛，保留父版本')
                    break
                self.save(item)
            item.update(status='completed', phase='实验结束')
        except asyncio.CancelledError:
            item.update(status='cancelled', phase='已取消')
        except Exception as error:
            item.update(status='failed', phase=str(error)[:1000])
        finally:
            self.save(item)
            self.tasks.pop(item['id'], None)

    async def shutdown(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
