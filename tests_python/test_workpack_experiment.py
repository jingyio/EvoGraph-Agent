import asyncio
from pathlib import Path
from uuid import uuid4

from backend.taskbank import TaskBank
from backend.workpack_experiment import (
    FULL_TRAIN_MODE,
    FULL_TRAIN_MODE_V2,
    PRECHECK_MODE,
    PRECHECK_MODE_V4,
    SMOKE_MODE_V4,
    PRECHECK_MODE_V5,
    SMOKE_MODE_V5,
    PRECHECK_MODE_V6,
    SMOKE_MODE_V6,
    PRECHECK_MODE_V7,
    SMOKE_MODE_V7,
    PRECHECK_MODE_V8,
    SMOKE_MODE_V8,
    PRECHECK_MODE_V9,
    SMOKE_MODE_V9,
    FULL_TRAIN_MODE_V7,
    FULL_TRAIN_MODE_V8,
    PRECHECK_MODE_V10,
    SMOKE_MODE_V10,
    PRECHECK_MODE_V11,
    SMOKE_MODE_V11,
    FULL_TRAIN_MODE_V9,
    PRECHECK_MODE_V12,
    SMOKE_MODE_V12,
    FULL_TRAIN_MODE_V10,
    WorkpackExperiment,
    full_train_manifest,
    precheck_manifest,
    smoke_manifest,
    smoke_manifest_v9,
)


def test_workpack_precheck_is_frozen_serial_and_contains_two_consecutive_train_instances(tmp_path):
    bank = TaskBank()
    bank.load()
    manifest = precheck_manifest(bank)
    assert len(manifest) == 12
    assert [item['round'] for item in manifest] == [1] * 6 + [2] * 6
    assert all(item['workpackId'].endswith(('-01', '-02')) for item in manifest)
    by_workflow = {}
    for item in manifest:
        by_workflow.setdefault(item['workflowType'], []).append(item['workpackId'])
    assert all(rows[0].endswith('-01') and rows[1].endswith('-02') for rows in by_workflow.values())

    experiment = WorkpackExperiment(bank, Path(tmp_path))
    protocol = experiment.protocol(PRECHECK_MODE)
    assert protocol['agentRuns'] == 24
    assert protocol['limits'] == {'run': 1, 'model': 1, 'read': 1}
    assert protocol['id'] == 'workspace-workpack-online-precheck-v3'
    assert protocol['rsi'] == 'graph_rsi_empty_isolated_experience_train_only'
    assert protocol['judge'].startswith('not_run')


def test_workpack_full_train_manifest_is_frozen_train_only_and_round_robin(tmp_path):
    bank = TaskBank()
    bank.load()
    manifest = full_train_manifest(bank)
    assert len(manifest) == 48
    assert [item['round'] for item in manifest] == [1] * 12 + [2] * 12 + [3] * 12 + [4] * 12
    assert {item['scenario'] for item in manifest} == {'finance', 'support', 'tickets'}
    assert {item['workflowType'] for item in manifest}
    by_workflow = {}
    for item in manifest:
        by_workflow.setdefault(item['workflowType'], []).append(item)
    assert all([item['workpackId'][-2:] for item in rows] == ['01', '02', '03', '04'] for rows in by_workflow.values())

    experiment = WorkpackExperiment(bank, Path(tmp_path))
    protocol = experiment.protocol(FULL_TRAIN_MODE)
    assert protocol['mode'] == FULL_TRAIN_MODE
    assert protocol['taskCountPerArm'] == 48
    assert protocol['agentRuns'] == 96
    assert protocol['estimatedAgentTokens'] > 0
    assert protocol['limits'] == {'run': 1, 'model': 1, 'read': 1}


def test_workpack_v4_smoke_and_precheck_are_versioned_and_stage_gated(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))

    smoke = experiment.protocol(SMOKE_MODE_V4)
    assert smoke['id'] == 'workspace-workpack-online-smoke-v4'
    assert smoke['taskCountPerArm'] == 3
    assert [row['scenario'] for row in smoke_manifest(bank)] == ['finance', 'support', 'tickets']
    assert smoke['runtimeFingerprint']['digest']

    precheck = experiment.protocol(PRECHECK_MODE_V4)
    assert precheck['id'] == 'workspace-workpack-online-precheck-v4'
    assert precheck['taskCountPerArm'] == 12
    assert precheck['qualityGate']['blocksNextStage'] is True

    failed_item = {'protocol': {'taskCountPerArm': 3}}
    gate = WorkpackExperiment._quality_gate(failed_item, {
        'pairedCompleted': 3,
        'baseline': {'attempts': 3, 'passed': 3},
        'rsi': {'attempts': 3, 'passed': 2},
    })
    assert gate['status'] == 'failed'
    assert gate['sameQualityCostClaim'] is False
    assert '不能代表同质量经济性' in gate['reason']
    assert FULL_TRAIN_MODE_V2 in {'full_train_v2'}


