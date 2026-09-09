"""Repeated paired evaluations with frozen experience and uncensored failures."""
import asyncio
from copy import deepcopy
import json
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field
from . import config
from .autotool import digest
from .domain import PRESETS, now
from .graph import contract_hash
from .graph_store import write_private
from .model_client import ModelClient, ModelOptions
from .runtime import create_run, execute_run
from .tools import sandbox_tools


class ReliabilityRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    scenario: Literal['finance', 'support'] = 'finance'
    rounds: int = Field(default=3, ge=1, le=30)


def summarize_run(run, tools):
    kinds = {t.name: t.effect for t in tools}
    counters = {key: {'attempts': 0, 'errors': 0} for key in ['graph', 'model', 'read', 'write']}
    errors = []
    action = None
    for observation in run['events']:
        if observation['type'] == 'action':
            action = observation
            continue
        if observation['type'] != 'observation' or action is None:
            continue
        executor = 'graph' if action['detail'].get('executor') == 'graph' else 'model'
        effect = 'read' if kinds.get(action['title']) == 'read' else 'write'
        for key in [executor, effect]:
            counters[key]['attempts'] += 1
            counters[key]['errors'] += int(observation['detail'].get('ok') is False)
        if observation['detail'].get('ok') is False:
            errors.append(dict(eventSeq=action['seq'], tool=action['title'], executor=executor, error=observation['detail'].get('error')))
        action = None
    return dict(runId=run['id'], status=run['status'], metrics=deepcopy(run['metrics']), evaluation=deepcopy(run['evaluation']),
                statePassed=run['status'] == 'completed' and run['evaluation']['status'] == 'passed',
                counters=counters, errors=errors, terminalError=run.get('error'),
                graphStatus=run.get('graph', {}).get('status'),
                guardHits=run.get('negativeMotif', {}).get('guardHits', 0), initialHash=digest(run['initial']))


def totals(item):
    summary = {}
    for arm in item['arms']:
        rows = [r for r in item['rows'] if r['arm'] == arm]
        metrics = dict(runs=len(rows), statePassed=sum(r['statePassed'] for r in rows),
                       runsWithToolErrors=sum(r['metrics']['toolErrors'] > 0 for r in rows),
                       modelRequests=sum(r['metrics']['modelRequests'] for r in rows),
                       toolCalls=sum(r['metrics']['toolCalls'] for r in rows), toolErrors=sum(r['metrics']['toolErrors'] for r in rows),
                       guardHits=sum(r['guardHits'] for r in rows),
                       graphFallbacks=sum(r.get('graphStatus') == 'fallback' for r in rows),
                       interruptedRuns=sum(bool(r.get('terminalError')) for r in rows),
                       usageComplete=all(r['metrics']['usageComplete'] for r in rows),
                       tokens=sum((r['metrics']['inputTokens'] or 0) + (r['metrics']['outputTokens'] or 0) for r in rows))
        metrics['counters'] = {k: {field: sum(r['counters'][k][field] for r in rows) for field in ['attempts', 'errors']} for k in ['graph', 'model', 'read', 'write']}
        summary[arm] = metrics
    return summary


