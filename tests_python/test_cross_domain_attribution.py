from copy import deepcopy
import asyncio
import hashlib
import json

import pytest

from backend import cross_domain_attribution_assets as assets
from backend.attribution_experiment import AttributionExperiment
from backend.config import ROOT
from backend.workspace import WorkspaceManager


def test_cross_domain_asset_freezes_48_tasks_and_six_cohorts():
    manifest = assets.build(ROOT)
    assert manifest['version'] == assets.VERSION
    assert len(manifest['tasks']) == 48
    assert [row['position'] for row in manifest['tasks']] == list(range(1, 49))
    assert {scenario: sum(row['scenario'] == scenario for row in manifest['tasks'])
            for scenario in ('finance', 'support', 'tickets')} == {
                'finance': 16, 'support': 16, 'tickets': 16,
            }
    assert {cohort: sum(row['cohort'] == cohort for row in manifest['tasks'])
            for cohort in {row['cohort'] for row in manifest['tasks']}} == {
                'finance-reconciliation': 8,
                'finance-payment-health': 8,
                'support-service-timing': 8,
                'support-response-coverage': 8,
                'tickets-activity-triage': 8,
                'tickets-delivery-readiness': 8,
            }
    assert [row['id'] for row in manifest['tasks'] if row.get('precheck')] == [
        'F01', 'F05', 'F10', 'F11',
        'C01', 'C04', 'C10', 'C11',
        'T01', 'T04', 'T10', 'T11',
    ]
    for row in manifest['tasks']:
        directory = ROOT / 'artifacts' / assets.VERSION / row['id']
        source = ROOT / 'artifacts' / assets.SOURCE_VERSION / row['sourceTaskId']
        assert (directory / 'request.txt').read_bytes() == (source / 'request.txt').read_bytes()
        assert (directory / 'inputs.json').read_bytes() == (source / 'inputs.json').read_bytes()
        assert hashlib.sha256((directory / 'inputs.json').read_bytes()).hexdigest() == row['inputHash']
        assert hashlib.sha256((directory / 'request.txt').read_bytes()).hexdigest() == row['requestHash']
        assert hashlib.sha256((directory / 'private.json').read_bytes()).hexdigest() == row['scoreHash']


@pytest.mark.parametrize(('task_id', 'scenario', 'selected_field'), [
    ('C01', 'support', 'complaint_id'),
    ('T01', 'tickets', 'issue_id'),
])
def test_cross_domain_install_uses_granular_tools_and_public_metric_semantics(
    tmp_path, task_id, scenario, selected_field,
):
    manifest = assets.build(ROOT)
    spec = next(row for row in manifest['tasks'] if row['id'] == task_id)
    manager = WorkspaceManager(tmp_path)
    _, public = assets.install(manager, ROOT, spec)
    internal = manager.tasks[public['id']]
    contract = public['deliveryContract']
    assert public['scenario'] == scenario
    assert internal['computeInterface'] == 'granular-compute-v1'
    assert contract['selectedIdField'] == selected_field
    assert contract['selectedIdsPolicy'] == 'union_of_groups'
    assert set(contract['metricDescriptions']) == set(contract['requiredMetricKeys'])
    assert all(isinstance(value, str) and value for value in contract['metricDescriptions'].values())
    assert contract['fieldValueNotes'] == assets.FIELD_VALUE_NOTES[scenario]
    report = next(tool for tool in manager.tools(public['id']) if tool.name == 'workspace_publish_report')
    schema = report.parameters['properties']['metrics']['properties']
    assert set(schema) == set(contract['requiredMetricKeys'])
    assert 'expected' not in json.dumps(report.parameters)
    if task_id == 'C01':
        assert contract['requiredTableSlots'] == ['complaints', 'responses']
        assert len(internal['publicScopeEvidenceIds']) == 20
        assert 'workspace_compare_datetimes' in {tool.name for tool in manager.tools(public['id'])}


@pytest.mark.asyncio
async def test_cross_domain_probe_selects_twelve_frozen_precheck_pairs(tmp_path, monkeypatch):
    from backend import attribution_experiment as module

    fake_tasks = []
    for index in range(48):
        scenario = ('finance', 'support', 'tickets')[index // 16]
        scenario_position = index % 16 + 1
        fake_tasks.append({
            'id': f'{scenario[0].upper()}{scenario_position:02d}',
            'position': index + 1,
            'title': str(index + 1),
            'opportunity': 'test',
            'sourceTaskId': f'source-{index + 1}',
            'scenario': scenario,
            'scenarioPosition': scenario_position,
            'precheck': scenario_position in {1, 5, 10, 11},
        })
    monkeypatch.setattr(assets, 'build', lambda root: {'tasks': deepcopy(fake_tasks)})
    monkeypatch.setattr(module, 'fingerprint', lambda root: {'files': {}, 'digest': 'runtime'})
    monkeypatch.setattr(AttributionExperiment, '_validate_model', lambda self: None)
    captured = {}

    class Pending:
        def cancel(self):
            pass

    def capture(coro):
        captured['coro'] = coro
        return Pending()

    monkeypatch.setattr(asyncio, 'create_task', capture)
    experiment = AttributionExperiment(tmp_path)
    smoke = await experiment.start('cross_domain_smoke')
    assert [(row['scenario'], row['scenarioPosition']) for row in smoke['manifest']] == [
        ('support', 1), ('tickets', 1),
    ]
    assert smoke['protocol']['actualGraphUseMinimumRate'] is None
    assert smoke['summary']['costConclusionAllowed'] is False
    captured['coro'].close()
    experiment.tasks.clear()
    captured.clear()
    started = await experiment.start('cross_domain_probe')
    assert len(started['manifest']) == 12
    assert started['assetVersion'] == assets.VERSION
    assert started['protocol']['id'] == 'cross-domain-graph-rsi-learning-attribution-v1'
    assert started['protocol']['taskCountPerArm'] == 12
    assert started['protocol']['actualGraphUseMinimumRate'] == .5
    assert started['summary']['costConclusionAllowed'] is False
    captured['coro'].close()