def test_workpack_v5_runtime_starts_a_new_staged_line(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))

    smoke = experiment.protocol(SMOKE_MODE_V5)
    assert smoke['id'] == 'workspace-workpack-online-smoke-v5'
    assert smoke['taskCountPerArm'] == 3
    assert smoke['limits'] == {'run': 1, 'model': 1, 'read': 1}

    precheck = experiment.protocol(PRECHECK_MODE_V5)
    assert precheck['id'] == 'workspace-workpack-online-precheck-v5'
    assert precheck['qualityGate']['blocksNextStage'] is True


def test_workpack_v6_isolated_after_public_reference_time_repair(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))

    smoke = experiment.protocol(SMOKE_MODE_V6)
    assert smoke['id'] == 'workspace-workpack-online-smoke-v6'
    assert smoke['taskCountPerArm'] == 3
    assert smoke['limits'] == {'run': 1, 'model': 1, 'read': 1}

    precheck = experiment.protocol(PRECHECK_MODE_V6)
    assert precheck['id'] == 'workspace-workpack-online-precheck-v6'
    assert precheck['qualityGate']['blocksNextStage'] is True


def test_workpack_v7_isolated_after_public_scope_recovery_repair(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))

    smoke = experiment.protocol(SMOKE_MODE_V7)
    assert smoke['id'] == 'workspace-workpack-online-smoke-v7'
    assert smoke['taskCountPerArm'] == 3
    assert smoke['limits'] == {'run': 1, 'model': 1, 'read': 1}

    precheck = experiment.protocol(PRECHECK_MODE_V7)
    assert precheck['id'] == 'workspace-workpack-online-precheck-v7'
    assert precheck['taskCountPerArm'] == 12
    assert precheck['qualityGate']['blocksNextStage'] is True


def test_workpack_v8_isolated_after_shared_keyed_reconciliation_repair(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))

    smoke = experiment.protocol(SMOKE_MODE_V8)
    assert smoke['id'] == 'workspace-workpack-online-smoke-v8'
    assert smoke['taskCountPerArm'] == 3
    assert smoke['limits'] == {'run': 1, 'model': 1, 'read': 1}
    assert smoke['qualityGate']['blocksNextStage'] is True

    precheck = experiment.protocol(PRECHECK_MODE_V8)
    assert precheck['id'] == 'workspace-workpack-online-precheck-v8'
    assert precheck['taskCountPerArm'] == 12
    assert precheck['qualityGate']['blocksNextStage'] is True


def test_workpack_v9_isolated_after_shared_weighted_ratio_repair(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))

    smoke = experiment.protocol(SMOKE_MODE_V9)
    assert smoke['id'] == 'workspace-workpack-online-smoke-v9'
    assert smoke['taskCountPerArm'] == 3
    assert smoke['limits'] == {'run': 1, 'model': 1, 'read': 1}
    assert smoke['qualityGate']['blocksNextStage'] is True
    assert smoke_manifest_v9(bank)[0]['workflowType'] == 'finance-freight-contribution'

    precheck = experiment.protocol(PRECHECK_MODE_V9)
    assert precheck['id'] == 'workspace-workpack-online-precheck-v9'
    assert precheck['taskCountPerArm'] == 12
    assert precheck['qualityGate']['blocksNextStage'] is True

    full = experiment.protocol(FULL_TRAIN_MODE_V7)
    assert full['id'] == 'workspace-workpack-online-full-train-v7'
    assert full['taskCountPerArm'] == 48


def test_workpack_v10_requires_actual_weighted_ratio_smoke_coverage(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))
    smoke = experiment.protocol(SMOKE_MODE_V10)
    assert smoke['id'] == 'workspace-workpack-online-smoke-v10'
    assert smoke['manifest'][0]['workflowType'] == 'finance-freight-contribution'
    assert experiment.protocol(PRECHECK_MODE_V10)['id'] == 'workspace-workpack-online-precheck-v10'
    assert experiment.protocol(FULL_TRAIN_MODE_V8)['id'] == 'workspace-workpack-online-full-train-v8'


def test_workpack_v11_isolated_after_shared_ratio_publication_guard(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))
    assert experiment.protocol(SMOKE_MODE_V11)['id'] == 'workspace-workpack-online-smoke-v11'
    assert experiment.protocol(PRECHECK_MODE_V11)['id'] == 'workspace-workpack-online-precheck-v11'
    assert experiment.protocol(FULL_TRAIN_MODE_V9)['id'] == 'workspace-workpack-online-full-train-v9'


