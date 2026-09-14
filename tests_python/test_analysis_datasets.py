"""Analysis datasets are pinned read-only projections of one saved experiment."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from backend.analysis_datasets import AnalysisDatasets
from backend.graph_store import write_private


MODEL_PRICING = {
    'currency': 'USD',
    'source': {
        'name': 'OpenRouter 标准价格快照',
        'url': 'https://openrouter.ai/models/qwen/qwen3.5-27b/api',
        'retrievedAt': '2026-09-14',
    },
    'models': {
        'qwen/qwen3.5-27b': {'inputPerMillionUsd': .195, 'outputPerMillionUsd': 1.56},
        'qwen/qwen3.5-9b': {'inputPerMillionUsd': .08, 'outputPerMillionUsd': .13},
    },
}


def fixture(root: Path):
    experiment_id = 'chosen-v17'
    metrics_a = {'inputTokens': 80, 'outputTokens': 20, 'usageComplete': True, 'durationMs': 1000,
                 'modelRequests': 2, 'toolCalls': 3}
    metrics_b = {'inputTokens': 40, 'outputTokens': 10, 'usageComplete': True, 'durationMs': 600,
                 'modelRequests': 1, 'toolCalls': 2}
    pairs = []
    for index in (1, 2):
        pairs.append({
            'index': index, 'workpackId': f'finance-review-{index:02d}', 'scenario': 'finance',
            'workflowType': 'finance-review', 'round': index, 'recordCount': 10, 'difficulty': 'A',
            'status': 'completed', 'runs': {
                'baseline': {'id': f'baseline-{index}', 'status': 'completed', 'metrics': deepcopy(metrics_a),
                             'models': {'planner': 'qwen/qwen3.5-27b', 'composition': 'qwen/qwen3.5-27b', 'executor': 'qwen/qwen3.5-27b'},
                             'evaluation': {'status': 'passed'}},
                'rsi': {'id': f'rsi-{index}', 'status': 'completed', 'metrics': deepcopy(metrics_b),
                        'models': {'planner': 'qwen/qwen3.5-27b', 'composition': 'qwen/qwen3.5-27b', 'executor': 'qwen/qwen3.5-27b'},
                        'evaluation': {'status': 'passed'},
                        'evolution': {'planningPath': 'fallback' if index == 1 else 'fast',
                                      'generatedVersionIds': ['g0'] if index == 1 else [],
                                      'usedVersionId': None if index == 1 else 'g0'}},
            },
        })
    experiment = {
        'id': experiment_id, 'mode': 'full', 'status': 'completed',
        'protocol': {'id': 'strict', 'taskCountPerArm': 2,
                     'runtimeFingerprint': {'executionDigest': 'runtime'}},
        'pairs': pairs,
        'summary': {
            'pairedCompleted': 2,
            'baseline': {'passed': 2, 'attempts': 2, 'totalTokens': 200, 'durationMs': 2000,
                         'modelRequests': 4, 'toolCalls': 6, 'usageIncomplete': 0},
            'rsi': {'passed': 2, 'attempts': 2, 'totalTokens': 100, 'durationMs': 1200,
                    'modelRequests': 2, 'toolCalls': 4, 'usageIncomplete': 0},
            'learning': {'workflowCreated': 1, 'fastReuse': 1, 'composition': 0, 'fallback': 1},
            'qualityGate': {'status': 'passed', 'sameQualityCostClaim': True},
            'reliability': {'allUsageComplete': True},
        },
    }
    experiment_path = root / 'artifacts/workpack-experiments' / experiment_id / 'experiment.json'
    write_private(experiment_path, experiment)
    digest = 'sha256:' + hashlib.sha256(experiment_path.read_bytes()).hexdigest()
    manifest = {
        'datasetId': 'v17', 'displayName': 'V17', 'status': 'formal', 'experimentId': experiment_id,
        'runtimeRevision': 'sha256:runtime', 'assetVersion': 'asset', 'artifactDigest': digest,
        'protocol': {'id': 'strict', 'mode': 'full', 'experimentStatus': 'completed',
                     'qualityGateStatus': 'passed', 'taskCountPerArm': 2, 'limits': {'run': 1, 'model': 1, 'read': 1}},
        'createdAt': '2026-09-13', 'claims': [], 'limitations': [],
    }
    write_private(root / 'releases/analysis-manifest.json',
                  {'schemaVersion': 1, 'defaultDatasetId': 'v17', 'modelPricing': MODEL_PRICING, 'datasets': [manifest]})
    return AnalysisDatasets(root), experiment_path, experiment


def test_analysis_dataset_is_pinned_and_derives_token_and_serial_latency_curves(tmp_path):
    store, _, _ = fixture(tmp_path)
    listing = store.list()
    assert listing['defaultDatasetId'] == 'v17' and len(listing['items']) == 1
    result = store.get('v17')
    assert result['summary']['tokenSaving'] == .5
    assert result['summary']['latencySaving'] == .4
    assert result['summary']['baseline']['costUsd'] == .0000936
    assert result['summary']['rsi']['costUsd'] == .0000468
    assert result['summary']['costSaving'] == .5
    assert result['points'][0]['baseline']['costUsd'] == .0000468
    assert len(result['points']) == 2
    assert result['points'][-1]['cumulativeBaselineTokens'] == 200
    assert result['points'][-1]['cumulativeRsiLatencyMs'] == 1200
    assert result['points'][-1]['planningPath'] == 'fast'
    assert result['points'][-1]['baseline']['reportUrl'].endswith('/baseline/baseline-2/report')


def test_analysis_dataset_fails_closed_on_artifact_runtime_protocol_or_quality_mismatch(tmp_path):
    store, experiment_path, experiment = fixture(tmp_path)
    for patch in [
        {'id': 'alien'},
        {'mode': 'other'},
        {'protocol': {**experiment['protocol'], 'runtimeFingerprint': {'executionDigest': 'other'}}},
        {'summary': {**experiment['summary'], 'qualityGate': {'status': 'failed'}}},
    ]:
        changed = {**experiment, **patch}
        write_private(experiment_path, changed)
        with pytest.raises(ValueError):
            store.get('v17')
        write_private(experiment_path, experiment)
    # A newer unrelated artifact is never selected implicitly.
    write_private(tmp_path / 'artifacts/workpack-experiments/newer/experiment.json',
                  {**experiment, 'id': 'newer', 'summary': {'baseline': {'totalTokens': 999999}}})
    assert store.get('v17')['dataset']['experimentId'] == 'chosen-v17'


def test_analysis_dataset_keeps_unknown_usage_unknown(tmp_path):
    store, experiment_path, experiment = fixture(tmp_path)
    registry_path = tmp_path / 'releases/analysis-manifest.json'
    experiment['pairs'][1]['runs']['rsi']['metrics']['usageComplete'] = False
    write_private(experiment_path, experiment)
    registry = json.loads(registry_path.read_text())
    registry['datasets'][0]['artifactDigest'] = 'sha256:' + hashlib.sha256(experiment_path.read_bytes()).hexdigest()
    write_private(registry_path, registry)
    result = store.get('v17')
    assert result['points'][1]['rsi']['tokens'] is None
    assert result['points'][1]['cumulativeRsiTokens'] is None
    assert result['points'][1]['cumulativeTokenSaving'] is None


def test_analysis_dataset_api_returns_only_named_dataset(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import backend.app as module

    store, _, _ = fixture(tmp_path)
    monkeypatch.setattr(module, 'AnalysisDatasets', lambda root: store)
    client = TestClient(module.create_app())
    assert client.get('/api/analysis/datasets').json()['defaultDatasetId'] == 'v17'
    assert client.get('/api/analysis/datasets/v17').json()['summary']['taskCount'] == 2
    assert client.get('/api/analysis/datasets/newest').status_code == 404


def test_repository_manifest_exposes_v4_36_as_an_isolated_online_e2e_dataset():
    root = Path(__file__).resolve().parents[1]
    store = AnalysisDatasets(root)
    listing = store.list()
    dataset_ids = [row['datasetId'] for row in listing['items']]
    assert listing['defaultDatasetId'] in dataset_ids
    expected_ids = {
        'finance-attribution-v5-repair-probe', 'finance-attribution-v4-6',
        'finance-attribution-v5-12-expanded', 'finance-attribution-2026-09-14',
        'workpack-v17-48', 'taskbank-v4-36',
    }
    assert expected_ids.issubset(dataset_ids)
    items_by_id = {row['datasetId']: row for row in listing['items']}
    assert items_by_id['finance-attribution-v5-repair-probe']['status'] == 'candidate'
    assert items_by_id['finance-attribution-v5-12-expanded']['status'] == 'historical'
    current = store.get('finance-attribution-v4-6')
    assert current['summary']['actualGraphUse']['hits'] == 4
    assert current['summary']['actualGraphUse']['attempts'] == 6
    expanded = store.get('finance-attribution-v5-12-expanded')
    assert expanded['dataset']['status'] == 'historical'
    assert expanded['experimentStatus'] == 'completed'
    assert expanded['summary']['taskCount'] == expanded['summary']['pairedCompleted'] == 12
    assert expanded['summary']['baseline']['passed'] == expanded['summary']['rsi']['passed'] == 8
    assert expanded['summary']['baseline']['tokens'] == 1467397
    assert expanded['summary']['rsi']['tokens'] == 1401822
    assert expanded['summary']['costConclusionAllowed'] is False
    assert expanded['summary']['actualGraphUse']['hits'] == 11
    assert expanded['summary']['actualGraphUse']['rate'] == pytest.approx(11 / 12)
    assert expanded['summary']['learning']['graphRevisions'] == 0
    assert expanded['summary']['learning']['matchingRevisions'] == 0
    assert len(expanded['points']) == 12
    assert expanded['points'][8]['baseline']['passed'] is False
    assert expanded['points'][8]['rsi']['passed'] is False
    assert expanded['points'][0]['detailUrl'] == '/api/releases/finance-attribution-v5-12-expanded/pairs/FX01'
    result = store.get('taskbank-v4-36')
    assert result['dataset']['status'] == 'historical'
    assert result['dataset']['source'] == {'kind': 'online-e2e'}
    assert result['summary']['taskCount'] == result['summary']['pairedCompleted'] == 36
    assert result['summary']['baseline']['passed'] == result['summary']['rsi']['passed'] == 36
    assert result['summary']['baseline']['tokens'] == 539468
    assert result['summary']['rsi']['tokens'] == 347368
    assert result['summary']['tokenSaving'] == .356092
    assert result['summary']['latencySaving'] == .418724
    assert result['summary']['learning'] == {
        'workflowCreated': 6, 'fastReuse': 24, 'composition': 0, 'fallback': 12,
    }
    assert result['points'][0]['index'] == 1 and result['points'][0]['sourceIndex'] == 0
    assert result['points'][-1]['index'] == 36 and result['points'][-1]['sourceIndex'] == 35
    assert result['points'][0]['workpackId'] == 'finance-cancelled_payments-01'
    assert result['points'][0]['workflowType'] == 'cancelled_payments'
    assert result['points'][0]['baseline']['reportUrl'].startswith(
        '/api/online-e2e/online-rsi-serial-final-v4/runs/baseline/'
    )
    assert result['points'][-1]['cumulativeBaselineTokens'] == 539468
    assert result['points'][-1]['cumulativeRsiTokens'] == 347368


def test_analysis_dataset_rejects_unregistered_source_paths(tmp_path):
    store, _, _ = fixture(tmp_path)
    registry_path = tmp_path / 'releases/analysis-manifest.json'
    registry = json.loads(registry_path.read_text())
    registry['datasets'][0]['source'] = {'kind': 'workpack', 'path': '../../outside.json'}
    write_private(registry_path, registry)
    with pytest.raises(ValueError, match='来源不受支持'):
        store.get('v17')


def attribution_fixture(root: Path):
    repository = Path(__file__).resolve().parents[1]
    registry = json.loads((repository / 'releases/analysis-manifest.json').read_text())
    manifest = deepcopy(next(row for row in registry['datasets'] if row['datasetId'] == 'finance-attribution-2026-09-14'))
    source = repository / 'artifacts/attribution-experiments' / manifest['experimentId'] / 'experiment.json'
    target = root / 'artifacts/attribution-experiments' / manifest['experimentId'] / 'experiment.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    write_private(root / 'releases/analysis-manifest.json', {
        'schemaVersion': 1,
        'defaultDatasetId': manifest['datasetId'],
        'modelPricing': MODEL_PRICING,
        'datasets': [manifest],
    })
    return AnalysisDatasets(root), target, json.loads(target.read_text()), manifest


def test_attribution_projection_keeps_incomplete_usage_and_creation_boundaries(tmp_path):
    store, _, _, manifest = attribution_fixture(tmp_path)
    result = store.get(manifest['datasetId'])
    assert result['experimentStatus'] == 'infrastructure_stopped'
    assert result['summary']['taskCount'] == 6
    assert result['summary']['pairedCompleted'] == 3
    assert result['summary']['baseline']['passed'] == 3
    assert result['summary']['baseline']['tokens'] == 238253
    assert result['summary']['rsi']['passed'] == 2
    assert result['summary']['rsi']['tokens'] is None
    assert result['summary']['rsi']['usageIncomplete'] == 1
    assert result['summary']['tokenSaving'] is None
    assert result['summary']['latencySaving'] is None
    assert result['summary']['costConclusionAllowed'] is False
    assert result['summary']['learning']['workflowCreated'] == 2
    assert result['summary']['learning']['matchingCreated'] == 2
    assert result['summary']['learning']['graphRevisions'] == 0
    assert result['summary']['learning']['subsequentUses'] == 0
    assert result['revisions'] == []
    assert len(result['points']) == 3
    assert len(result['taskPlan']) == 6
    assert [row['status'] for row in result['taskPlan']] == ['recorded'] * 3 + ['pending'] * 3
    assert result['points'][2]['baseline']['tokens'] == 168889
    assert result['points'][2]['rsi']['tokens'] is None
    assert result['points'][2]['cumulativeBaselineTokens'] == 238253
    assert result['points'][2]['cumulativeRsiTokens'] is None
    assert result['points'][2]['cumulativeTokenSaving'] is None
    assert result['points'][0]['rsi']['generatedMatchVersions'] == [0]
    assert result['points'][0]['baseline']['reportUrl'].endswith(
        '/runs/no_learning/8faab78f-7e0f-4855-8689-e47f6b6d0cf5/report'
    )
    assert result['points'][0]['rsi']['traceUrl'].endswith(
        '/runs/online_rsi/9d286f5f-78d6-476e-a2d6-e838eb512765'
    )


def test_attribution_dataset_fails_closed_on_digest_runtime_asset_protocol_and_status(tmp_path):
    store, path, original, manifest = attribution_fixture(tmp_path)
    registry_path = tmp_path / 'releases/analysis-manifest.json'

    path.write_text(path.read_text() + '\n')
    with pytest.raises(ValueError, match='摘要不一致'):
        store.get(manifest['datasetId'])
    write_private(path, original)

    patches = [
        {'status': 'completed'},
        {'assetVersion': 'other-asset'},
        {'fingerprint': {**original['fingerprint'], 'digest': 'other-runtime'}},
        {'protocol': {**original['protocol'], 'model': 'other-model'}},
        {'protocol': {**original['protocol'], 'taskOrder': list(reversed(original['protocol']['taskOrder']))}},
    ]
    for patch in patches:
        changed = {**original, **patch}
        write_private(path, changed)
        registry = json.loads(registry_path.read_text())
        registry['datasets'][0]['artifactDigest'] = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
        write_private(registry_path, registry)
        with pytest.raises(ValueError, match='测试组与保存实验不一致'):
            store.get(manifest['datasetId'])
    write_private(path, original)


def test_attribution_revision_projection_separates_m_only_revision_and_requires_execution():
    g0 = {
        'id': 'g0', 'generation': 0, 'matchVersion': 1, 'parentGraphId': None,
        'sourceRunId': 'create-run',
        'patches': [{'before': [], 'after': ['read']}],
        'matchPatches': [
            {'sourceRunId': 'create-run', 'before': None, 'after': {'purpose': 'finance'}},
            {'sourceRunId': 'revise-run', 'before': {'threshold': 8}, 'after': {'threshold': 10}},
        ],
    }
    item = {'pairs': [
        {'spec': {'id': 'FA01'}, 'online_rsi': {'id': 'create-run'}},
        {'spec': {'id': 'FA02'}, 'online_rsi': {'id': 'revise-run'},
         'experienceAfter': {'onlineRsiVersions': [g0]}},
        {'spec': {'id': 'FA03'}, 'online_rsi': {
            'id': 'use-run', 'evolution': {'usedVersionId': 'g0', 'matchVersion': 1},
            'toolTrace': [{'executor': 'graph', 'ok': True}],
        }},
    ]}
    revisions = AnalysisDatasets._attribution_revisions(item)
    assert len(revisions) == 1
    assert revisions[0]['sourcePairId'] == 'FA02'
    assert revisions[0]['sourceRunId'] == 'revise-run'
    assert revisions[0]['graphChanged'] is False
    assert revisions[0]['matchingChanged'] is True
    assert revisions[0]['subsequentUses'] == [
        {'pairId': 'FA03', 'taskId': 'FA03', 'runId': 'use-run', 'matchVersion': 1}
    ]
    item['pairs'][2]['online_rsi']['toolTrace'] = []
    assert AnalysisDatasets._attribution_revisions(item)[0]['subsequentUses'] == []


def test_cost_estimate_uses_role_phase_models_and_refuses_unknown_usage_or_prices():
    pricing = deepcopy(MODEL_PRICING)
    mixed = {
        'metrics': {'inputTokens': 100, 'outputTokens': 20, 'usageComplete': True},
        'models': {
            'planner': 'qwen/qwen3.5-9b',
            'composition': 'qwen/qwen3.5-27b',
            'executor': 'qwen/qwen3.5-27b',
        },
        'phaseMetrics': {
            'plan': {'inputTokens': 60, 'outputTokens': 10, 'usageComplete': True},
            'composition': {'inputTokens': 0, 'outputTokens': 0, 'usageComplete': True},
            'execute': {'inputTokens': 40, 'outputTokens': 10, 'usageComplete': True},
        },
    }
    assert AnalysisDatasets._cost_usd(mixed, pricing) == .0000295
    assert AnalysisDatasets._cost_usd({**mixed, 'metrics': {**mixed['metrics'], 'usageComplete': False}}, pricing) is None
    assert AnalysisDatasets._cost_usd({**mixed, 'models': {**mixed['models'], 'executor': 'missing/model'}}, pricing) is None


def test_cumulative_version_snapshots_do_not_duplicate_revision_or_invent_later_use():
    version = {'id': 'g1', 'generation': 1, 'matchVersion': 1, 'parentGraphId': 'g0',
               'sourceRunId': 'source', 'patches': [{'before': ['read'], 'after': ['read', 'filter']}],
               'matchPatches': [{'before': {'purpose': 'old'}, 'after': {'purpose': 'new'}, 'sourceRunId': 'source'}]}
    item = {'pairs': [
        {'spec': {'id': 'F3'}, 'online_rsi': {'id': 'source'}, 'experienceAfter': {'onlineRsiVersions': [version]}},
        {'spec': {'id': 'F4'}, 'online_rsi': {'id': 'loaded', 'evolution': {'usedVersionId': 'g1'}, 'toolTrace': []}, 'experienceAfter': {'onlineRsiVersions': [version]}},
        {'spec': {'id': 'F5'}, 'online_rsi': {'id': 'executed', 'evolution': {'usedVersionId': 'g1'}, 'toolTrace': [{'executor': 'graph', 'ok': True}]}, 'experienceAfter': {'onlineRsiVersions': [version]}},
    ]}
    revisions = AnalysisDatasets._attribution_revisions(item)
    assert len(revisions) == 1 and revisions[0]['sourcePairId'] == 'F3'
    assert [use['pairId'] for use in revisions[0]['subsequentUses']] == ['F5']


def test_attribution_detail_link_keeps_the_registered_release_context(tmp_path):
    store, _, _, manifest = attribution_fixture(tmp_path)
    registry = json.loads(store.path.read_text())
    registry['datasets'][0]['releaseId'] = 'finance-attribution-v4'
    write_private(store.path, registry)
    result = store.get(manifest['datasetId'])
    assert result['dataset']['releaseId'] == 'finance-attribution-v4'
    assert result['points'][0]['detailUrl'] == '/api/releases/finance-attribution-v4/pairs/FA01'


def test_numbering_only_successor_is_excluded_from_evolution_projection():
    def compiled(first, second):
        return {'descriptor': {'slots': {}, 'schema': {}}, 'nodes': [
            {'id': first, 'tool': 'map', 'arguments': {'field': 'amount'}, 'effect': 'compute', 'dependencies': [], 'paginate': False},
            {'id': second, 'tool': 'sum', 'arguments': {'receipt': {'$output': {'nodeId': first, 'path': ['receiptId']}}}, 'effect': 'compute', 'dependencies': [first], 'paginate': False},
        ]}
    version = {'id': 'g1', 'parentGraphId': 'g0', 'generation': 1, 'matchVersion': 1, 'sourceRunId': 'b',
               'patches': [{'before': ['t0'], 'after': ['t9']}], 'matchPatches': [{'before': {'id': 't0'}, 'after': {'id': 't9'}, 'sourceRunId': 'b'}]}
    item = {'pairs': [
        {'spec': {'id': 'one'}, 'online_rsi': {'id': 'a', 'evolution': {'generatedVersionIds': ['g0'], 'trajectoryCompilation': compiled('t0','t1')}}},
        {'spec': {'id': 'two'}, 'online_rsi': {'id': 'b', 'evolution': {'generatedVersionIds': ['g1'], 'trajectoryCompilation': compiled('t9','t8')}}, 'experienceAfter': {'onlineRsiVersions': [version]}},
    ]}
    assert AnalysisDatasets._attribution_revisions(item) == []


def formal_attribution_with_diagnostics_fixture(root: Path):
    repository = Path(__file__).resolve().parents[1]
    registry = json.loads((repository / 'releases/analysis-manifest.json').read_text())
    manifest = deepcopy(next(row for row in registry['datasets'] if row['datasetId'] == 'finance-attribution-v4-6'))
    experiment_source = repository / 'artifacts/attribution-experiments' / manifest['experimentId'] / 'experiment.json'
    experiment_target = root / 'artifacts/attribution-experiments' / manifest['experimentId'] / 'experiment.json'
    experiment_target.parent.mkdir(parents=True, exist_ok=True)
    experiment_target.write_bytes(experiment_source.read_bytes())
    for entry in manifest['maintenanceDiagnostics']:
        source = repository / 'artifacts/attribution-diagnostics' / entry['diagnosticId'] / 'diagnostic.json'
        target = root / 'artifacts/attribution-diagnostics' / entry['diagnosticId'] / 'diagnostic.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    write_private(root / 'releases/analysis-manifest.json', {
        'schemaVersion': 1,
        'defaultDatasetId': manifest['datasetId'],
        'modelPricing': MODEL_PRICING,
        'datasets': [manifest],
    })
    return AnalysisDatasets(root), manifest


def test_formal_attribution_projects_cross_runtime_maintenance_without_changing_kpis(tmp_path):
    store, manifest = formal_attribution_with_diagnostics_fixture(tmp_path)
    result = store.get(manifest['datasetId'])
    diagnostic = result['maintenanceDiagnostics']
    assert len(result['points']) == result['summary']['pairedCompleted'] == 6
    assert result['summary']['baseline']['tokens'] == 944492
    assert result['summary']['rsi']['tokens'] == 549900
    assert result['points'][-1]['cumulativeBaselineTokens'] == 944492
    assert result['points'][-1]['cumulativeRsiTokens'] == 549900
    assert diagnostic['excludedFromFormalMetrics'] is True
    assert diagnostic['sourceTaskId'] == 'FA06'
    assert diagnostic['formal']['modelRequests'] == 13
    assert diagnostic['formal']['tokens'] == 183752
    assert diagnostic['formal']['latencyMs'] == 170786.096
    assert diagnostic['validated']['modelRequests'] == 3
    assert diagnostic['validated']['tokens'] == 40158
    assert diagnostic['validated']['latencyMs'] == 62880.277
    assert diagnostic['validated']['usedVersionId'] == '4a9f228d-4917-4afe-80a4-f2fa6f85f31f'
    assert diagnostic['validated']['usedMatchVersion'] == 2
    assert diagnostic['validated']['selectedGraphNodeCount'] == 15
    assert diagnostic['failedSetup']['diagnosticStatus'] == 'configuration_failed'
    assert diagnostic['failedSetup']['learningEnabled'] is False
    serialized_points = json.dumps(result['points'])
    assert diagnostic['validated']['runId'] not in serialized_points
    assert diagnostic['failedSetup']['runId'] not in serialized_points


def test_maintenance_diagnostic_fails_closed_on_digest_runtime_and_source_task_mismatch(tmp_path):
    store, manifest = formal_attribution_with_diagnostics_fixture(tmp_path)
    registry_path = tmp_path / 'releases/analysis-manifest.json'
    validated = manifest['maintenanceDiagnostics'][0]
    path = tmp_path / 'artifacts/attribution-diagnostics' / validated['diagnosticId'] / 'diagnostic.json'

    path.write_text(path.read_text() + '\n')
    with pytest.raises(ValueError, match='维护诊断保存工件摘要不一致'):
        store.get(manifest['datasetId'])
    source = Path(__file__).resolve().parents[1] / 'artifacts/attribution-diagnostics' / validated['diagnosticId'] / 'diagnostic.json'
    path.write_bytes(source.read_bytes())

    for key, value in [('runtimeRevision', 'sha256:other'), ('sourceTaskId', 'FA05')]:
        registry = json.loads(registry_path.read_text())
        registry['datasets'][0]['maintenanceDiagnostics'][0][key] = value
        write_private(registry_path, registry)
        with pytest.raises(ValueError, match='维护诊断'):
            store.get(manifest['datasetId'])
        write_private(registry_path, {
            'schemaVersion': 1,
            'defaultDatasetId': manifest['datasetId'],
            'modelPricing': MODEL_PRICING,
            'datasets': [manifest],
        })


def test_maintenance_diagnostic_api_is_read_only_and_release_scoped(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import backend.app as module

    store, manifest = formal_attribution_with_diagnostics_fixture(tmp_path)
    monkeypatch.setattr(module, 'AnalysisDatasets', lambda root: store)
    client = TestClient(module.create_app())
    diagnostic_id = manifest['maintenanceDiagnostics'][0]['diagnosticId']
    response = client.get(f'/api/analysis/datasets/{manifest["datasetId"]}/maintenance-diagnostics/{diagnostic_id}')
    assert response.status_code == 200
    payload = response.json()
    assert payload['datasetId'] == manifest['datasetId']
    assert payload['experimentId'] == manifest['experimentId']
    assert payload['excludedFromFormalMetrics'] is True
    assert payload['diagnostic']['tokens'] == 40158
    assert client.get(f'/api/analysis/datasets/{manifest["datasetId"]}/maintenance-diagnostics/not-registered').status_code == 404


def test_attribution_summary_exposes_saved_execution_decision_stages_without_inventing_requests():
    root = Path(__file__).resolve().parents[1]
    result = AnalysisDatasets(root).get('finance-attribution-v4-6')
    baseline = result['summary']['baseline']['executionStages']
    rsi = result['summary']['rsi']['executionStages']
    assert {key: row['requests'] for key, row in baseline.items()} == {
        'read_selection_and_binding': 5,
        'compute_selection_and_binding': 55,
        'mixed_tool_decision': 0,
        'report_composition': 6,
    }
    assert {key: row['requests'] for key, row in rsi.items()} == {
        'read_selection_and_binding': 6,
        'compute_selection_and_binding': 22,
        'mixed_tool_decision': 1,
        'report_composition': 6,
    }
    assert sum(row['requests'] for row in baseline.values()) == 66
    assert sum(row['requests'] for row in rsi.values()) == 35
    assert result['summary']['baseline']['modelRequests'] == 72
    assert result['summary']['rsi']['modelRequests'] == 42
    assert all(row['usageComplete'] is True and row['tokens'] is not None for row in baseline.values())


def test_execution_stage_projection_prefers_saved_metrics_and_keeps_failed_execute_usage_unknown():
    saved = {
        'executionStageMetrics': {
            'read_selection_and_binding': {
                'requests': 2, 'inputTokens': 10, 'outputTokens': 2, 'usageComplete': True,
            },
            'terminal_response': {
                'requests': 1, 'inputTokens': 4, 'outputTokens': 1, 'usageComplete': True,
            },
        },
        'events': [{'type': 'model', 'title': 'execute', 'detail': {'usage': {'input': 999, 'output': 1}}}],
    }
    result = AnalysisDatasets._execution_stages({'pairs': [{'no_learning': saved}]}, 'no_learning', {})
    assert result['read_selection_and_binding']['requests'] == 2
    assert result['read_selection_and_binding']['tokens'] == 12
    assert result['mixed_tool_decision']['requests'] == 1
    assert result['mixed_tool_decision']['tokens'] == 5
    assert result['compute_selection_and_binding']['requests'] == 0

    failed = {'events': [{'type': 'model_error', 'title': 'execute', 'detail': {}}]}
    result = AnalysisDatasets._execution_stages({'pairs': [{'online_rsi': failed}]}, 'online_rsi', {})
    assert result['mixed_tool_decision']['requests'] == 1
    assert result['mixed_tool_decision']['usageComplete'] is False
    assert result['mixed_tool_decision']['tokens'] is None
