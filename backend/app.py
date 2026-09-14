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
from .trajectory_experiment import TrajectoryExperiment
from .llm_judge import LLMJudge, JudgeRequest, JUDGE_PROMPT
from .autotool import digest
from .showcase import SHOWCASE_EXPERIMENT, build_pair_detail, build_showcase
from .live_showcase import LiveShowcase
from .workspace import WorkspaceManager, WorkspaceBank, WORKSPACE_ROLES
from .workpacks import install_workpack, list_workpacks
from .workpack_experiment import WorkpackExperiment
from .workpack_judge import WorkpackJudge


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


class LiveShowcaseRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    taskId: str = Field(min_length=1, max_length=120)
    steps: int = Field(default=2, ge=1, le=2)
    # A live showcase makes real provider requests. Keep this acknowledgement
    # in the API boundary so a direct caller cannot start a run by accident.
    confirmCost: bool = False


class WorkspaceCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    role: Literal['finance', 'support', 'tickets']
    label: str = Field(default='未命名工作区', min_length=1, max_length=120)


class WorkspaceTaskRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request: str = Field(min_length=1, max_length=6000)
    title: Optional[str] = Field(default=None, max_length=180)
    answers: dict[str, str] = Field(default_factory=dict)
    followupRunId: Optional[str] = Field(default=None, max_length=100)


class WorkspaceRunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    strategy: Literal['plan_react', 'graph_rsi'] = 'graph_rsi'
    confirmCost: bool = False


class WorkpackExperimentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    mode: Literal['smoke_v4', 'precheck_v4', 'full_train_v2', 'smoke_v5', 'precheck_v5', 'full_train_v3',
                  'smoke_v6', 'precheck_v6', 'full_train_v4', 'smoke_v7', 'precheck_v7', 'full_train_v5',
                  'smoke_v8', 'precheck_v8', 'full_train_v6', 'smoke_v9', 'precheck_v9', 'full_train_v7',
                  'smoke_v10', 'precheck_v10', 'full_train_v8', 'smoke_v11', 'precheck_v11', 'full_train_v9',
                  'smoke_v12', 'precheck_v12', 'full_train_v10', 'smoke_v13', 'precheck_v13', 'full_train_v11',
                  'smoke_v14', 'precheck_v14', 'full_train_v12', 'smoke_v15', 'precheck_v15', 'full_train_v13',
                  'smoke_v16', 'precheck_v16', 'full_train_v14', 'smoke_v17', 'precheck_v17', 'full_train_v15'] = 'smoke_v17'
    confirmCost: bool = False


class WorkpackJudgeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    confirmCost: bool = False


