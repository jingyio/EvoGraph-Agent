import asyncio
import json
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
    PRECHECK_MODE_V13,
    SMOKE_MODE_V13,
    FULL_TRAIN_MODE_V11,
    PRECHECK_MODE_V14,
    SMOKE_MODE_V14,
    FULL_TRAIN_MODE_V12,
    FULL_TRAIN_MODE_V13,
    FULL_TRAIN_MODE_V14,
    PRECHECK_MODE_V16,
    SMOKE_MODE_V16,
    FULL_TRAIN_MODE_V15,
    PRECHECK_MODE_V17,
    SMOKE_MODE_V17,
    WorkpackExperiment,
    full_train_manifest,
    precheck_manifest,
    smoke_manifest,
    smoke_manifest_v9,
    smoke_manifest_v16,
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


def test_workpack_v13_starts_a_new_staged_line_and_fingerprints_model_transport(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))
    protocol = experiment.protocol(SMOKE_MODE_V13)
    assert protocol['id'] == 'workspace-workpack-online-smoke-v13'
    assert 'backend/model_client.py' in protocol['runtimeFingerprint']['files']
    assert PRECHECK_MODE_V13 in experiment.protocol(PRECHECK_MODE_V13)['mode']
    assert FULL_TRAIN_MODE_V11 in experiment.protocol(FULL_TRAIN_MODE_V11)['mode']


def test_workpack_v14_starts_a_new_staged_line_and_fingerprints_prompt_guidance(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))
    protocol = experiment.protocol(SMOKE_MODE_V14)
    assert protocol['id'] == 'workspace-workpack-online-smoke-v14'
    assert 'backend/agent_prompts.py' in protocol['runtimeFingerprint']['files']
    assert experiment.protocol(PRECHECK_MODE_V14)['mode'] == PRECHECK_MODE_V14
    assert experiment.protocol(FULL_TRAIN_MODE_V12)['mode'] == FULL_TRAIN_MODE_V12


def test_workpack_v16_keeps_declared_fact_recovery_observational_before_precheck(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))
    protocol = experiment.protocol(SMOKE_MODE_V16)

    assert protocol['id'] == 'workspace-workpack-online-smoke-v16'
    assert protocol['taskCountPerArm'] == 4
    assert [item['workflowType'] for item in smoke_manifest_v16(bank)] == [
        'finance-freight-contribution', 'support-policy-draft',
        'support-period-comparison', 'tickets-triage',
    ]
    assert 'never_forced_by_a_synthetic_failure' in protocol['requiredSmokeCoverage']
    assert experiment.protocol(PRECHECK_MODE_V16)['taskCountPerArm'] == 12
    assert experiment.protocol(FULL_TRAIN_MODE_V14)['taskCountPerArm'] == 48

    def successful_pair(index, workflow):
        return {
            'index': index, 'status': 'completed', 'workpackId': workflow + '-01',
            'workflowType': workflow, 'scenario': 'support' if workflow.startswith('support-') else 'finance', 'round': 1,
            'runs': {arm: {
                'status': 'completed', 'evaluation': {'status': 'passed'},
                'metrics': {'inputTokens': 1, 'outputTokens': 1, 'usageComplete': True},
            } for arm in ['baseline', 'rsi']},
        }

    smoke = {
        'id': 'v16-smoke', 'mode': SMOKE_MODE_V16, 'status': 'completed', 'finishedAt': '2026-09-13T00:00:00Z',
        'protocol': {'taskCountPerArm': 4, 'runtimeFingerprint': protocol['runtimeFingerprint']},
        'pairs': [
            successful_pair(1, 'finance-freight-contribution'),
            successful_pair(2, 'support-policy-draft'),
            successful_pair(3, 'support-period-comparison'),
            successful_pair(4, 'tickets-triage'),
        ],
        'coverage': {
            'weightedRatioReconcile': {'arms': ['baseline', 'rsi']},
            'deterministicFactRecovery': {
                'workspace_aggregate_rows': {'arms': ['baseline']},
                'workspace_ordered_partition': {'arms': ['baseline', 'rsi']},
            },
        },
    }
    experiment.items[smoke['id']] = smoke
    assert experiment._eligible_predecessor(PRECHECK_MODE_V16, protocol['runtimeFingerprint'])['id'] == smoke['id']


def test_workpack_v17_isolated_after_shared_deadline_finalization_guard(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))

    protocol = experiment.protocol(SMOKE_MODE_V17)
    assert protocol['id'] == 'workspace-workpack-online-smoke-v17'
    assert protocol['taskCountPerArm'] == 4
    assert experiment.protocol(PRECHECK_MODE_V17)['taskCountPerArm'] == 12
    assert experiment.protocol(FULL_TRAIN_MODE_V15)['taskCountPerArm'] == 48
    assert protocol['runtimeFingerprint']['files']['backend/task_runner.py']


