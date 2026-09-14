"""Release isolation uses small injected saved receipts, never a model call."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from backend.releases import ReleaseEvidence, selection_csv
from backend.graph_store import write_private
from backend.workspace import WorkspaceManager


def fixture(root):
    key='current-candidate';directory=root/'artifacts/trajectory-experiments'/'chosen'
    manager=WorkspaceManager(directory);w=manager.create('finance')
    manager.add_source(w['id'],'orders.json',b'[{"order_id":"o1"}]')
    task,_=manager.create_task(w['id'],'Review current attachment',split='train')
    m={'inputTokens':10,'outputTokens':2,'toolCalls':1,'modelRequests':1,'toolErrors':0,'durationMs':20,'usageComplete':True}
    run={'id':'run-a','taskId':task['id'],'status':'completed','evaluation':{'status':'passed'},'metrics':m,'events':[],
         'submission':{'metrics':{'count':1},'summary':'test report','selectedIds':['o1'],'groups':[]}}
    pair={'spec':{'id':'pair-1','group':'group','title':'Review','scenario':'finance','position':1,'features':{}},'taskId':task['id'],'status':'completed','baseline':run,'rsi':dict(run,id='run-b')}
    protocol={'limits':{'run':1,'model':1,'read':1}}
    item={'id':'chosen','assetVersion':'asset','fingerprint':{'digest':'frozen'},'protocol':protocol,'createdAt':'2026','status':'completed','manifest':[{}],'pairs':[pair]}
    write_private(directory/'experiment.json',item)
    for arm in ['baseline','rsi']:write_private(directory/arm/'runs'/(pair[arm]['id']+'.json'),pair[arm])
    release={'releaseId':key,'displayName':'Candidate','status':'candidate','source':'trajectory','experimentId':'chosen','runtimeRevision':'sha256:frozen','assetVersion':'asset','protocol':protocol,'claims':[],'limitations':[],'createdAt':'2026'}
    write_private(root/'releases/manifest.json',{'currentReleaseId':key,'releases':[release]})
    # Deliberately newer/large alien data cannot change selection or numbers.
    write_private(root/'artifacts/trajectory-experiments/newest/experiment.json',dict(item,id='newest',createdAt='2999',summary={'tokens':999999}))
    return ReleaseEvidence(root),directory,item,key


def test_release_isolation_and_readonly_report_input_drilldown(tmp_path):
    store,directory,item,key=fixture(tmp_path)
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    assert store.manifest()['experimentId']=='chosen'
    result=store.evidence(key)
    assert result['summary']['arms']['rsi']['tokens']==12
    assert not result['evolutionEvidence']['graph'] and not result['revisions']
    pair=store.pair(key,'pair-1')
    assert 'privateValidation' not in json.dumps(pair)
    assert pair['runs']['rsi']['id']=='run-b'
    path,name=store.input_file(key,'pair-1',pair['inputs'][0]['id'])
    assert name=='orders.json' and path.read_bytes()==b'[{"order_id":"o1"}]'
    assert 'test report' in store.report(key,'pair-1','rsi')
    assert before=={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(KeyError):store.pair(key,'other-pair')
    with pytest.raises(KeyError):store.run(key,'pair-1','other-arm')
    with pytest.raises(KeyError):store.evidence('newest')


def test_release_does_not_fallback_when_source_missing_or_runtime_asset_protocol_mismatch(tmp_path):
    store,directory,item,key=fixture(tmp_path)
    for patch in [{'assetVersion':'wrong'},{'fingerprint':{'digest':'wrong'}},{'protocol':{}},{'id':'wrong'}]:
        write_private(directory/'experiment.json',dict(item,**patch))
        with pytest.raises(ValueError,match='不一致'):store.evidence(key)
    (directory/'experiment.json').unlink()
    with pytest.raises(FileNotFoundError):store.evidence(key)


def test_revision_requires_changed_structure_and_real_later_use(tmp_path):
    store,directory,item,key=fixture(tmp_path)
    run=item['pairs'][0]['rsi'];run['evolution']={'generatedVersionIds':['g1'],'trajectoryCompilation':{'patches':[{'before':[1],'after':[2]}],'matchPatches':[{'before':{'scope':1},'after':{'scope':2}}]}}
    write_private(directory/'rsi/runs/run-b.json',run)
    result=store.evidence(key)
    assert len(result['revisions'])==1 and not result['evolutionEvidence']['graph']
    second=deepcopy(item['pairs'][0]);second['spec']['id']='pair-2';second['rsi']=dict(run,id='run-c',evolution={'usedVersionId':'g1','matchVersion':1},toolTrace=[{'executor':'graph','ok':True}])
    item['pairs'].append(second);item['manifest'].append({});write_private(directory/'experiment.json',item);write_private(directory/'rsi/runs/run-c.json',second['rsi'])
    result=store.evidence(key)
    assert result['evolutionEvidence']=={'graph':True,'matching':True}
    assert result['revisions'][0]['subsequentUses'][0]['pairId']=='pair-2'


def test_selection_download_escapes_spreadsheet_formula_and_keeps_empty_groups():
    value=selection_csv({'groups':[{'name':'=malicious','condition':'test','selectedIds':['+123'],'count':1,'evidenceIds':[]},{'name':'empty','count':0,'selectedIds':[]}]})
    assert "'=malicious" in value and "'+123" in value and 'empty,,,0,' in value


def test_release_api_membership_and_downloads(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    import backend.app as module
    store,_,_,key=fixture(tmp_path)
    monkeypatch.setattr(module,'ReleaseEvidence',lambda root:store)
    client=TestClient(module.create_app())
    release=client.get('/api/releases/current');assert release.status_code==200 and release.json()['status']=='candidate'
    assert client.get(f'/api/releases/{key}/evidence').json()['release']['experimentId']=='chosen'
    detail=client.get(f'/api/releases/{key}/pairs/pair-1').json()
    assert client.get(detail['inputs'][0]['download']).status_code==200
    report=client.get(f'/api/releases/{key}/pairs/pair-1/runs/rsi/report')
    assert report.status_code==200 and 'attachment' in report.headers['content-disposition']
    assert client.get(f'/api/releases/{key}/pairs/pair-1/runs/rsi/selection').status_code==200
    assert client.get(f'/api/releases/{key}/pairs/alien/runs/rsi').status_code==404


def test_archive_context_is_explicit_and_has_no_cross_experiment_total(tmp_path):
    store,directory,item,key=fixture(tmp_path)
    path=tmp_path/'releases/manifest.json';registry=json.loads(path.read_text())
    historic=dict(registry['releases'][0],releaseId='v4-history',source='online-e2e',status='historical',experimentId='old-v4',runtimeRevision='git:recorded')
    registry['releases'].append(historic);registry['legacyRoutes']={'replay':'v4-history','trajectory':key};write_private(path,registry)
    result=store.archive()
    assert 'summary' not in result and 'metrics' not in result
    assert result['legacyRoutes']['trajectory']['experimentId']=='chosen'
    assert result['legacyRelease']['status']=='historical'
    row=next(x for x in result['items'] if x['experimentId']=='chosen')
    assert row['runtimeRevision']=='sha256:frozen' and row['assetVersion']=='asset'


def test_tampered_run_membership_cannot_show_another_tasks_report(tmp_path):
    store,directory,item,key=fixture(tmp_path)
    path=directory/'rsi/runs/run-b.json';run=json.loads(path.read_text());run['taskId']='other-experiment-task';write_private(path,run)
    with pytest.raises(ValueError,match='身份'):store.evidence(key)
    with pytest.raises(ValueError,match='身份'):store.report(key,'pair-1','rsi')
