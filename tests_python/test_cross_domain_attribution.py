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
    stage1, stage2, stage3 = assets.campaign_plan(manifest['tasks'])
    assert (len(stage1), len(stage2), len(stage3)) == (12, 12, 24)
    assert len({row['id'] for row in stage1 + stage2 + stage3}) == 48
    assert [row['campaignStage'] for row in stage1 + stage2 + stage3] == [1] * 12 + [2] * 12 + [3] * 24
    assert {scenario: sum(row['scenario'] == scenario for row in stage1 + stage2)
            for scenario in ('finance', 'support', 'tickets')} == {'finance': 8, 'support': 8, 'tickets': 8}
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


def test_cross_domain_expansion_gate_allows_more_reliable_online_arm_without_cost_claim():
    from backend.attribution_experiment import summarize

    def run(status='passed', used=False):
        return {
            'id': status + ('-used' if used else ''),
            'status': 'completed' if status == 'passed' else 'limited',
            'evaluation': {'status': status},
            'metrics': {
                'usageComplete': True, 'inputTokens': 10, 'outputTokens': 2,
                'modelRequests': 1, 'toolCalls': 1, 'toolErrors': 0,
                'durationMs': 10,
            },
            'evolution': {'usedVersionId': 'g0' if used else None},
            'toolTrace': ([{'ok': True, 'executor': 'graph'}] if used else []),
        }

    item = {
        'mode': 'cross_domain_probe', 'status': 'completed',
        'manifest': [{'id': 'one'}, {'id': 'two'}],
        'protocol': {'actualGraphUseMinimumRate': .5},
        'pairs': [
            {'status': 'completed', 'spec': {'id': 'one', 'position': 1, 'title': 'one', 'opportunity': 'create', 'sourceTaskId': 'one'},
             'no_learning': run(), 'online_rsi': run()},
            {'status': 'completed', 'spec': {'id': 'two', 'position': 2, 'title': 'two', 'opportunity': 'reuse', 'sourceTaskId': 'two'},
             'no_learning': run('failed'), 'online_rsi': run(used=True)},
        ],
    }
    result = summarize(item)
    assert result['qualityGate'] is False
    assert result['expansionGate'] is True
    assert result['costConclusionAllowed'] is False
    assert result['comparativeConclusionAllowed'] is False


def test_cross_domain_campaign_gate_allows_one_task_relative_quality_gap():
    from backend.attribution_experiment import campaign_gate_snapshot

    def run(passed=True, used=False):
        return {
            'status': 'completed' if passed else 'limited',
            'evaluation': {'status': 'passed' if passed else 'failed'},
            'metrics': {'usageComplete': True},
            'evolution': {'usedVersionId': 'g0' if used else None},
            'toolTrace': ([{'ok': True, 'executor': 'graph'}] if used else []),
        }

    task_ids = ['one', 'two', 'three']
    item = {
        'protocol': {'actualGraphUseMinimumRate': .5, 'maximumOnlineQualityGapTasks': 1},
        'pairs': [
            {'status': 'completed', 'spec': {'id': task_id}, 'no_learning': run(),
             'online_rsi': run(passed=index != 2, used=index < 2)}
            for index, task_id in enumerate(task_ids)
        ],
    }
    gate = campaign_gate_snapshot(item, task_ids)
    assert gate['noLearningPassed'] == 3
    assert gate['onlineRsiPassed'] == 2
    assert gate['onlineQualityGapTasks'] == 1
    assert gate['relativeQualityGate'] is True
    assert gate['expansionGate'] is True

    item['protocol']['maximumOnlineQualityGapTasks'] = 0
    strict_gate = campaign_gate_snapshot(item, task_ids)
    assert strict_gate['relativeQualityGate'] is False
    assert strict_gate['expansionGate'] is False


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
    assert started['summary']['expansionGate'] is False
    captured['coro'].close()
    experiment.tasks.clear()
    captured.clear()
    formal = await experiment.start('cross_domain_formal')
    assert formal['predecessorId'] is None
    assert len(formal['manifest']) == 24
    assert len(formal['campaign']['stage1']['taskIds']) == 12
    assert len(formal['campaign']['stage2']['taskIds']) == 12
    assert len(formal['campaign']['stage3']['taskIds']) == 24
    assert len(formal['campaign']['allTaskIds']) == 48
    assert formal['campaign']['stage3']['status'] == 'frozen_waiting_for_explicit_expansion'
    captured['coro'].close()