def test_runtime_compatibility_allows_summary_only_controller_repair_but_rejects_agent_runtime_change(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))
    current = experiment._runtime_fingerprint()

    prior_files = dict(current['files'])
    prior_files['backend/workpack_experiment.py'] = 'old-controller-summary-only-hash'
    prior = {'files': prior_files, 'digest': 'old-full-fingerprint'}

    assert WorkpackExperiment._runtime_matches(prior, current) is True

    changed_files = dict(prior_files)
    changed_files['backend/task_runner.py'] = 'changed-agent-runtime-hash'
    assert WorkpackExperiment._runtime_matches({'files': changed_files, 'digest': 'another-old-fingerprint'}, current) is False
    assert experiment.protocol(FULL_TRAIN_MODE_V13)['runtimeFingerprint']['controllerBehaviorVersion'] == 1


def test_workpack_dashboard_dtos_keep_v17_kpis_and_exclude_raw_traces_and_reports(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))
    item = {
        'id': 'v17-dashboard', 'mode': FULL_TRAIN_MODE_V15, 'status': 'completed',
        'createdAt': '2026-09-13T00:00:00Z', 'finishedAt': '2026-09-13T01:00:00Z',
        'protocol': {
            'id': 'workspace-workpack-online-full-train-v15', 'mode': FULL_TRAIN_MODE_V15,
            'taskCountPerArm': 1, 'agentRuns': 2, 'limits': {'run': 1, 'model': 1, 'read': 1},
            'manifest': [{'workpackId': 'finance-reconciliation-01', 'scenario': 'finance',
                          'workflowType': 'finance-reconciliation', 'recordCount': 10,
                          'difficulty': 'normal', 'round': 1}],
            'saturationRule': {'window': 4},
            'runtimeFingerprint': {'files': {'backend/task_runner.py': 'private-hash'}},
        },
        'pairs': [{
            'index': 1, 'workpackId': 'finance-reconciliation-01', 'scenario': 'finance',
            'workflowType': 'finance-reconciliation', 'sourceTaskId': 'finance-task-01',
            'recordCount': 10, 'difficulty': 'normal', 'round': 1, 'status': 'completed',
            'runs': {
                'baseline': {
                    'id': 'baseline-run', 'status': 'completed', 'strategy': 'plan_react',
                    'metrics': {'inputTokens': 100, 'outputTokens': 20, 'durationMs': 50,
                                'modelRequests': 2, 'toolCalls': 3, 'usageComplete': True,
                                'reportAttempts': 1},
                    'evaluation': {'status': 'passed'}, 'submission': {'summary': 'private report body'},
                    'events': [{'private': 'raw model trace'}], 'graph': {'nodes': ['private graph']},
                    'plan': {'steps': ['private plan']},
                    'phaseMetrics': {'plan': {'private': 'raw plan metric'}, 'graph': {'private': 'raw graph metric'}},
                },
                'rsi': {
                    'id': 'rsi-run', 'status': 'completed', 'strategy': 'graph_rsi',
                    'metrics': {'inputTokens': 70, 'outputTokens': 10, 'durationMs': 40,
                                'modelRequests': 1, 'toolCalls': 2, 'usageComplete': True,
                                'reportAttempts': 1},
                    'evaluation': {'status': 'passed'},
                    'evolution': {'planningPath': 'fast', 'usedVersionId': 'workflow-1'},
                    'submission': {'summary': 'private RSI report body'},
                    'events': [{'private': 'raw tool trace'}], 'graph': {'nodes': ['private graph']},
                    'modelPlan': {'steps': ['private model plan']},
                    'phaseMetrics': {'plan': {'private': 'raw plan metric'}, 'graph': {'private': 'raw graph metric'}},
                },
            },
            'snapshots': [{
                'id': 'snapshot-1', 'kind': 'before', 'arm': 'rsi', 'pairIndex': 1,
                'workpackId': 'finance-reconciliation-01',
                'versions': [{'id': 'workflow-1', 'sourceTaskId': 'finance-task-00'}],
                'workflows': [], 'tinyEdges': [],
            }],
        }],
    }
    item['summary'] = experiment._summary(item)
    experiment.items[item['id']] = item

    rows = experiment.list_summaries()
    assert rows == [{
        'id': 'v17-dashboard', 'mode': FULL_TRAIN_MODE_V15, 'status': 'completed',
        'createdAt': '2026-09-13T00:00:00Z', 'startedAt': None,
        'finishedAt': '2026-09-13T01:00:00Z', 'error': None,
        'protocol': {'id': 'workspace-workpack-online-full-train-v15', 'mode': FULL_TRAIN_MODE_V15,
                     'taskCountPerArm': 1, 'agentRuns': 2, 'limits': {'run': 1, 'model': 1, 'read': 1},
                     'model': None},
        'summary': {
            'pairedCompleted': 1, 'tokenSavingRate': 0.333333,
            'learning': {'workflowCreated': 0, 'fastReuse': 1, 'composition': 0, 'fallback': 0},
            'qualityGate': item['summary']['qualityGate'],
        },
    }]

    dashboard = experiment.dashboard(item['id'])
    assert dashboard['summary']['baseline']['totalTokens'] == 120
    assert dashboard['summary']['rsi']['totalTokens'] == 80
    assert dashboard['pairs'][0]['runs']['rsi']['id'] == 'rsi-run'
    assert dashboard['pairs'][0]['snapshots'][0]['versions'][0]['sourceTaskId'] == 'finance-task-00'
    payload = json.dumps(dashboard, ensure_ascii=False)
    for forbidden in ['private report body', 'raw model trace', 'raw tool trace', 'private graph',
                      'private plan', 'private model plan', 'runtimeFingerprint']:
        assert forbidden not in payload


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


