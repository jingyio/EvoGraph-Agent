from contextlib import asynccontextmanager
from typing import Literal, Optional
import json
import re
from copy import deepcopy
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse, Response, HTMLResponse
from pydantic import ValidationError, BaseModel, ConfigDict, Field
from . import config
from .domain import markdown
from .models import RunRequest
from .service import RunService, tools_for
from .platform_check import check_platforms
from .taskbank import TaskBank
from .task_runner import TaskRunner, TaskRunRequest
from .paired_evaluation import PairedEvaluation, EvaluationRequest
from .business_report import render_report
from .llm_judge import LLMJudge, JudgeRequest, JUDGE_PROMPT
from .autotool import digest
from .showcase import SHOWCASE_EXPERIMENT, build_pair_detail, build_showcase


class ReportReview(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    factualConsistency: int = Field(ge=0, le=2)
    requirementCoverage: int = Field(ge=0, le=2)
    readability: int = Field(ge=0, le=2)
    note: str = Field(default='', max_length=2000)


class TaskSessionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    taskId: str = Field(min_length=1, max_length=120)


class TaskToolRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    tool: str = Field(min_length=1, max_length=100)
    arguments: dict = Field(default_factory=dict)


def create_app(service=None):
    service = service or RunService()
    taskbank = TaskBank()
    task_runner = TaskRunner(taskbank)
    paired = PairedEvaluation(task_runner)
    judge = LLMJudge(paired)
    @asynccontextmanager
    async def lifespan(app):
        service.restore()
        taskbank.load()
        task_runner.restore()
        paired.restore()
        judge.restore()
        try:
            yield
        finally:
            await judge.shutdown()
            await paired.shutdown()
            await task_runner.shutdown()
            await service.shutdown()
    app = FastAPI(title='RSI Agent Lab', version='0.3.0', lifespan=lifespan)
    app.state.service = service
    app.state.taskbank = taskbank
    app.state.task_runner = task_runner
    app.state.paired = paired
    app.state.judge = judge

    @app.get('/api/evaluations')
    async def evaluation_list():
        return [{k: item.get(k) for k in ['id', 'status', 'createdAt', 'split', 'protocol', 'summary', 'byScenario', 'historicalSetupTokens']}
                for item in sorted(paired.items.values(), key=lambda x: x['createdAt'], reverse=True)]

    def online_e2e_path(key):
        if not key or any(char not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for char in key):
            raise HTTPException(404, 'Online experiment not found')
        return taskbank.root / 'artifacts' / 'online-e2e' / key

    def efficiency_path(key):
        if not key or any(char not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for char in key):
            raise HTTPException(404, 'Efficiency experiment not found')
        return taskbank.root / 'artifacts' / 'efficiency' / key

    @app.get('/api/efficiency/{key}')
    async def efficiency_get(key: str):
        path = efficiency_path(key) / 'result.json'
        if not path.exists():
            raise HTTPException(404, 'Efficiency experiment not found')
        return json.loads(path.read_text())

    @app.get('/api/efficiency/{key}/report', response_class=HTMLResponse)
    async def efficiency_report(key: str):
        path = efficiency_path(key) / 'index.html'
        if not path.exists():
            raise HTTPException(404, 'Efficiency experiment report not found')
        return HTMLResponse(path.read_text(), headers={'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'"})

    @app.get('/api/online-e2e/{key}')
    async def online_e2e_get(key: str):
        path = online_e2e_path(key) / 'result.json'
        if not path.exists():
            raise HTTPException(404, 'Online experiment not found')
        return json.loads(path.read_text())

    @app.get('/api/online-e2e/{key}/report', response_class=HTMLResponse)
    async def online_e2e_report(key: str):
        path = online_e2e_path(key) / 'index.html'
        if not path.exists():
            raise HTTPException(404, 'Online experiment report not found')
        return HTMLResponse(path.read_text(), headers={'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'"})

    @app.get('/api/showcase/{key}')
    async def showcase_get(key: str):
        if key != SHOWCASE_EXPERIMENT:
            raise HTTPException(404, 'Showcase experiment not found')
        try:
            return build_showcase(taskbank.root, taskbank, key)
        except FileNotFoundError:
            raise HTTPException(404, 'Showcase experiment not found')

    @app.get('/api/showcase/{key}/pairs/{task_id}')
    async def showcase_pair_get(key: str, task_id: str):
        if key != SHOWCASE_EXPERIMENT or task_id not in taskbank.tasks:
            raise HTTPException(404, 'Showcase task not found')
        try:
            return build_pair_detail(taskbank.root, taskbank, key, task_id)
        except (FileNotFoundError, KeyError):
            raise HTTPException(404, 'Showcase task not found')

    def online_e2e_run(key, arm, run_id):
        if arm not in ['baseline', 'rsi'] or not re.fullmatch(r'[0-9a-f-]{36}', run_id):
            raise HTTPException(404, 'Online experiment run not found')
        path = online_e2e_path(key) / arm / 'runs' / (run_id + '.json')
        if not path.exists():
            raise HTTPException(404, 'Online experiment run not found')
        run = json.loads(path.read_text())
        if run.get('id') != run_id:
            raise HTTPException(404, 'Online experiment run not found')
        return run

    @app.get('/api/online-e2e/{key}/runs/{arm}/{run_id}')
    async def online_e2e_run_trace(key: str, arm: str, run_id: str):
        return online_e2e_run(key, arm, run_id)

    @app.get('/api/online-e2e/{key}/runs/{arm}/{run_id}/report', response_class=HTMLResponse)
    async def online_e2e_run_report(key: str, arm: str, run_id: str):
        run = online_e2e_run(key, arm, run_id)
        return HTMLResponse(render_report(run, taskbank.task(run['taskId'])), headers={'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'"})

    @app.post('/api/evaluations', status_code=202)
    async def evaluation_start(request: EvaluationRequest):
        if judge.tasks:
            raise ValueError('裁判正在运行，请等待结束后测量 Agent 性能')
        return {'id': (await paired.start(request))['id']}

    @app.get('/api/evaluations/{key}')
    async def evaluation_get(key: str):
        if key not in paired.items:
            raise HTTPException(404, 'Evaluation not found')
        return deepcopy(paired.items[key])

    @app.post('/api/evaluations/{key}/cancel')
    async def evaluation_cancel(key: str):
        if key not in paired.items:
            raise HTTPException(404, 'Evaluation not found')
        task = paired.tasks.get(key)
        if task:
            task.cancel()
        return {'cancelled': bool(task)}

    @app.get('/api/evaluations/{key}/judgements')
    async def judgements_list(key: str):
        if key not in paired.items:
            raise HTTPException(404, 'Evaluation not found')
        return {'items': [j for j in judge.items.values() if j['experimentId'] == key],
                'model': config.JUDGE_MODEL, 'rubricHash': digest(JUDGE_PROMPT), 'sameAsExecutor': config.JUDGE_MODEL == paired.items[key]['protocol']['executor']}

    @app.post('/api/evaluations/{key}/judgements', status_code=202)
    async def judgement_start(key: str, request: JudgeRequest):
        if key not in paired.items:
            raise HTTPException(404, 'Evaluation not found')
        return {'id': (await judge.start(key, request.pairIndex))['id']}

    @app.get('/api/taskbank/evolution')
    async def online_evolution_list():
        return {'versions': task_runner.evolution.versions, 'tinyEdges': task_runner.evolution.tiny_edges,
                'workflows': [{key: item.get(key) for key in ['id', 'sourceRunId', 'sourceGraphId', 'sourceTaskId', 'scenario', 'family']} for item in task_runner.evolution.workflows],
                'runs': [{k: r.get(k) for k in ['id', 'taskId', 'status', 'createdAt', 'split', 'metrics', 'evaluation', 'evolution']}
                         for r in task_runner.runs.values() if r.get('strategy') == 'graph_rsi'],
                'protocol': {'shadowRollouts': 0, 'learningSplit': 'train', 'validation': 'natural-tasks',
                             'test': 'frozen-no-feedback', 'score': 'structured-facts-and-evidence',
                             'inertiaExecution': 'removed; historical traces remain replayable'}}

    @app.get('/api/taskbank/runs')
    async def task_run_list(taskId: Optional[str] = None, limit: int = Query(50, ge=1, le=500)):
        rows = sorted((r for r in task_runner.runs.values() if not taskId or r['taskId'] == taskId), key=lambda r: r['createdAt'], reverse=True)[:limit]
        return {'scheduler': task_runner.status(), 'runs': [{k: r[k] for k in ['id', 'taskId', 'status', 'strategy', 'phase', 'createdAt', 'models', 'metrics', 'evaluation']} for r in rows]}

    @app.post('/api/taskbank/runs', status_code=202)
    async def task_run_start(request: TaskRunRequest):
        if judge.tasks:
            raise ValueError('裁判正在运行，请等待结束后执行任务')
        if paired.tasks:
            raise ValueError('冻结成对评测正在运行，请等待评测结束或取消评测')
        return {'id': (await task_runner.start(request))['id']}

    @app.get('/api/taskbank/runs/{key}')
    async def task_run_get(key: str):
        if key not in task_runner.runs:
            raise HTTPException(404, 'Task run not found')
        result = deepcopy(task_runner.runs[key])
        result['comparison'] = task_runner.compare_with_baseline(task_runner.runs[key])
        result['planReactComparison'] = task_runner.compare_with_strategy(task_runner.runs[key], 'plan_react') if result.get('strategy') in ['autotool', 'graph_rsi'] else None
        result['reusedPlanReactComparison'] = task_runner.compare_with_strategy(task_runner.runs[key], 'plan_react_reuse') if result.get('strategy') == 'graph_rsi' else None
        return result

    @app.get('/api/taskbank/runs/{key}/report', response_class=HTMLResponse)
    async def task_report(key: str):
        if key not in task_runner.runs:
            raise HTTPException(404, 'Task run not found')
        run = task_runner.runs[key]
        return HTMLResponse(render_report(run, taskbank.task(run['taskId'])), headers={'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'"})

    @app.post('/api/taskbank/runs/{key}/review')
    async def task_review(key: str, request: ReportReview):
        if key not in task_runner.runs:
            raise HTTPException(404, 'Task run not found')
        run = task_runner.runs[key]
        if run['status'] in ['running', 'queued']:
            raise ValueError('请等待任务结束后复核报告')
        from .domain import now
        run['manualReview'] = dict(request.model_dump(), status='reviewed', at=now(), source='human')
        task_runner.save(run)
        return run['manualReview']

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

    @app.get('/api/tools')
    def tools(scenario: Literal['finance', 'support'], source: Literal['erpnext', 'zammad']):
        return [t.card() for t in tools_for({'scenario': scenario, 'source': source})]

    @app.get('/api/runs')
    def history():
        return service.history()

    @app.post('/api/runs', status_code=202)
    async def start(request: RunRequest):
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
    def graphs(scenario: Optional[Literal['finance', 'support']] = None, source: Optional[Literal['erpnext', 'zammad']] = None):
        return service.graphs.list(scenario, source)

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