@pytest.mark.asyncio
async def test_cross_domain_campaign_runs_24_then_restores_same_experience_for_48(tmp_path, monkeypatch):
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
            'campaignStage': (1 if scenario_position in assets.CAMPAIGN_STAGE1_POSITIONS
                              else 2 if scenario_position in assets.CAMPAIGN_STAGE2_POSITIONS else 3),
        })
    frozen_asset = {'version': assets.VERSION, 'tasks': deepcopy(fake_tasks)}
    monkeypatch.setattr(assets, 'build', lambda root: deepcopy(frozen_asset))
    verified = []
    monkeypatch.setattr(assets, 'verify_task_files', lambda root, spec: verified.append(spec['id']))
    runtime_digest = ['runtime']
    monkeypatch.setattr(module, 'fingerprint', lambda root: {'files': {}, 'digest': runtime_digest[0]})
    monkeypatch.setattr(AttributionExperiment, '_validate_model', lambda self: None)
    installed = []

    def fake_install(manager, root, spec):
        installed.append(spec['id'])
        return {'id': 'workspace-' + spec['id']}, {'id': 'task-' + spec['id']}

    monkeypatch.setattr(assets, 'install', fake_install)

    class FakeEvolution:
        stores = {}
        restore_calls = []

        def __init__(self, path, learning_enabled):
            self.path = str(path)
            self.learning_enabled = learning_enabled
            self.versions = []

        def restore(self):
            self.restore_calls.append((self.path, self.learning_enabled))
            self.versions = deepcopy(self.stores.get(self.path, []))

        def persist(self):
            self.stores[self.path] = deepcopy(self.versions)

    class FakeRunner:
        starts = []

        def __init__(self, bank, provider_factory=None, run_limit=None, model_limit=None, read_limit=None,
                     run_directory=None, evolution_path=None, learning_enabled=True):
            self.learning_enabled = learning_enabled
            self.evolution = FakeEvolution(evolution_path, learning_enabled)
            self.tasks = {}

        def restore(self):
            self.evolution.restore()

        async def start(self, request, *, evaluation_context=None):
            task_id = request.taskId.removeprefix('task-')
            self.starts.append((self.learning_enabled, task_id))
            run_id = f'{"online" if self.learning_enabled else "baseline"}-{task_id}'
            used = self.learning_enabled and bool(self.evolution.versions)
            run = {
                'id': run_id,
                'taskId': request.taskId,
                'status': 'completed',
                'evaluation': {'status': 'passed'},
                'metrics': {
                    'usageComplete': True, 'inputTokens': 10, 'outputTokens': 2,
                    'modelRequests': 1, 'toolCalls': 1, 'toolErrors': 0, 'durationMs': 10,
                },
                'evolution': {'usedVersionId': self.evolution.versions[-1]['id'] if used else None},
                'toolTrace': ([{'ok': True, 'executor': 'graph'}] if used else []),
            }
            if not self.learning_enabled and task_id == fake_tasks[1]['id']:
                run.update(status='limited', evaluation={'status': 'failed'})
            if self.learning_enabled:
                self.evolution.versions.append({
                    'id': 'graph-' + task_id, 'generation': 0, 'matchVersion': 0,
                    'sourceRunId': run_id, 'patches': [], 'matchPatches': [],
                })
                self.evolution.persist()
            self.tasks[run_id] = asyncio.create_task(asyncio.sleep(0))
            return run

        async def shutdown(self):
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    monkeypatch.setattr(module, 'TaskRunner', FakeRunner)
    experiment = AttributionExperiment(tmp_path)
    started = await experiment.start('cross_domain_formal')
    experiment_id = started['id']
    initial_task = experiment.tasks[experiment_id]
    await initial_task
    first = experiment.get(experiment_id)
    stage1, stage2, stage3 = assets.campaign_plan(fake_tasks)
    first_24 = [row['id'] for row in stage1 + stage2]
    all_48 = [row['id'] for row in stage1 + stage2 + stage3]
    assert first['status'] == 'completed'
    assert first['campaign']['status'] == 'completed_24'
    assert first['campaign']['stage1']['gate']['expansionGate'] is True
    assert first['campaign']['stage2']['status'] == 'completed'
    assert first['campaign']['stage3']['status'] == 'frozen_waiting_for_explicit_expansion'
    assert [pair['spec']['id'] for pair in first['pairs']] == first_24
    assert installed == first_24
    online_path = str(tmp_path / 'artifacts' / 'attribution-experiments' / experiment_id / 'online_rsi' / 'experience.json')
    assert len(FakeEvolution.stores[online_path]) == 24

    runtime_digest[0] = 'changed'
    with pytest.raises(ValueError, match='runtime changed'):
        await experiment.continue_campaign(experiment_id, target_pairs=48)
    assert len(experiment.get(experiment_id)['manifest']) == 24
    runtime_digest[0] = 'runtime'
    resumed = await experiment.continue_campaign(experiment_id, target_pairs=48)
    assert resumed['id'] == experiment_id
    continuation_task = experiment.tasks[experiment_id]
    await continuation_task
    final = experiment.get(experiment_id)
    assert final['status'] == 'completed'
    assert final['campaign']['status'] == 'expanded_to_48'
    assert final['campaign']['stage3']['status'] == 'completed'
    assert [pair['spec']['id'] for pair in final['pairs']] == all_48
    assert len({pair['spec']['id'] for pair in final['pairs']}) == 48
    assert installed == all_48
    assert [task_id for learning, task_id in FakeRunner.starts if learning] == all_48
    assert (online_path, True) in FakeEvolution.restore_calls
    assert len(FakeEvolution.stores[online_path]) == 48
    assert set(verified) == {row['id'] for row in stage3}

