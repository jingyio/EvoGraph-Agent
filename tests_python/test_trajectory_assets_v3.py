"""V3 asset construction checks only; never invoke a model."""
import json
from collections import Counter
from backend.config import ROOT
from backend.trajectory_assets_v3 import VERSION, PRECHECK, build, install, task_plan
from backend.workspace import WorkspaceManager


def test_v3_freezes_48_heterogeneous_train_and_independent_holdouts():
    manifest=build(ROOT)
    assert manifest['version']==VERSION
    assert Counter(task['split'] for task in manifest['tasks'])=={'train':48,'validation':6,'test':6}
    train=[task for task in manifest['tasks'] if task['split']=='train']
    assert Counter(task['scenario'] for task in train)=={'finance':16,'support':16,'tickets':16}
    assert sum(task['precheck'] for task in train)==12
    assert {task['id'] for task in train if task['precheck']}==set().union(*PRECHECK.values())
    assert all(task['auditFeatures'] for task in train)
    assert len({task['requestHash'] for task in train})==48
    assert len({tuple(task['recordIds']) for task in manifest['tasks']})==60


def test_v3_install_exposes_only_current_task_contract(tmp_path):
    manifest=json.loads((ROOT/'benchmarks/history/trajectory-review-v3.json').read_text())
    spec=next(task for task in manifest['tasks'] if task['id']=='F01')
    manager=WorkspaceManager(tmp_path)
    _,task=install(manager,ROOT,spec)
    assert task['split']=='train' and 'auditFeatures' not in json.dumps(task)
    contract=task['deliveryContract']
    assert contract['requiredGroupNames']==spec['requiredGroupNames']
    assert contract['requiredMetricKeys']==spec['requiredMetricKeys']
    prompt=task['task']
    assert 'workspace_' not in prompt and 'F01' not in prompt


def test_opportunity_audit_is_frozen_offline_only_and_not_runtime_input():
    payload=json.loads((ROOT/'benchmarks/history/trajectory-review-v3-opportunity-audit.json').read_text())
    assert payload['version']==VERSION and payload['offlineOnly'] is True
    assert len(payload['rows'])==48
    assert all(row['offlineAuditOnly'] for row in payload['rows'])
    assert set(payload['capabilityRecurrenceMatrix'])=={'finance','support','tickets'}