def create_app(service=None):
    service = service or RunService()
    taskbank = TaskBank()
    task_runner = TaskRunner(taskbank)
    workspace_manager = WorkspaceManager(taskbank.root)
    workspace_bank = WorkspaceBank(workspace_manager)
    workspace_runner = TaskRunner(workspace_bank, run_limit=1, model_limit=1, read_limit=1,
                                  run_directory=taskbank.root / 'artifacts' / 'workspace-runs',
                                  evolution_path=taskbank.root / 'artifacts' / 'workspace-runtime' / 'experience.json',
                                  learning_enabled=False)
    trajectory_experiment = TrajectoryExperiment(taskbank.root)
    workpack_experiment = WorkpackExperiment(taskbank, taskbank.root)
    workpack_judge = WorkpackJudge(workpack_experiment, taskbank.root)
    paired = PairedEvaluation(task_runner)
    judge = LLMJudge(paired)
    live_showcase = LiveShowcase(taskbank, taskbank.root)
    @asynccontextmanager
    async def lifespan(app):
        service.restore()
        taskbank.load()
        workspace_bank.load()
        task_runner.restore()
        workspace_runner.restore()
        trajectory_experiment.restore()
        workpack_experiment.restore()
        workpack_judge.restore()
        paired.restore()
        judge.restore()
        try:
            yield
        finally:
            await judge.shutdown()
            await paired.shutdown()
            await task_runner.shutdown()
            await workspace_runner.shutdown()
            await workpack_judge.shutdown()
            await trajectory_experiment.shutdown()
            await workpack_experiment.shutdown()
            await live_showcase.shutdown()
            await service.shutdown()
    app = FastAPI(title='RSI Agent Lab', version='0.3.0', lifespan=lifespan)
    app.state.service = service
    app.state.taskbank = taskbank
    app.state.task_runner = task_runner
    app.state.workspace_manager = workspace_manager
    app.state.workspace_runner = workspace_runner
    app.state.workpack_experiment = workpack_experiment
    app.state.workpack_judge = workpack_judge
    app.state.paired = paired
    app.state.judge = judge
    app.state.live_showcase = live_showcase

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

    @app.post('/api/live-showcase', status_code=202)
    async def live_showcase_start(request: LiveShowcaseRequest):
        if judge.tasks or paired.tasks or workpack_judge.tasks:
            raise ValueError('裁判或冻结评测正在运行；在线展示保持独占以避免干扰计量')
        if live_showcase.tasks:
            raise HTTPException(409, '已有在线展示正在运行；请先等待完成或停止该会话')
        if not request.confirmCost:
            raise HTTPException(400, '在线展示会发起真实模型请求；请确认费用后再启动')
        try:
            item = await live_showcase.start(request.taskId, request.steps)
        except ValueError as error:
            raise HTTPException(400, str(error))
        return {'id': item['id'], 'status': item['status'], 'taskIds': item['taskIds']}

    @app.get('/api/live-showcase/{key}')
    async def live_showcase_get(key: str):
        try:
            return live_showcase.get(key)
        except KeyError:
            raise HTTPException(404, 'Live showcase run not found')

    @app.get('/api/live-showcase/{key}/runs/{arm}/{run_id}')
    async def live_showcase_run(key: str, arm: str, run_id: str):
        try:
            return live_showcase.run(key, arm, run_id)
        except KeyError:
            raise HTTPException(404, 'Live showcase run not found')

    @app.post('/api/live-showcase/{key}/cancel')
    async def live_showcase_cancel(key: str):
        task = live_showcase.tasks.get(key)
        if not task:
            try:
                live_showcase.get(key)
            except KeyError:
                raise HTTPException(404, 'Live showcase run not found')
            return {'cancelled': False}
        task.cancel()
        return {'cancelled': True}

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
        if judge.tasks or workpack_judge.tasks:
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

    @app.get('/api/workspaces')
    def workspace_list():
        return [workspace_manager.public_workspace(key) for key in sorted(workspace_manager.workspaces)]

    @app.post('/api/workspaces', status_code=201)
    def workspace_create(request: WorkspaceCreateRequest):
        return workspace_manager.create(request.role, label=request.label)

    @app.get('/api/workspaces/{key}/tables/{table_id}/preview')
    def workspace_preview(key: str, table_id: str, limit: int = Query(8, ge=1, le=50)):
        return workspace_manager.preview(key, table_id, limit)

    @app.get('/api/workpacks')
    def workpack_list(scenario: Optional[Literal['finance', 'support', 'tickets']] = None):
        rows = list_workpacks(taskbank)
        return [row for row in rows if not scenario or row['scenario'] == scenario]

    @app.get('/api/trajectory-experiments')
    def trajectory_list():
        return [{'id':i['id'], 'createdAt':i['createdAt'], 'mode':i['mode'], 'status':i['status'], 'summary':trajectory_experiment.get(i['id'])['summary']} for i in sorted(trajectory_experiment.items.values(), key=lambda item: item['createdAt'])]

    @app.post('/api/trajectory-experiments', status_code=202)
    async def trajectory_start(request: WorkspaceRunRequest, mode: Literal['precheck', 'full'] = 'precheck'):
        if not request.confirmCost:
            raise HTTPException(400, '需要确认真实模型费用')
        if workspace_runner.tasks or workpack_experiment.tasks:
            raise HTTPException(409, '已有工作区或工作包任务在途')
        try:
            return await trajectory_experiment.start(mode)
        except ValueError as error:
            raise HTTPException(400, str(error))

    @app.get('/api/trajectory-experiments/{key}')
    def trajectory_get(key: str):
        if key not in trajectory_experiment.items: raise HTTPException(404, '实验不存在')
        return trajectory_experiment.dashboard(key)

    @app.get('/api/trajectory-experiments/{key}/runs/{arm}/{run_id}')
    def trajectory_run(key: str, arm: str, run_id: str):
        try: return trajectory_experiment.run(key, arm, run_id)
        except (KeyError, FileNotFoundError): raise HTTPException(404, '运行不存在')

    @app.get('/api/trajectory-experiments/{key}/runs/{arm}/{run_id}/report', response_class=HTMLResponse)
    def trajectory_report(key: str, arm: str, run_id: str):
        try:
            run=trajectory_experiment.run(key, arm, run_id)
            return HTMLResponse(render_report(run, trajectory_experiment.task(key, run)), headers={'Content-Disposition': 'attachment; filename="trajectory-report.html"'})
        except (KeyError, FileNotFoundError, ValueError): raise HTTPException(404, '报告不存在')

    @app.get('/api/workpack-experiments/protocol')
    def workpack_experiment_protocol(mode: Literal['smoke_v4', 'precheck_v4', 'full_train_v2', 'smoke_v5', 'precheck_v5', 'full_train_v3',
                                                   'smoke_v6', 'precheck_v6', 'full_train_v4', 'smoke_v7', 'precheck_v7', 'full_train_v5',
                                                   'smoke_v8', 'precheck_v8', 'full_train_v6', 'smoke_v9', 'precheck_v9', 'full_train_v7',
                                                   'smoke_v10', 'precheck_v10', 'full_train_v8', 'smoke_v11', 'precheck_v11', 'full_train_v9',
                                                   'smoke_v12', 'precheck_v12', 'full_train_v10', 'smoke_v13', 'precheck_v13', 'full_train_v11',
                                                   'smoke_v14', 'precheck_v14', 'full_train_v12', 'smoke_v15', 'precheck_v15', 'full_train_v13',
                                                   'smoke_v16', 'precheck_v16', 'full_train_v14', 'smoke_v17', 'precheck_v17', 'full_train_v15'] = 'smoke_v17'):
        return workpack_experiment.protocol(mode)

    @app.get('/api/workpack-experiments')
    def workpack_experiment_list():
        return workpack_experiment.list_summaries()

    @app.post('/api/workpack-experiments', status_code=202)
    async def workpack_experiment_start(request: WorkpackExperimentRequest):
        if not request.confirmCost:
            protocol = workpack_experiment.protocol(request.mode)
            raise HTTPException(400, f'工作包在线实验会发起 {protocol["agentRuns"]} 次真实 Agent 运行；请确认费用后再启动')
        if any([task_runner.tasks, paired.tasks, judge.tasks, workpack_judge.tasks, live_showcase.tasks, workspace_runner.tasks, workpack_experiment.tasks]):
            raise HTTPException(409, '已有模型任务或实验在运行；串行在线预检保持独占以保护计量')
        try:
            item = await workpack_experiment.start(request.mode)
        except ValueError as error:
            raise HTTPException(400, str(error))
        return workpack_experiment.dashboard(item['id'])

    @app.get('/api/workpack-experiments/{key}')
    def workpack_experiment_get(key: str):
        try:
            return workpack_experiment.dashboard(key)
        except KeyError:
            raise HTTPException(404, '工作包在线实验不存在')

    @app.get('/api/workpack-experiments/{key}/judgements')
    def workpack_judgements_list(key: str):
        try:
            protocol = workpack_judge.protocol(key)
        except KeyError:
            raise HTTPException(404, '工作包在线实验不存在')
        return {'items': workpack_judge.list(key), 'protocol': protocol, 'model': config.JUDGE_MODEL,
                'rubricHash': digest(JUDGE_PROMPT)}

    @app.post('/api/workpack-experiments/{key}/judgements', status_code=202)
    async def workpack_judgements_start(key: str, request: WorkpackJudgeRequest):
        try:
            protocol = workpack_judge.protocol(key)
        except KeyError:
            raise HTTPException(404, '工作包在线实验不存在')
        if not request.confirmCost:
            raise HTTPException(400, f'工作包 Judge 会发起约 {protocol["normalModelRequests"]} 次真实模型请求；请确认费用后再启动')
        if any([task_runner.tasks, paired.tasks, judge.tasks, live_showcase.tasks, workspace_runner.tasks, workpack_experiment.tasks, workpack_judge.tasks]):
            raise HTTPException(409, '已有 Agent、评测或 Judge 在运行；为保持成本账本隔离，请等待结束')
        try:
            item = await workpack_judge.start(key)
        except ValueError as error:
            raise HTTPException(400, str(error))
        return {'id': item['id'], 'status': item['status'], 'protocol': item['protocol']}

    @app.get('/api/workpack-experiments/{key}/runs/{arm}/{run_id}')
    def workpack_experiment_run(key: str, arm: Literal['baseline', 'rsi'], run_id: str):
        try:
            return workpack_experiment.run(key, arm, run_id)
        except KeyError:
            raise HTTPException(404, '工作包在线实验运行不存在')

    @app.get('/api/workpack-experiments/{key}/runs/{arm}/{run_id}/report', response_class=HTMLResponse)
    def workpack_experiment_report(key: str, arm: Literal['baseline', 'rsi'], run_id: str):
        try:
            run, task = workpack_experiment.run_with_task(key, arm, run_id)
        except KeyError:
            raise HTTPException(404, '工作包在线实验运行不存在')
        return HTMLResponse(render_report(run, task), headers={'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'"})

    @app.post('/api/workpack-experiments/{key}/cancel')
    def workpack_experiment_cancel(key: str):
        try:
            return {'cancelled': workpack_experiment.cancel(key)}
        except KeyError:
            raise HTTPException(404, '工作包在线实验不存在')

    @app.post('/api/workpacks/{pack_id}/workspace', status_code=201)
    def workpack_install(pack_id: str):
        workspace, task = install_workpack(workspace_manager, taskbank, pack_id)
        return {'workspace': workspace, 'task': task,
                'notice': '预定义工作包已通过与用户上传相同的文件解析和工作区工具入口载入；尚未运行模型。'}

    @app.post('/api/workspaces/{key}/files', status_code=201)
    async def workspace_upload(key: str, request: Request, name: str = Query(..., min_length=1, max_length=180)):
        workspace = workspace_manager.workspace(key)
        if len(workspace['sources']) >= 10:
            raise ValueError('上传后将超过每工作区 10 个文件限制')
        content = await request.body()
        result = workspace_manager.add_source(key, name, content)
        return {'file': result, 'workspace': workspace_manager.public_workspace(key)}

    @app.delete('/api/workspaces/{key}/files/{source_id}', status_code=204)
    def workspace_remove_source(key: str, source_id: str):
        workspace_manager.remove_source(key, source_id)
        return Response(status_code=204)

    @app.get('/api/workspaces/{key}/sources/{source_id}/download')
    def workspace_source_download(key: str, source_id: str):
        path = workspace_manager.source_path(key, source_id)
        return FileResponse(path, filename=workspace_manager.source_name(key, source_id))

    @app.post('/api/workspaces/{key}/tasks', status_code=201)
    def workspace_create_task(key: str, request: WorkspaceTaskRequest):
        task, clarifications = workspace_manager.create_task(key, request.request, title=request.title,
                                                              answers=request.answers, followup_run_id=request.followupRunId)
        if clarifications:
            return {'status': 'needs_clarification', 'clarifications': clarifications}
        return {'status': 'ready', 'task': task}

    @app.get('/api/workspaces/tasks/{task_id}')
    def workspace_task_get(task_id: str):
        return workspace_manager.public_task(task_id)

    @app.post('/api/workspaces/tasks/{task_id}/runs', status_code=202)
    async def workspace_run_start(task_id: str, request: WorkspaceRunRequest):
        task = workspace_manager.task(task_id)
        if not request.confirmCost:
            raise HTTPException(400, '工作区 Agent 会发起真实模型请求；请确认费用后再启动')
        if workspace_runner.tasks:
            raise HTTPException(409, '当前已有一个工作区 Agent 在运行；串行工作台请等待或取消')
        run = await workspace_runner.start(TaskRunRequest(taskId=task['id'], strategy=request.strategy))
        return {'id': run['id'], 'taskId': task_id, 'status': run['status']}

    @app.get('/api/workspaces/runs')
    def workspace_run_list(workspaceId: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
        rows = [run for run in workspace_runner.runs.values() if not workspaceId or workspace_manager.task(run['taskId']).get('workspaceId') == workspaceId]
        rows.sort(key=lambda run: run.get('createdAt', ''), reverse=True)
        return {'scheduler': workspace_runner.status(), 'runs': [{key: run.get(key) for key in ['id', 'taskId', 'status', 'strategy', 'phase', 'createdAt', 'metrics', 'evaluation', 'evolution']} for run in rows[:limit]]}

    @app.get('/api/workspaces/runs/{run_id}')
    def workspace_run_get(run_id: str):
        if run_id not in workspace_runner.runs:
            raise HTTPException(404, '工作区执行记录不存在')
        return deepcopy(workspace_runner.runs[run_id])

    @app.get('/api/workspaces/runs/{run_id}/report', response_class=HTMLResponse)
    def workspace_run_report(run_id: str):
        if run_id not in workspace_runner.runs:
            raise HTTPException(404, '工作区执行记录不存在')
        run = workspace_runner.runs[run_id]
        return HTMLResponse(render_report(run, workspace_manager.task(run['taskId'])), headers={'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'"})

    @app.get('/api/workspaces/runs/{run_id}/report/download')
    def workspace_run_report_download(run_id: str):
        if run_id not in workspace_runner.runs:
            raise HTTPException(404, '工作区执行记录不存在')
        run = workspace_runner.runs[run_id]
        body = render_report(run, workspace_manager.task(run['taskId']))
        return Response(body, media_type='text/html; charset=utf-8', headers={
            'Content-Disposition': f'attachment; filename="operations-report-{run_id}.html"',
            'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'",
        })

    @app.post('/api/workspaces/runs/{run_id}/cancel')
    async def workspace_run_cancel(run_id: str):
        if run_id not in workspace_runner.runs:
            raise HTTPException(404, '工作区执行记录不存在')
        job = workspace_runner.tasks.get(run_id)
        if job:
            job.cancel()
        return {'cancelled': bool(job)}

    @app.get('/api/workspaces/{key}/exports/{export_id}')
    def workspace_export_download(key: str, export_id: str):
        path = workspace_manager.export_path(key, export_id)
        return FileResponse(path, filename=path.name, media_type='text/csv; charset=utf-8')

    # Keep this broad workspace-detail route after reserved subpaths such as
    # ``/runs``.  Otherwise FastAPI treats "runs" as a workspace ID.
    @app.get('/api/workspaces/{key}')
    def workspace_get(key: str):
        return workspace_manager.public_workspace(key)

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
    def taskbank_tasks(scenario: Optional[Literal['finance', 'support', 'tickets']] = None, split: Optional[Literal['train', 'validation', 'test', 'showcase']] = None):
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
            is_file_upload = request.url.path.startswith('/api/workspaces/') and request.url.path.endswith('/files')
            # Installing a frozen example is a body-less command.  It only
            # materializes source files through the same workspace parser; a
            # JSON media type is neither supplied nor meaningful here.
            is_workpack_install = bool(re.fullmatch(r'/api/workpacks/[^/]+/workspace', request.url.path))
            if request.method not in ['GET', 'HEAD'] and not is_file_upload and not is_workpack_install:
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