def test_workpack_summary_excludes_cancelled_pair_from_paired_curve_but_keeps_arm_attempts():
    def run(tokens: int) -> dict:
        return {
            'status': 'completed',
            'evaluation': {'status': 'passed'},
            'metrics': {'inputTokens': tokens, 'outputTokens': 0, 'usageComplete': True},
            'evolution': {},
        }

    item = {
        'protocol': {'taskCountPerArm': 2},
        'pairs': [
            {
                'index': 1, 'status': 'completed', 'workpackId': 'completed',
                'workflowType': 'finance-reconciliation', 'scenario': 'finance', 'round': 1,
                'runs': {'baseline': run(10), 'rsi': run(5)},
            },
            {
                'index': 2, 'status': 'cancelled', 'workpackId': 'cancelled',
                'workflowType': 'finance-reconciliation', 'scenario': 'finance', 'round': 1,
                'runs': {'baseline': run(100), 'rsi': run(50)},
            },
        ],
    }

    summary = WorkpackExperiment._summary(item)

    assert summary['baseline']['attempts'] == 2
    assert summary['rsi']['attempts'] == 2
    assert summary['pairedCompleted'] == 1
    assert [point['workpackId'] for point in summary['curve']] == ['completed']
    assert summary['tokenSavingRate'] == 0.5


def test_workpack_showcase_comparison_returns_only_a_completed_quality_gated_v17_pair(tmp_path):
    bank = TaskBank()
    bank.load()
    experiment = WorkpackExperiment(bank, Path(tmp_path))

    def run(run_id: str, strategy: str, tokens: int, planning_path=None) -> dict:
        return {
            'id': run_id, 'status': 'completed', 'strategy': strategy,
            'evaluation': {'status': 'passed'},
            'metrics': {'inputTokens': tokens, 'outputTokens': 0, 'modelRequests': 2,
                        'toolCalls': 3, 'durationMs': 1000, 'usageComplete': True},
            'evolution': {'planningPath': planning_path} if planning_path else {},
        }

    pair = {
        'index': 1, 'status': 'completed', 'workpackId': 'finance-reconciliation-01',
        'workflowType': 'finance-reconciliation', 'scenario': 'finance', 'round': 1,
        'difficulty': 'A', 'recordCount': 10, 'sourceTaskId': 'finance-reconciliation-01',
        'runs': {
            'baseline': run('baseline-run', 'plan_react', 120),
            'rsi': run('rsi-run', 'graph_rsi', 80, 'fast'),
        },
        'snapshots': [],
    }
    item = {
        'id': 'saved-v17', 'mode': FULL_TRAIN_MODE_V15, 'status': 'completed',
        'createdAt': '2026-09-14T00:00:00Z', 'finishedAt': '2026-09-14T00:01:00Z',
        'protocol': {'taskCountPerArm': 1, 'limits': {'run': 1, 'model': 1, 'read': 1}},
        'pairs': [pair],
    }
    item['summary'] = WorkpackExperiment._summary(item)
    experiment.items[item['id']] = item

    saved = experiment.showcase_comparison('finance-reconciliation-01')

    assert saved['available'] is True
    assert saved['experiment']['id'] == 'saved-v17'
    assert saved['pair']['runs']['baseline']['id'] == 'baseline-run'
    assert saved['pair']['runs']['rsi']['evolution']['planningPath'] == 'fast'
    assert saved['comparison']['tokenSavingRate'] == 0.333333
    assert saved['workpack']['deliveryContract']['requiredSources'] == ['orders.csv', 'payments.json', 'items.csv']

    missing = experiment.showcase_comparison('finance-reconciliation-05')
    assert missing['available'] is False
    assert '不会自动发起' in missing['reason']
