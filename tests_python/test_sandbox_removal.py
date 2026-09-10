import httpx
from backend.app import create_app
from backend.service import RunService
from backend.runtime import create_run
from backend.tools import Tool, object_schema
from test_runtime_api import Scripted, response, call
import pytest


async def test_removed_routes_rejected_and_platform_runtime_still_works(tmp_path, monkeypatch):
    tools = [Tool('read_record', 'read', 'read', object_schema(), lambda a,c: {'id': 'fresh'})]
    monkeypatch.setattr('backend.service.tools_for', lambda request: tools)
    service = RunService(tmp_path, provider_factory=lambda: Scripted([response([call('read_record')]), response()]))
    app = create_app(service)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            for path in ['/api/snapshot','/api/evolutions','/api/reliability','/api/negative-motifs']:
                assert (await client.get(path)).status_code == 404
            assert (await client.post('/api/runs',json={'source':'sandbox','scenario':'finance','mode':'fixture','task':'retired'})).status_code == 400
            assert (await client.post('/api/platforms/check',json={},headers={'Origin':'https://untrusted.example'})).status_code == 403
            assert (await client.post('/api/platforms/check',content='plain')).status_code == 415
            posted = await client.post('/api/runs',json={'source':'erpnext','scenario':'finance','mode':'live','task':'read'})
            assert posted.status_code == 202
            key = posted.json()['id']
            if key in service.tasks: await service.tasks[key]
            run = (await client.get('/api/runs/'+key)).json()
            assert run['status'] == 'completed' and run['metrics']['toolCalls'] == 1
            assert run['evaluation']['status'] == 'not_evaluated'
            assert set(run['initial']) == {'asOf'}
            assert (await client.get('/api/runs/'+key+'/export/md')).status_code == 200
    restored = RunService(tmp_path);restored.restore();assert key in restored.runs
    with pytest.raises(ValueError):create_run({'source':'sandbox','mode':'live'})
