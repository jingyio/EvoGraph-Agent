import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import time
from uuid import uuid4, UUID
from . import config
from .domain import now
from .autotool import digest
from .graph import compile_read_graph, ordered_nodes, run_read_graph, contract_hash, task_key, applicable
from .gagent import retrieve
from .tools import ToolContext
from .runtime import create_run


def environment_hash(source):
    return digest({'source': source, 'url': 'synthetic-v1' if source == 'sandbox' else os.getenv(source.upper() + '_BASE_URL', 'unconfigured'), 'runtime': 'python-v1'})


def write_private(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.' + str(uuid4()) + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n' if not isinstance(value, str) else value)
    os.replace(temporary, path)


class GraphStore:
    def __init__(self, directory=None):
        self.directory = Path(directory or config.ARTIFACTS / 'graphs-python')
        self.graphs = {}
        self.lock = asyncio.Lock()

    def restore(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        for path in self.directory.glob('*.json'):
            try:
                graph = json.loads(path.read_text())
                UUID(graph['id'])
                if path.stem == graph['id'] and graph.get('scope') == 'read-prefix' and graph.get('validation', {}).get('status') == 'passed' and isinstance(graph.get('nodes'), list):
                    self.graphs[graph['id']] = graph
            except (ValueError, KeyError, TypeError):
                continue

    def list(self, scenario=None, source=None):
        return sorted([g for g in self.graphs.values() if (not scenario or g['scenario'] == scenario) and (not source or g['source'] == source)], key=lambda g: (g['version'], g['createdAt']), reverse=True)

    def select(self, request, tools):
        candidates = self.list(request['scenario'], request['source'])
        environment = environment_hash(request['source'])
        for graph in candidates:
            if not applicable(graph, request, tools, environment):
                ordered_nodes(graph['nodes'], tools)
                return {'graph': graph, 'candidates': [], 'reason': None}
        return {'graph': None, 'candidates': retrieve(candidates, request, tools, environment), 'reason': '尚无精确适用的已验证读取图'}

    async def learn(self, run, tools):
        async with self.lock:
            existing = next((g for g in self.list() if g['sourceRunId'] == run['id'] and g['contractHash'] == contract_hash(tools) and g['environmentHash'] == environment_hash(run['request']['source'])), None)
            if existing:
                return existing
            started = time.monotonic()
            nodes = compile_read_graph(run, tools)
            ordered_nodes(nodes, tools)
            compile_ms = round((time.monotonic() - started) * 1000)
            probe = create_run(dict(run['request'], strategy='react'))
            probe['initial'], probe['state'] = deepcopy(run['initial']), deepcopy(run['initial'])
            context, calls = ToolContext(probe), 0
            by_name = {t.name: t for t in tools}
            async def invoke(name, args, node):
                nonlocal calls
                calls += 1
                if calls > 60:
                    raise ValueError('影子验证超过 60 次读取')
                return await by_name[name].execute(args, context)
            validation_start = time.monotonic()
            await asyncio.wait_for(run_read_graph(nodes, tools, invoke), timeout=60)
            if probe['initial'] != probe['state']:
                raise ValueError('读取工具修改了业务状态，拒绝学习')
            key = task_key(run['request']['task'])
            version = max([0] + [g['version'] for g in self.list(run['request']['scenario'], run['request']['source']) if g['taskKey'] == key]) + 1
            graph = {'id': str(uuid4()), 'version': version, 'createdAt': now(), 'sourceRunId': run['id'], 'scenario': run['request']['scenario'], 'source': run['request']['source'],
                     'task': run['request']['task'], 'taskKey': key, 'contractHash': contract_hash(tools), 'environmentHash': environment_hash(run['request']['source']), 'nodes': nodes,
                     'sourceModelRequests': run['metrics']['modelRequests'], 'sourceInputTokens': run['metrics']['inputTokens'], 'sourceOutputTokens': run['metrics']['outputTokens'],
                     'validation': {'status': 'passed', 'toolCalls': calls, 'durationMs': round((time.monotonic() - validation_start) * 1000), 'compileMs': compile_ms, 'learningModelRequests': 0},
                     'scope': 'read-prefix', 'compilerVersion': 1, 'backend': 'python'}
            write_private(self.directory / (graph['id'] + '.json'), graph)
            self.graphs[graph['id']] = graph
            return graph