@pytest.mark.asyncio
async def test_cross_domain_campaign_gate_failure_stops_before_stage2(tmp_path, monkeypatch):
    from backend import attribution_experiment as module

    fake_tasks = []
    for index in range(48):
        scenario = ('finance', 'support', 'tickets')[index // 16]
        scenario_position = index % 16 + 1
        fake_tasks.append({
            'id': f'{scenario[0].upper()}{scenario_position:02d}', 'position': index + 1,
            'title': str(index + 1), 'opportunity': 'test', 'sourceTaskId': f'source-{index + 1}',
            'scenario': scenario, 'scenarioPosition': scenario_position,
            'campaignStage': (1 if scenario_position in assets.CAMPAIGN_STAGE1_POSITIONS
                              else 2 if scenario_position in assets.CAMPAIGN_STAGE2_POSITIONS else 3),
        })
    monkeypatch.setattr(assets, 'build', lambda root: {'version': assets.VERSION, 'tasks': deepcopy(fake_tasks)})
    monkeypatch.setattr(assets, 'install', lambda manager, root, spec: (
        {'id': 'workspace-' + spec['id']}, {'id': 'task-' + spec['id']},
    ))
    monkeypatch.setattr(module, 'fingerprint', lambda root: {'files': {}, 'digest': 'runtime'})
    monkeypatch.setattr(AttributionExperiment, '_validate_model', lambda self: None)

    class Evolution:
        def __init__(self):
            self.versions = []

    class Runner:
        starts = []

        def __init__(self, bank, provider_factory=None, run_limit=None, model_limit=None, read_limit=None,
                     run_directory=None, evolution_path=None, learning_enabled=True):
            self.learning_enabled = learning_enabled
            self.evolution = Evolution()
            self.tasks = {}

        async def start(self, request, *, evaluation_context=None):
            task_id = request.taskId.removeprefix('task-')
            self.starts.append((self.learning_enabled, task_id))
            run_id = f'{self.learning_enabled}-{task_id}'
            passed = not (self.learning_enabled and len([row for row in self.starts if row[0]]) == 1)
            run = {
                'id': run_id, 'taskId': request.taskId,
                'status': 'completed' if passed else 'limited',
                'evaluation': {'status': 'passed' if passed else 'failed'},
                'metrics': {'usageComplete': True, 'inputTokens': 1, 'outputTokens': 1,
                            'modelRequests': 1, 'toolCalls': 1, 'toolErrors': 0, 'durationMs': 1},
                'evolution': {}, 'toolTrace': [],
            }
            self.tasks[run_id] = asyncio.create_task(asyncio.sleep(0))
            return run

        async def shutdown(self):
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    monkeypatch.setattr(module, 'TaskRunner', Runner)
    experiment = AttributionExperiment(tmp_path)
    started = await experiment.start('cross_domain_formal')
    experiment_id = started['id']
    task = experiment.tasks[experiment_id]
    await task
    saved = experiment.get(experiment_id)
    assert saved['status'] == 'gate_stopped'
    assert saved['campaign']['status'] == 'stopped_at_12'
    assert saved['campaign']['stage2']['status'] == 'blocked_by_stage1_gate'
    assert len(saved['pairs']) == 12
    assert len(Runner.starts) == 24


def test_two_domain_manifest_freezes_twelve_finance_and_twelve_ticket_tasks():
    from backend.attribution_experiment import two_domain_manifest

    manifest = assets.build(ROOT)
    selected = two_domain_manifest(manifest['tasks'])
    assert len(selected) == 24
    assert [row['id'] for row in selected[:12]] == [f'F{index:02d}' for index in range(1, 13)]
    assert [row['id'] for row in selected[12:]] == [f'T{index:02d}' for index in range(1, 13)]
    assert {row['scenario'] for row in selected} == {'finance', 'tickets'}
    assert [row['id'] for row in two_domain_manifest(manifest['tasks'], probe=True)] == [
        'F01', 'F02', 'T01', 'T02',
    ]


@pytest.mark.asyncio
async def test_two_domain_probe_runs_paired_arms_in_parallel_with_isolated_learning(tmp_path, monkeypatch):
    from backend import attribution_experiment as module

    fake_tasks = [
        {
            'id': f'{prefix}{index:02d}', 'position': offset + index,
            'title': f'{scenario}-{index}', 'opportunity': 'test',
            'sourceTaskId': f'{prefix}{index:02d}', 'scenario': scenario,
            'scenarioPosition': index,
        }
        for offset, scenario, prefix in ((0, 'finance', 'F'), (32, 'tickets', 'T'))
        for index in range(1, 13)
    ]
    monkeypatch.setattr(assets, 'build', lambda root: {'version': assets.VERSION, 'tasks': deepcopy(fake_tasks)})
    monkeypatch.setattr(assets, 'install', lambda manager, root, spec: (
        {'id': 'workspace-' + spec['id']}, {'id': 'task-' + spec['id']},
    ))
    monkeypatch.setattr(module, 'fingerprint', lambda root: {'files': {}, 'digest': 'runtime'})
    monkeypatch.setattr(AttributionExperiment, '_validate_model', lambda self: None)
    monkeypatch.setattr(module.config, 'API_KEY', 'primary')
    monkeypatch.setattr(module.config, 'SECONDARY_API_KEY', 'secondary')
    events = []

    class Evolution:
        def __init__(self):
            self.versions = []

    class Runner:
        def __init__(self, bank, provider_factory=None, run_limit=None, model_limit=None, read_limit=None,
                     run_directory=None, evolution_path=None, learning_enabled=True):
            self.learning_enabled = learning_enabled
            self.provider_factory = provider_factory
            self.evolution = Evolution()
            self.tasks = {}

        async def start(self, request, *, evaluation_context=None):
            task_id = request.taskId.removeprefix('task-')
            arm = 'online' if self.learning_enabled else 'baseline'
            events.append(('start', task_id, arm))
            used = self.learning_enabled and bool(self.evolution.versions)
            run_id = f'{arm}-{task_id}'
            run = {
                'id': run_id, 'taskId': request.taskId, 'status': 'completed',
                'evaluation': {'status': 'passed'},
                'metrics': {'usageComplete': True, 'inputTokens': 10, 'outputTokens': 2,
                            'modelRequests': 1, 'toolCalls': 1, 'toolErrors': 0, 'durationMs': 10},
                'evolution': {'usedVersionId': self.evolution.versions[-1]['id'] if used else None},
                'toolTrace': ([{'ok': True, 'executor': 'graph'}] if used else []),
            }
            if self.learning_enabled:
                self.evolution.versions.append({
                    'id': 'graph-' + task_id, 'generation': 0, 'matchVersion': 0,
                    'sourceRunId': run_id, 'patches': [], 'matchPatches': [],
                })

            async def finish():
                await asyncio.sleep(0)
                events.append(('done', task_id, arm))

            self.tasks[run_id] = asyncio.create_task(finish())
            return run

        async def shutdown(self):
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    monkeypatch.setattr(module, 'TaskRunner', Runner)
    experiment = AttributionExperiment(tmp_path)
    started = await experiment.start('finance_tickets_probe')
    await experiment.tasks[started['id']]
    saved = experiment.get(started['id'])
    assert saved['status'] == 'completed'
    assert saved['protocol']['executionPolicy'] == 'parallel_dual_key'
    assert saved['protocol']['armOrder'].startswith('parallel dual-key')
    assert [row['id'] for row in saved['manifest']] == ['F01', 'F02', 'T01', 'T02']
    assert saved['summary']['qualityGate'] is True
    for task_id in ['F01', 'F02', 'T01', 'T02']:
        starts = [index for index, event in enumerate(events) if event[:2] == ('start', task_id)]
        dones = [index for index, event in enumerate(events) if event[:2] == ('done', task_id)]
        assert len(starts) == 2 and len(dones) == 2
        assert max(starts) < min(dones)
