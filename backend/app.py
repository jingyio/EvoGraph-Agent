from contextlib import asynccontextmanager
from typing import Literal, Optional
import json
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse, Response
from pydantic import ValidationError, BaseModel, ConfigDict, Field
from . import config
from .domain import seed, markdown
from .models import RunRequest
from .service import RunService, tools_for
from .platform_check import check_platforms
from .evolution import EvolutionService, EvolutionRequest
from .reliability import ReliabilityService, ReliabilityRequest
from .taskbank import TaskBank
from .task_runner import TaskRunner, TaskRunRequest


class TaskSessionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    taskId: str = Field(min_length=1, max_length=120)


class TaskToolRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    tool: str = Field(min_length=1, max_length=100)
    arguments: dict = Field(default_factory=dict)


def create_app(service=None):
    service = service or RunService()
    evolution = EvolutionService(service)
    reliability = ReliabilityService(service)
    taskbank = TaskBank()
    task_runner = TaskRunner(taskbank)
    @asynccontextmanager
    async def lifespan(app):
        service.restore()
        evolution.restore()
        reliability.restore()
        taskbank.load()
        task_runner.restore()
        try:
            yield
        finally:
            await task_runner.shutdown()
            await reliability.shutdown()
            await evolution.shutdown()
            await service.shutdown()
    app = FastAPI(title='RSI Agent Lab', version='0.3.0', lifespan=lifespan)
    app.state.service = service
    app.state.evolution = evolution
    app.state.reliability = reliability
    app.state.taskbank = taskbank
    app.state.task_runner = task_runner

    @app.get('/api/taskbank/runs')
    def task_run_list():
        rows = sorted(task_runner.runs.values(), key=lambda r: r['createdAt'], reverse=True)[:50]
        return {'scheduler': task_runner.status(), 'runs': [{k: r[k] for k in ['id', 'taskId', 'status', 'strategy', 'phase', 'models', 'metrics', 'evaluation']} for r in rows]}

    @app.post('/api/taskbank/runs', status_code=202)
    async def task_run_start(request: TaskRunRequest):
        return {'id': (await task_runner.start(request))['id']}

    @app.get('/api/taskbank/runs/{key}')
    def task_run_get(key: str):
        if key not in task_runner.runs:
            raise HTTPException(404, 'Task run not found')
        result = dict(task_runner.runs[key])
        result['comparison'] = task_runner.compare_with_baseline(task_runner.runs[key])
        result['planReactComparison'] = task_runner.compare_with_strategy(task_runner.runs[key], 'plan_react') if result.get('strategy') == 'autotool' else None
        return result

    @app.post('/api/taskbank/runs/{key}/cancel')
    async def task_run_cancel(key: str):
        if key not in task_runner.runs:
            raise HTTPException(404, 'Task run not found')
        job = task_runner.tasks.get(key)
        if job:
            job.cancel()
        return {'cancelled': bool(job)}

    @app.get('/api/taskbank/manifest')
    def taskbank_manifest():
        return {'manifest': taskbank.manifest, 'ready': bool(taskbank.gold)}

    @app.get('/api/taskbank/tasks')
    def taskbank_tasks(scenario: Optional[Literal['finance', 'support', 'tickets']] = None, split: Optional[Literal['train', 'validation', 'test']] = None):
        return [t for t in taskbank.tasks.values() if (not scenario or t['scenario'] == scenario) and (not split or t['split'] == split)]

    @app.get('/api/taskbank/tasks/{key}/tools')
    def taskbank_tools(key: str):
        return [t.card() for t in taskbank.tools(key)]

    @app.post('/api/taskbank/sessions', status_code=201)
    def taskbank_session(request: TaskSessionRequest):
        return taskbank.start(request.taskId)

    @app.post('/api/taskbank/sessions/{key}/call')
    async def taskbank_call(key: str, request: TaskToolRequest):
        return await taskbank.call(key, request.tool, request.arguments)

    @app.middleware('http')
    async def api_boundary(request, call_next):
        if request.url.path.startswith('/api'):
            origin = request.headers.get('origin')
            if origin and origin not in [f'http://127.0.0.1:{config.PORT}', f'http://localhost:{config.PORT}', 'http://127.0.0.1:5173', 'http://localhost:5173']:
                return JSONResponse({'error': 'Origin not allowed'}, status_code=403)
            if request.method not in ['GET', 'HEAD']:
                if request.headers.get('content-type', '').split(';')[0] != 'application/json':
                    return JSONResponse({'error': 'Use application/json'}, status_code=415)
                body = await request.body()
                if len(body) > 32768:
                    return JSONResponse({'error': 'Request body too large'}, status_code=413)
        response = await call_next(request)
        if request.url.path.startswith('/api'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, error):
        return JSONResponse({'error': str(error)[:1500]}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Avoid echoing request values in validation responses.
        return JSONResponse({'error': '; '.join('.'.join(map(str, item['loc'])) + ': ' + item['msg'] for item in error.errors())}, status_code=400)

    @app.exception_handler(RuntimeError)
    async def runtime_error(request, error):
        return JSONResponse({'error': str(error)[:1500]}, status_code=422)

    def get_run(key):
        if key not in service.runs:
            raise HTTPException(404, 'Run not found')
        return service.runs[key]

    @app.get('/api/config')
    def configuration():
        return config.public_config()

    @app.get('/api/evolutions')
    def evolutions():
        return sorted(evolution.items.values(), key=lambda item: item['createdAt'], reverse=True)

    @app.post('/api/evolutions', status_code=202)
    async def start_evolution(request: EvolutionRequest):
        if reliability.tasks:
            raise ValueError('稳定性实验正在运行，请等待或停止后再启动其他执行')
        return await evolution.start(request)

    @app.get('/api/reliability')
    def reliability_history():
        return sorted(reliability.items.values(), key=lambda item: item['createdAt'], reverse=True)

    @app.post('/api/reliability', status_code=202)
    async def start_reliability(request: ReliabilityRequest):
        if evolution.tasks:
            raise ValueError('请等待进化实验结束后再开始稳定性对照')
        return await reliability.start(request)

    @app.post('/api/reliability/{key}/cancel')
    async def cancel_reliability(key: str):
        if key not in reliability.items:
            raise HTTPException(404, 'Experiment not found')
        task = reliability.tasks.get(key)
        if task:
            task.cancel()
        return {'cancelled': bool(task)}

    @app.get('/api/reliability/{key}/export')
    def export_reliability(key: str):
        if key not in reliability.items:
            raise HTTPException(404, 'Experiment not found')
        return Response(json.dumps(reliability.items[key], ensure_ascii=False, indent=2), media_type='application/json', headers={'Content-Disposition': f'attachment; filename="reliability-{key}.json"'})

    @app.post('/api/evolutions/{key}/cancel')
    async def cancel_evolution(key: str):
        task = evolution.tasks.get(key)
        if task:
            task.cancel()
        return {'cancelled': bool(task)}

    @app.get('/api/snapshot')
    def snapshot(variant: Literal['base', 'changed', 'exception'] = 'base'):
        return seed(variant)

    @app.get('/api/tools')
    def tools(scenario: Literal['finance', 'support'], source: Literal['sandbox', 'erpnext', 'zammad'] = 'sandbox'):
        return [t.card() for t in tools_for({'scenario': scenario, 'source': source})]

    @app.get('/api/runs')
    def history():
        return service.history()

    @app.post('/api/runs', status_code=202)
    async def start(request: RunRequest):
        if reliability.tasks:
            raise ValueError('稳定性实验正在运行，请等待或停止后再启动其他执行')
        run = await service.start(request.model_dump())
        return {'id': run['id']}

    @app.get('/api/runs/{key}')
    def run(key: str):
        return service.view(get_run(key))

    @app.post('/api/runs/{key}/cancel')
    async def cancel(key: str):
        get_run(key)
        return {'cancelled': service.cancel(key)}

    @app.post('/api/runs/{key}/learn')
    async def learn(key: str):
        get_run(key)
        return await service.learn(key)

    @app.get('/api/runs/{key}/export/{format}')
    def export_run(key: str, format: Literal['json', 'md']):
        value = get_run(key)
        body = json.dumps(value, ensure_ascii=False, indent=2) if format == 'json' else markdown(value)
        return Response(body, media_type='application/json' if format == 'json' else 'text/markdown', headers={'Content-Disposition': f'attachment; filename="run-{key}.{format}"'})

    @app.get('/api/graphs')
    def graphs(scenario: Optional[Literal['finance', 'support']] = None, source: Optional[Literal['sandbox', 'erpnext', 'zammad']] = None):
        return service.graphs.list(scenario, source)

    @app.get('/api/negative-motifs')
    def negative_motifs():
        return list(service.negative.motifs.values())

    @app.post('/api/runs/{key}/reflect')
    async def reflect(key: str):
        get_run(key)
        return await service.reflect(key)

    @app.get('/api/graphs/{key}/export')
    def export_graph(key: str):
        if key not in service.graphs.graphs:
            raise HTTPException(404, 'Graph not found')
        return Response(json.dumps(service.graphs.graphs[key], ensure_ascii=False, indent=2), media_type='application/json', headers={'Content-Disposition': f'attachment; filename="graph-{key}.json"'})

    @app.post('/api/platforms/check')
    async def platforms():
        return await check_platforms()

    @app.get('/{path:path}')
    def frontend(path: str):
        if path.startswith('api/'):
            raise HTTPException(404, 'Unknown API route')
        dist = (config.ROOT / 'dist').resolve()
        candidate = (dist / path).resolve()
        if dist != candidate and dist not in candidate.parents:
            raise HTTPException(404)
        if candidate.is_file():
            return FileResponse(candidate)
        if (dist / 'index.html').exists():
            return FileResponse(dist / 'index.html')
        return JSONResponse({'error': 'Run npm run build to create the React frontend'}, status_code=503)
    return app


app = create_app()
