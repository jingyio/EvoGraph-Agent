import asyncio
from copy import deepcopy
import json
from pathlib import Path
from uuid import UUID
from . import config
from .models import RunRequest
from .model_client import ModelClient, ModelOptions
from .connectors import platform_tools
from .runtime import create_run, execute_run
from .graph_store import GraphStore, write_private
from .domain import markdown, now
from .evaluation import evaluate


def tools_for(request):
    return platform_tools(request['source'])


class RunService:
    def __init__(self, artifacts=None, provider_factory=None):
        self.directory = Path(artifacts or config.ARTIFACTS)
        self.runs, self.tasks = {}, {}
        self.graphs = GraphStore(self.directory / 'graphs-python')
        self.provider_factory = provider_factory

    def restore(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.graphs.restore()
        for folder in self.directory.iterdir():
            if not folder.is_dir():
                continue
            try:
                UUID(folder.name)
                run = json.loads((folder / 'run.json').read_text())
                if run['request'].get('source') in ['erpnext', 'zammad'] and run['id'] == folder.name and run.get('finishedAt') and isinstance(run.get('events'), list):
                    self.runs[run['id']] = run
            except (ValueError, KeyError, TypeError, OSError):
                continue

    def view(self, run):
        value = deepcopy(run)
        if run['id'] in self.tasks:
            value['status'] = 'running'
        return value

    def history(self):
        rows = sorted(self.runs.values(), key=lambda run: run['startedAt'], reverse=True)[:30]
        return [{key: self.view(run)[key] for key in ['id', 'request', 'status', 'startedAt', 'metrics']} for run in rows]

    def persist(self, run):
        folder = self.directory / run['id']
        write_private(folder / 'run.json', run)
        write_private(folder / 'report.md', markdown(run))

    async def start(self, raw):
        request = RunRequest.model_validate(raw).model_dump()
        if len(self.tasks) >= 2:
            raise ValueError('已有两个任务运行中，请等待或取消。')
        if self.provider_factory:
            provider = self.provider_factory()
        else:
            provider = ModelClient(ModelOptions(config.BASE_URL, config.API_KEY, config.MODEL, config.MODEL_TIMEOUT))
        tools = tools_for(request)
        run = create_run(request, provider.model)
        selection = self.graphs.select(request, tools) if request['strategy'] == 'graph' else None
        if selection:
            graph = selection['graph']
            run['graph'] = {'status': 'hit' if graph else 'miss', 'selection': 'exact' if graph else 'none', 'plannerRequests': 0,
                            'reason': selection['reason'], 'nodeStates': {n['id']: 'pending' for n in graph['nodes']} if graph else {}, 'toolCalls': 0, 'completedNodes': 0}
            if graph:
                run['graph'].update(graphId=graph['id'], version=graph['version'], sourceRunId=graph['sourceRunId'])
        self.runs[run['id']] = run

        async def work():
            try:
                await execute_run(run, provider, tools, max_steps=config.MAX_STEPS, max_tools=config.MAX_TOOLS, timeout=config.RUN_TIMEOUT,
                                  graph=selection['graph'] if selection else None, candidates=selection['candidates'] if selection else None)
                info = run.get('graph')
                if run['status'] == 'completed' and info and (info['status'] != 'hit' or info['selection'] == 'adapted'):
                    try:
                        graph = await self.graphs.learn(run, tools)
                        info.update(learnedGraphId=graph['id'], learning=graph['validation'])
                        run['events'].append({'seq': len(run['events']) + 1, 'at': now(), 'type': 'graph', 'title': f"读取图 v{graph['version']} 校验通过并保存", 'detail': {'graphId': graph['id'], 'learning': graph['validation']}})
                    except asyncio.CancelledError:
                        info['learningError'] = '学习已取消；保留任务执行结果。'
                    except Exception as error:
                        info['learningError'] = str(error)[:1500]
            finally:
                try:
                    self.persist(run)
                except OSError:
                    run['error'] = '结果写入磁盘失败，请从页面导出。'
                self.tasks.pop(run['id'], None)
        task = asyncio.create_task(work())
        self.tasks[run['id']] = task
        def cleanup_unstarted(done):
            if run['id'] not in self.tasks:
                return
            run.update(status='cancelled' if done.cancelled() else 'failed', finishedAt=now(), error='任务在开始执行前被取消。' if done.cancelled() else '后台任务异常结束。')
            try:
                self.persist(run)
            finally:
                self.tasks.pop(run['id'], None)
        task.add_done_callback(cleanup_unstarted)
        return run

    def cancel(self, key):
        task = self.tasks.get(key)
        if task:
            task.cancel()
            return True
        return False

    async def learn(self, key):
        if key not in self.runs:
            raise KeyError(key)
        if key in self.tasks:
            raise ValueError('请等待执行和保存完成')
        run = self.runs[key]
        candidate = deepcopy(run)
        candidate['evaluation'] = evaluate(candidate, candidate['request'].get('evaluationProfile', 'auto'))
        return await self.graphs.learn(candidate, tools_for(candidate['request']))

    async def shutdown(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