def test_workpack_v12_isolated_after_shared_duplicate_compute_guard(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))
    assert experiment.protocol(SMOKE_MODE_V12)['id'] == 'workspace-workpack-online-smoke-v12'
    assert experiment.protocol(PRECHECK_MODE_V12)['id'] == 'workspace-workpack-online-precheck-v12'
    assert experiment.protocol(FULL_TRAIN_MODE_V10)['id'] == 'workspace-workpack-online-full-train-v10'

    smoke = {
        'id': 'v12-smoke', 'mode': SMOKE_MODE_V12, 'status': 'completed', 'finishedAt': '2026-09-13T00:00:00Z',
        'protocol': {'taskCountPerArm': 3, 'runtimeFingerprint': experiment.protocol(SMOKE_MODE_V12)['runtimeFingerprint']},
        'coverage': {'weightedRatioReconcile': {'arms': ['baseline', 'rsi']}},
        'pairs': [
            {
                'index': index,
                'workpackId': f'finance-freight-contribution-{index:02d}',
                'workflowType': 'finance-freight-contribution',
                'scenario': 'finance',
                'round': 1,
                'runs': {
                    arm: {
                        'status': 'completed',
                        'evaluation': {'status': 'passed'},
                        'metrics': {'inputTokens': 1, 'outputTokens': 1},
                    }
                    for arm in ['baseline', 'rsi']
                },
            }
            for index in range(1, 4)
        ],
    }
    experiment.items[smoke['id']] = smoke
    assert experiment._eligible_predecessor(PRECHECK_MODE_V12, smoke['protocol']['runtimeFingerprint'])['id'] == smoke['id']


async def test_cancelled_workpack_experiment_does_not_start_next_arm_or_pair(tmp_path, monkeypatch):
    import backend.workpack_experiment as module

    first_started = asyncio.Event()
    started = []

    class FakeEvolution:
        versions = []
        workflows = []
        tiny_edges = []

    class FakeRunner:
        def __init__(self, *_args, **_kwargs):
            self.evolution = FakeEvolution()
            self.tasks = {}

        async def start(self, request):
            run = {
                'id': str(uuid4()), 'taskId': request.taskId, 'scenario': 'finance', 'split': 'train',
                'strategy': request.strategy, 'status': 'queued', 'phase': 'queued', 'createdAt': 'now',
                'models': {'executor': 'fake'}, 'modelSettings': {},
                'metrics': {'inputTokens': 0, 'outputTokens': 0, 'modelRequests': 0, 'toolCalls': 0, 'durationMs': 0, 'runtimeOverheadMs': 0},
                'evaluation': {'status': 'failed'}, 'evolution': {}, 'runtimeOverhead': {}, 'events': [],
            }

            async def complete():
                started.append(request.taskId)
                first_started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    run.update(status='cancelled', phase='cancelled')

            self.tasks[run['id']] = asyncio.create_task(complete())
            return run

        async def shutdown(self):
            for task in self.tasks.values():
                task.cancel()
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)

    manifest = [
        {'workpackId': 'first', 'scenario': 'finance', 'workflowType': 'finance-reconciliation', 'sourceTaskId': 'one', 'recordCount': 1, 'difficulty': 'A', 'round': 1},
        {'workpackId': 'second', 'scenario': 'finance', 'workflowType': 'finance-reconciliation', 'sourceTaskId': 'two', 'recordCount': 1, 'difficulty': 'A', 'round': 2},
    ]

    monkeypatch.setattr(module, 'TaskRunner', FakeRunner)
    monkeypatch.setattr(module, 'smoke_manifest', lambda _bank: manifest)
    monkeypatch.setattr(WorkpackExperiment, '_runtime_fingerprint', lambda _self: {'files': {}, 'digest': 'test-runtime'})
    monkeypatch.setattr(module, 'install_workpack', lambda _manager, _bank, pack_id: ({'id': 'workspace-' + pack_id}, {'id': 'task-' + pack_id}))
    experiment = WorkpackExperiment(object(), Path(tmp_path))
    item = await experiment.start(SMOKE_MODE_V4)
    controller = experiment.tasks[item['id']]
    await asyncio.wait_for(first_started.wait(), timeout=1)

    assert experiment.cancel(item['id']) is True
    await asyncio.wait_for(controller, timeout=1)
    saved = experiment.get(item['id'])
    assert saved['status'] == 'cancelled'
    assert saved['cancelRequested'] is True
    assert started == ['task-first']
    assert saved['pairs'][0]['status'] == 'cancelled'
    assert saved['pairs'][1]['status'] == 'pending'
