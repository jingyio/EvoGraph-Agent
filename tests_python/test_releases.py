"""Release isolation uses small injected saved receipts, never a model call."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pytest
from backend.releases import ReleaseEvidence, selection_csv
from backend.config import ROOT
from backend.trajectory_assets_v3_r2 import build as build_v3_r2
from backend.trajectory_assets_v3_r3 import build as build_v3_r3
from backend.graph_store import write_private
from backend.workspace import WorkspaceManager
from backend.trajectory_assets import request_for, task_plan


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


def test_pending_candidate_exposes_zero_evidence_and_validates_asset_counts(tmp_path):
    root=tmp_path;asset=root/'artifacts/trajectory-review-v2/manifest.json'
    tasks=[]
    for task in task_plan():
        request=request_for(task['scenario'],task['group'],task['position'])
        tasks.append(dict(task,requestHash=hashlib.sha256(request.encode()).hexdigest()))
    write_private(asset,{'version':'trajectory-review-v2','tasks':tasks,'sources':{}})
    release={'releaseId':'pending','displayName':'Pending','status':'candidate','source':'trajectory-plan',
             'experimentId':'not-started','runtimeRevision':'pending','assetVersion':'trajectory-review-v2',
             'assetManifest':'artifacts/trajectory-review-v2/manifest.json','createdAt':'2026','claims':[],'limitations':[],
             'protocol':{'assetCounts':{'train':48,'validation':6,'test':6}}}
    write_private(root/'releases/manifest.json',{'currentReleaseId':'pending','releases':[release]})
    result=ReleaseEvidence(root).evidence('pending')
    assert result['experimentStatus']=='not_started' and result['plannedPairs']==48 and result['pairs']==[]
    assert result['summary']['netTokenSaving'] is None and not result['summary']['qualityGate']
    assert len(result['taskReview'])==6 and len(result['taskReview'][0]['variants'])==8
    changed=deepcopy(tasks);changed[0]['requestHash']='tampered'
    write_private(asset,{'version':'trajectory-review-v2','tasks':changed,'sources':{}})
    with pytest.raises(ValueError,match='题面'):ReleaseEvidence(root).evidence('pending')
    tasks.pop();write_private(asset,{'version':'trajectory-review-v2','tasks':tasks,'sources':{}})
    with pytest.raises(ValueError,match='不一致'):ReleaseEvidence(root).evidence('pending')


def test_v3_r2_frozen_asset_has_six_business_cohorts_without_delivery_contract_in_requests():
    build_v3_r2(ROOT)
    asset = json.loads((ROOT / 'benchmarks/trajectory-review-v3-r2.json').read_text())
    train = [row for row in asset['tasks'] if row['split'] == 'train']
    cohorts = {row['cohort'] for row in train}
    assert len(train) == 48 and len(cohorts) == 6
    assert cohorts == {
        'finance-reconciliation', 'finance-payment-health',
        'support-service-timing', 'support-response-coverage',
        'tickets-activity-triage', 'tickets-delivery-readiness',
    }
    for row in train:
        request = (ROOT / 'artifacts/trajectory-review-v3-r2' / row['id'] / 'request.txt').read_text()
        assert hashlib.sha256(request.encode()).hexdigest() == row['requestHash']
        assert 'selectedIds' not in request and 'evidenceIds' not in request and 'metrics' not in request


def test_historical_unrun_v3_r3_candidate_keeps_its_asset_context():
    build_v3_r3(ROOT)
    store = ReleaseEvidence(ROOT)
    result = store.evidence('trajectory-p05-v3-r3-candidate')
    assert result['release']['releaseId'] == 'trajectory-p05-v3-r3-candidate'
    assert result['release']['assetVersion'] == 'trajectory-review-v3-r3'
    assert result['experimentStatus'] == 'not_started'
    assert result['plannedPairs'] == 48 and result['pairs'] == []
    assert result['summary']['netTokenSaving'] is None
    assert len(result['taskReview']) == 6


def test_attribution_release_maps_public_arms_and_keeps_g0_out_of_revisions(tmp_path):
    root = tmp_path
    key = 'attr-candidate'
    experiment_id = 'attr-exp'
    directory = root / 'artifacts/attribution-experiments' / experiment_id
    manager = WorkspaceManager(directory)
    workspace = manager.create('finance')
    manager.add_source(workspace['id'], 'input.json', b'{"orders":[{"order_id":"o1"}]}')
    task, questions = manager.create_task(workspace['id'], '复核当前附件', split='train')
    assert not questions
    protocol = {'id': 'attribution-test', 'taskCountPerArm': 1}
    fingerprint = {'digest': 'frozen'}
    def run(run_id):
        return {'id': run_id, 'taskId': task['id'], 'status': 'completed',
                'evaluation': {'status': 'passed'},
                'metrics': {'inputTokens': 10, 'outputTokens': 5, 'usageComplete': True,
                            'durationMs': 20, 'modelRequests': 1, 'toolCalls': 1, 'toolErrors': 0}}
    no_learning, online = run('a'), run('b')
    online['evolution'] = {'generatedVersionIds': ['g0'], 'generatedMatchVersions': [{'graphId': 'g0', 'version': 0}]}
    write_private(directory / 'no_learning/runs/a.json', no_learning)
    write_private(directory / 'online_rsi/runs/b.json', online)
    item = {'id': experiment_id, 'assetVersion': 'asset', 'fingerprint': fingerprint,
            'protocol': protocol, 'status': 'completed', 'manifest': [{'id': 'FA01'}],
            'pairs': [{'status': 'completed', 'taskId': task['id'],
                       'spec': {'id': 'FA01', 'title': 'one', 'scenario': 'finance', 'position': 1,
                                'opportunity': 'create', 'sourceTaskId': 'F01'},
                       'no_learning': no_learning, 'online_rsi': online,
                       'experienceAfter': {'onlineRsiVersions': [{'id': 'g0', 'generation': 0,
                           'matchVersion': 0, 'parentGraphId': None, 'sourceRunId': 'b',
                           'patches': [{'before': [], 'after': [1]}],
                           'matchPatches': [{'before': None, 'after': {'purpose': 'x'}}]}]}}]}
    path = directory / 'experiment.json'
    write_private(path, item)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    release = {'releaseId': key, 'displayName': 'Attribution', 'status': 'candidate',
               'source': 'attribution', 'experimentId': experiment_id,
               'runtimeRevision': 'sha256:frozen', 'artifactDigest': 'sha256:' + digest,
               'assetVersion': 'asset', 'protocol': protocol, 'claims': [], 'limitations': [], 'createdAt': '2026'}
    write_private(root / 'releases/manifest.json', {'currentReleaseId': key, 'releases': [release]})
    store = ReleaseEvidence(root)
    evidence = store.evidence(key)
    assert evidence['pairs'][0]['runs']['baseline']['id'] == 'a'
    assert evidence['pairs'][0]['runs']['rsi']['id'] == 'b'
    assert evidence['revisions'] == []
    assert store.run(key, 'FA01', 'baseline')['storedArm'] == 'no_learning'


def test_current_release_and_default_analysis_share_one_experiment_context():
    release = ReleaseEvidence(ROOT).manifest()
    registry = json.loads((ROOT / 'releases/analysis-manifest.json').read_text())
    dataset = next(row for row in registry['datasets'] if row['datasetId'] == registry['defaultDatasetId'])
    assert dataset['releaseId'] == release['releaseId']
    for name in ('experimentId', 'runtimeRevision', 'assetVersion', 'artifactDigest', 'status'):
        assert dataset[name] == release[name]
    assert dataset['protocol']['id'] == release['protocol']['id']


def test_repository_current_candidate_exposes_real_api_quality_limit_and_revision_use_chains():
    store = ReleaseEvidence(ROOT)
    release = store.manifest()
    assert release['releaseId'] == 'finance-attribution-v5-12-api-candidate'
    assert release['status'] == 'candidate'
    assert release['experimentId'] == 'd02f0ecd-8bb5-4359-94be-e7f7233df6a5'
    assert release['runtimeRevision'] == 'sha256:11e6f73013a0ad50c4023b637214660087c001cff55a676c354e7aba299d68f4'
    evidence = store.evidence(release['releaseId'])
    assert evidence['experimentStatus'] == 'completed'
    assert evidence['summary']['qualityGate'] is False
    assert evidence['summary']['costConclusionAllowed'] is False
    assert evidence['summary']['arms']['no_learning']['passed'] == 11
    assert evidence['summary']['arms']['online_rsi']['passed'] == 12
    assert evidence['summary']['arms']['no_learning']['tokens'] == 2119742
    assert evidence['summary']['arms']['online_rsi']['tokens'] == 936718
    assert evidence['summary']['actualGraphUse']['hits'] == 11
    assert evidence['summary']['actualGraphUse']['attempts'] == 12
    chains = {row['sourcePairId']: {use['pairId'] for use in row['subsequentUses']}
              for row in evidence['revisions']}
    assert 'FX10' in chains['FX09']
    assert chains['FX11'] == {'FX12'}
    fx11 = next(pair for pair in evidence['pairs'] if pair['pairId'] == 'FX11')
    assert fx11['runs']['baseline']['evaluation']['status'] == 'failed'
    assert fx11['runs']['rsi']['evaluation']['status'] == 'passed'
    assert store.report(release['releaseId'], 'FX12', 'rsi')


def test_repository_current_release_api_returns_only_the_pinned_candidate():
    from fastapi.testclient import TestClient
    import backend.app as module

    client = TestClient(module.create_app())
    release = client.get('/api/releases/current')
    assert release.status_code == 200
    assert release.json()['releaseId'] == 'finance-attribution-v5-12-api-candidate'
    evidence = client.get('/api/releases/finance-attribution-v5-12-api-candidate/evidence')
    assert evidence.status_code == 200
    payload = evidence.json()
    assert payload['summary']['qualityGate'] is False
    assert payload['summary']['costConclusionAllowed'] is False
    assert len(payload['pairs']) == 12
    assert client.get('/api/releases/finance-attribution-v5-12-api-candidate/pairs/FX12/runs/rsi/report').status_code == 200
