"""Analysis datasets are pinned read-only projections of one saved experiment."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from backend.analysis_datasets import AnalysisDatasets
from backend.graph_store import write_private


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
                             'evaluation': {'status': 'passed'}},
                'rsi': {'id': f'rsi-{index}', 'status': 'completed', 'metrics': deepcopy(metrics_b),
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
                  {'schemaVersion': 1, 'defaultDatasetId': 'v17', 'datasets': [manifest]})
    return AnalysisDatasets(root), experiment_path, experiment


def test_analysis_dataset_is_pinned_and_derives_token_and_serial_latency_curves(tmp_path):
    store, _, _ = fixture(tmp_path)
    listing = store.list()
    assert listing['defaultDatasetId'] == 'v17' and len(listing['items']) == 1
    result = store.get('v17')
    assert result['summary']['tokenSaving'] == .5
    assert result['summary']['latencySaving'] == .4
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
    assert [row['datasetId'] for row in listing['items']] == ['workpack-v17-48', 'taskbank-v4-36']
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