class ReliabilityService:
    def __init__(self, runs):
        self.runs = runs
        self.directory = runs.directory / 'reliability'
        self.items, self.tasks = {}, {}

    def save(self, item):
        item['totals'] = totals(item)
        write_private(self.directory / (item['id'] + '.json'), item)

    def restore(self):
        for path in self.directory.glob('*.json'):
            try:
                item = json.loads(path.read_text())
                if path.stem != item['id']:
                    continue
                for row in item['rows']:
                    if 'graphStatus' not in row and row['runId'] in self.runs.runs:
                        row['graphStatus'] = self.runs.runs[row['runId']].get('graph', {}).get('status')
                if item['status'] == 'running':
                    item.update(status='interrupted', phase='服务中断，未完成配对不补造结果')
                self.save(item)
                self.items[item['id']] = item
            except (ValueError, KeyError, TypeError, OSError):
                continue

    def provider(self):
        if self.runs.provider_factory:
            return self.runs.provider_factory()
        return ModelClient(ModelOptions(config.BASE_URL, config.API_KEY, config.MODEL, config.MODEL_TIMEOUT))

    async def start(self, request):
        if self.tasks or self.runs.tasks:
            raise ValueError('请等待当前执行结束后开始稳定性实验')
        task_request = dict(scenario=request.scenario, source='sandbox', task=PRESETS[request.scenario])
        tools = sandbox_tools(request.scenario)
        graph = self.runs.graphs.select(task_request, tools)['graph']
        if not graph:
            raise ValueError('需要该预设任务的已验证读取图，才能进行固定经验对照')
        motifs = self.runs.negative.select(task_request, tools) if request.scenario == 'finance' else []
        if request.scenario == 'finance' and not motifs:
            raise ValueError('请先从财务失败轨迹提取已验证负 motif')
        provider = self.provider()
        arms = ['react', 'graph', 'graph_negative'] if motifs else ['react', 'graph']
        item = dict(id=str(uuid4()), createdAt=now(), scenario=request.scenario, maxRounds=request.rounds,
                    status='running', phase='准备执行', arms=arms, rows=[], currentRunId=None,
                    model=provider.model, modelSettings=deepcopy(getattr(provider, 'settings', {})),
                    graph=deepcopy(graph), negativeMotifs=deepcopy(motifs), contractHash=contract_hash(tools),
                    limits=dict(max_steps=config.MAX_STEPS, max_tools=config.MAX_TOOLS, timeout=config.RUN_TIMEOUT),
                    snapshots=['base', 'changed', 'exception'], reportQuality='not_evaluated',
                    note='经验冻结；轮换执行顺序；同轮相同快照；所有失败保留。开发快照重复使用，非独立测试集。')
        self.items[item['id']] = item
        self.save(item)
        task = asyncio.create_task(self.work(item))
        self.tasks[item['id']] = task
        def cleanup(done):
            if done.cancelled() and item['status'] == 'running':
                item.update(status='cancelled', phase='已取消')
                self.save(item)
            self.tasks.pop(item['id'], None)
        task.add_done_callback(cleanup)
        return item

    async def work(self, item):
        try:
            for round_index in range(item['maxRounds']):
                offset = round_index % len(item['arms'])
                order = item['arms'][offset:] + item['arms'][:offset]
                snapshot = item['snapshots'][round_index % len(item['snapshots'])]
                for arm in order:
                    provider = self.provider()
                    if provider.model != item['model'] or getattr(provider, 'settings', {}) != item['modelSettings']:
                        raise ValueError('模型配置改变，停止配对')
                    graph = item['graph'] if arm != 'react' else None
                    request = dict(scenario=item['scenario'], source='sandbox', task=PRESETS[item['scenario']], mode='live',
                                   strategy='graph' if graph else 'react', negativeMotifs=arm == 'graph_negative',
                                   snapshot=snapshot, evaluationProfile=item['scenario'] + '_full')
                    run = create_run(request, provider.model)
                    if graph:
                        run['graph'] = dict(status='hit', selection='exact', plannerRequests=0, graphId=graph['id'], version=graph['version'],
                                            sourceRunId=graph['sourceRunId'], nodeStates={n['id']: 'pending' for n in graph['nodes']}, toolCalls=0, completedNodes=0)
                    self.runs.runs[run['id']] = run
                    item.update(currentRunId=run['id'], phase=f'第 {round_index + 1}/{item["maxRounds"]} 轮 · {snapshot} · {arm}')
                    self.save(item)
                    tools = sandbox_tools(item['scenario'])
                    await execute_run(run, provider, tools, graph=graph, negative_motifs=item['negativeMotifs'], **item['limits'])
                    self.runs.persist(run)
                    row = summarize_run(run, tools)
                    row.update(round=round_index + 1, snapshot=snapshot, arm=arm)
                    item['rows'].append(row)
                    self.save(item)
                    if run['status'] == 'cancelled':
                        raise asyncio.CancelledError()
            item.update(status='completed', phase='全部配对结束')
        except asyncio.CancelledError:
            item.update(status='cancelled', phase='已取消，保留已执行结果')
        except Exception as error:
            item.update(status='failed', phase=str(error)[:1000])
        finally:
            item['currentRunId'] = None
            self.save(item)
            self.tasks.pop(item['id'], None)

    async def shutdown(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
