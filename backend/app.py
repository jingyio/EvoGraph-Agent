from contextlib import asynccontextmanager
from typing import Literal, Optional
import json
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse, Response
from pydantic import ValidationError
from . import config
from .domain import seed, markdown
from .models import RunRequest
from .service import RunService, tools_for
from .platform_check import check_platforms
from .evolution import EvolutionService, EvolutionRequest


def create_app(service=None):
    service = service or RunService()
    evolution = EvolutionService(service)
    @asynccontextmanager
    async def lifespan(app):
        service.restore()
        evolution.restore()
        try:
            yield
        finally:
            await evolution.shutdown()
            await service.shutdown()
    app = FastAPI(title='RSI Agent Lab', version='0.3.0', lifespan=lifespan)
    app.state.service = service
    app.state.evolution = evolution

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
        return await evolution.start(request)

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
