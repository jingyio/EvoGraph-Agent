"""Isolated serial online experiments over the workspace workpack entry path.

The controller deliberately materializes every fixed task through
``install_workpack``.  It therefore exercises the same source parser,
workspace task protocol, tools, TaskRunner, report evaluator and trace format
as an uploaded work request; it does not have a benchmark-only executor.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from uuid import uuid4

from .domain import now
from .graph_store import write_private
from .task_runner import TaskRunner, TaskRunRequest
from .workpacks import install_workpack, list_workpacks
from .workspace import WorkspaceBank, WorkspaceManager


PRECHECK_WORKFLOWS = (
    'finance-reconciliation', 'finance-cancel-installments',
    'support-health-rollup', 'support-escalation-queue',
    'tickets-triage', 'tickets-blocker-summary',
)

PRECHECK_WORKFLOWS_V16 = (
    'finance-freight-contribution', 'finance-cancel-installments',
    'support-policy-draft', 'support-period-comparison',
    'tickets-triage', 'tickets-blocker-summary',
)

ALL_TRAIN_WORKFLOWS = (
    'finance-reconciliation', 'finance-cancel-installments',
    'finance-freight-contribution', 'finance-link-completeness',
    'support-health-rollup', 'support-escalation-queue',
    'support-policy-draft', 'support-period-comparison',
    'tickets-triage', 'tickets-blocker-summary',
    'tickets-activity-followup', 'tickets-export-comparison',
)

# V3/V1 remain readable historical artifacts.  New experiments start at V4
# because public delivery contracts and bounded business-fact recovery changed
# the runtime behaviour.  Mixing results across this boundary would invalidate
# a same-quality cost claim.
PRECHECK_MODE = 'precheck_v3'
FULL_TRAIN_MODE = 'full_train_v1'
SMOKE_MODE_V4 = 'smoke_v4'
PRECHECK_MODE_V4 = 'precheck_v4'
FULL_TRAIN_MODE_V2 = 'full_train_v2'
# V5 starts after the V4 smoke exposed a shared Plan + ReAct long tail.  It
# cannot reuse V4 because optional-plan normalization and observed-scope
# context handling change both arms' runtime behaviour.
SMOKE_MODE_V5 = 'smoke_v5'
PRECHECK_MODE_V5 = 'precheck_v5'
FULL_TRAIN_MODE_V3 = 'full_train_v3'
# V6 follows a V5 quality-gate failure caused by an ambiguous public temporal
# rule in ticket workpacks.  The source-derived reference time is now exposed
# to both arms, so V5 artifacts remain immutable diagnostics and cannot be
# mixed with this repaired runtime.
SMOKE_MODE_V6 = 'smoke_v6'
PRECHECK_MODE_V6 = 'precheck_v6'
FULL_TRAIN_MODE_V4 = 'full_train_v4'
# V7 follows a V6 quality-gate failure: the public workpack contract named
# source files but did not give the shared runtime a public way to finish the
# declared table scope after an evidence-only report failure.  V7 adds only
# deterministic table-slot recovery for both arms; it does not reveal private
# validation rows or alter an already-selected business conclusion.
SMOKE_MODE_V7 = 'smoke_v7'
PRECHECK_MODE_V7 = 'precheck_v7'
FULL_TRAIN_MODE_V5 = 'full_train_v5'
# V8 adds a shared deterministic keyed reconciliation compute tool after V7
# showed that correct raw observations can still be misreported by model
# arithmetic. It changes both arms, so it starts a separate staged line.
SMOKE_MODE_V8 = 'smoke_v8'
PRECHECK_MODE_V8 = 'precheck_v8'
FULL_TRAIN_MODE_V6 = 'full_train_v6'
# V9 extends V8's shared keyed reconciliation tool with explicit weighted
# comparison terms. This is necessary for public ratio rules such as
# ``freight >= 0.2 * price``; it changes both arms and starts a new line.
SMOKE_MODE_V9 = 'smoke_v9'
PRECHECK_MODE_V9 = 'precheck_v9'
FULL_TRAIN_MODE_V7 = 'full_train_v7'
# V10 keeps V9's generic weighted comparison but improves only its shared
# tool ergonomics and execution guidance. V9 artifacts remain immutable:
# Baseline bypassed the new tool and repeated a wrong manual comparison.
SMOKE_MODE_V10 = 'smoke_v10'
PRECHECK_MODE_V10 = 'precheck_v10'
FULL_TRAIN_MODE_V8 = 'full_train_v8'
# V11 adds a shared, task-generic publication guard for public percentage or
# ratio conditions. It requires a successful weighted reconciliation before a
# report may be submitted, so V10 cannot be reused after this runtime change.
SMOKE_MODE_V11 = 'smoke_v11'
PRECHECK_MODE_V11 = 'precheck_v11'
FULL_TRAIN_MODE_V9 = 'full_train_v9'
# V12 closes a shared no-progress recovery gap exposed by V11: a model could
# repeat an identical successful deterministic compute call until its request
# budget expired. The guard applies to both arms and therefore requires a new
# staged line rather than reusing V11 as a strict comparison.
SMOKE_MODE_V12 = 'smoke_v12'
PRECHECK_MODE_V12 = 'precheck_v12'
FULL_TRAIN_MODE_V10 = 'full_train_v10'
# V13 fixes a shared one-to-many reconciliation anchor defect and records a
# single retry for transient model transport failures. Both affect correctness
# and cost accounting for both arms, so V12 artifacts remain immutable.
SMOKE_MODE_V13 = 'smoke_v13'
PRECHECK_MODE_V13 = 'precheck_v13'
FULL_TRAIN_MODE_V11 = 'full_train_v11'
# V14 rejects ambiguous grouped row counts after V13 smoke found one arm
# treating count(groupBy=...) as a distinct-group result. This is shared
# semantics and prompt guidance, so it starts a new staged line.
SMOKE_MODE_V14 = 'smoke_v14'
PRECHECK_MODE_V14 = 'precheck_v14'
FULL_TRAIN_MODE_V12 = 'full_train_v12'
# V15 adds deterministic totals for the keys selected by a reconciliation
# comparison, avoiding a second model-side sum over already-reconciled rows.
SMOKE_MODE_V15 = 'smoke_v15'
PRECHECK_MODE_V15 = 'precheck_v15'
FULL_TRAIN_MODE_V13 = 'full_train_v13'
# V16 adds two shared, publicly declared fact-recovery computes after the V15
# retry exposed model-side nonempty-count and odd-row partition failures. The
# tools operate only on current workspace data and both arms receive them, so
# all later comparisons start from a separate staged runtime line.
SMOKE_MODE_V16 = 'smoke_v16'
PRECHECK_MODE_V16 = 'precheck_v16'
FULL_TRAIN_MODE_V14 = 'full_train_v14'
# V17 follows V16's Baseline deadline exhaustion: complete public scope could
# still be followed by a non-terminal draft tool call, leaving no provider turn
# for the required report. The shared finalization guard changes both arms, so
# V16 artifacts remain diagnostics and V17 starts from a fresh smoke stage.
SMOKE_MODE_V17 = 'smoke_v17'
PRECHECK_MODE_V17 = 'precheck_v17'
FULL_TRAIN_MODE_V15 = 'full_train_v15'
EXPERIMENT_MODES = {PRECHECK_MODE, FULL_TRAIN_MODE, SMOKE_MODE_V4, PRECHECK_MODE_V4, FULL_TRAIN_MODE_V2,
                    SMOKE_MODE_V5, PRECHECK_MODE_V5, FULL_TRAIN_MODE_V3,
                    SMOKE_MODE_V6, PRECHECK_MODE_V6, FULL_TRAIN_MODE_V4,
                    SMOKE_MODE_V7, PRECHECK_MODE_V7, FULL_TRAIN_MODE_V5,
                    SMOKE_MODE_V8, PRECHECK_MODE_V8, FULL_TRAIN_MODE_V6,
                    SMOKE_MODE_V9, PRECHECK_MODE_V9, FULL_TRAIN_MODE_V7,
                    SMOKE_MODE_V10, PRECHECK_MODE_V10, FULL_TRAIN_MODE_V8,
                    SMOKE_MODE_V11, PRECHECK_MODE_V11, FULL_TRAIN_MODE_V9,
                    SMOKE_MODE_V12, PRECHECK_MODE_V12, FULL_TRAIN_MODE_V10,
                    SMOKE_MODE_V13, PRECHECK_MODE_V13, FULL_TRAIN_MODE_V11,
                    SMOKE_MODE_V14, PRECHECK_MODE_V14, FULL_TRAIN_MODE_V12,
                    SMOKE_MODE_V15, PRECHECK_MODE_V15, FULL_TRAIN_MODE_V13,
                    SMOKE_MODE_V16, PRECHECK_MODE_V16, FULL_TRAIN_MODE_V14,
                    SMOKE_MODE_V17, PRECHECK_MODE_V17, FULL_TRAIN_MODE_V15}
STARTABLE_MODES = {SMOKE_MODE_V4, PRECHECK_MODE_V4, FULL_TRAIN_MODE_V2,
                   SMOKE_MODE_V5, PRECHECK_MODE_V5, FULL_TRAIN_MODE_V3,
                   SMOKE_MODE_V6, PRECHECK_MODE_V6, FULL_TRAIN_MODE_V4,
                   SMOKE_MODE_V7, PRECHECK_MODE_V7, FULL_TRAIN_MODE_V5,
                   SMOKE_MODE_V8, PRECHECK_MODE_V8, FULL_TRAIN_MODE_V6,
                   SMOKE_MODE_V9, PRECHECK_MODE_V9, FULL_TRAIN_MODE_V7,
                   SMOKE_MODE_V10, PRECHECK_MODE_V10, FULL_TRAIN_MODE_V8,
                   SMOKE_MODE_V11, PRECHECK_MODE_V11, FULL_TRAIN_MODE_V9,
                   SMOKE_MODE_V12, PRECHECK_MODE_V12, FULL_TRAIN_MODE_V10,
                   SMOKE_MODE_V13, PRECHECK_MODE_V13, FULL_TRAIN_MODE_V11,
                   SMOKE_MODE_V14, PRECHECK_MODE_V14, FULL_TRAIN_MODE_V12,
                   SMOKE_MODE_V15, PRECHECK_MODE_V15, FULL_TRAIN_MODE_V13,
                   SMOKE_MODE_V16, PRECHECK_MODE_V16, FULL_TRAIN_MODE_V14,
                   SMOKE_MODE_V17, PRECHECK_MODE_V17, FULL_TRAIN_MODE_V15}

RUNTIME_SOURCE_FILES = (
    'backend/agent_prompts.py',
    'backend/model_client.py',
    'backend/task_runner.py',
    'backend/workspace.py',
    'backend/workpacks.py',
    'backend/workpack_experiment.py',
    'backend/gagent.py',
    'backend/intent_graph.py',
    'backend/online_evolution.py',
)
# The controller persists/checkpoints experiments, while the remaining files
# determine an Agent arm's planning, execution, tools and learning behavior.
# Bump this only when controller changes alter the frozen manifest, arm order,
# limits, cancellation semantics, or task/experience isolation. Dashboard-only
# summary changes must not invalidate a completed staged predecessor.
EXPERIMENT_CONTROLLER_FILE = 'backend/workpack_experiment.py'
EXPERIMENT_CONTROLLER_BEHAVIOR_VERSION = 1


class ExperimentCancelled(Exception):
    """A persisted cancellation observed between serial experiment units."""


def _total(metrics: dict | None) -> int:
    metrics = metrics or {}
    return int(metrics.get('inputTokens') or 0) + int(metrics.get('outputTokens') or 0)


def _percentile(values: list[float], percent: float) -> float | None:
    """Nearest-rank percentile for a saved finite sample."""
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * percent) - 1)], 3)


def _failure_category(run: dict) -> list[str]:
    """Classify saved terminal outcomes without changing their original status."""
    categories = []
    error = str(run.get('error') or '')
    if '时限' in error or 'timeout' in error.lower():
        categories.append('timeout')
    elif error:
        categories.append('runtime_error')
    evaluation = run.get('evaluation') or {}
    for issue in evaluation.get('issues') or []:
        categories.append(f'evaluation:{issue}')
    if not _has_submission(run) and 'evaluation:missing_report' not in categories:
        categories.append('missing_report')
    return categories


def _counter(rows: list[str]) -> dict[str, int]:
    values: dict[str, int] = {}
    for row in rows:
        values[row] = values.get(row, 0) + 1
    return dict(sorted(values.items()))


def _compact(run: dict) -> dict:
    """Keep the experiment ledger small; raw replay stays in the run file.

    Workpack experiments write a complete TaskRunner record per arm under the
    arm-specific ``runs`` directory.  The controller only needs a stable
    accounting projection for summaries, quality gates, and run links.  Do
    not duplicate traces, plans, graphs, or report content into
    ``experiment.json``: a completed 48-pair experiment otherwise becomes a
    multi-megabyte list payload before the dashboard can render.
    """
    return {key: deepcopy(run.get(key)) for key in [
        'id', 'taskId', 'scenario', 'split', 'strategy', 'status', 'phase',
        'createdAt', 'startedAt', 'finishedAt', 'models', 'metrics',
        'evaluation', 'evolution', 'runtimeOverhead', 'error',
    ]}


def _has_submission(run: dict) -> bool:
    """Read compact and pre-compaction ledger records without rewriting history."""
    return bool(run.get('hasSubmission') or run.get('submission'))


def _dashboard_run(run: dict | None) -> dict | None:
    """Return a trace-free run projection for the experiment dashboard."""
    if not run:
        return None
    evolution = run.get('evolution') or {}
    return {
        key: deepcopy(run.get(key)) for key in [
            'id', 'taskId', 'scenario', 'split', 'strategy', 'status', 'phase',
            'createdAt', 'startedAt', 'finishedAt', 'models', 'metrics',
            'evaluation', 'runtimeOverhead', 'error',
        ]
    } | {
        'evolution': {
            key: deepcopy(evolution.get(key)) for key in [
                'usedVersionId', 'sourceGraphId', 'generation', 'planningPath',
                'note', 'generatedVersionIds', 'tinyEdgeMaintenance',
            ]
        } if evolution else {},
    }


def _frozen_manifest(bank, *, workflows: tuple[str, ...], positions: tuple[int, ...], label: str) -> list[dict]:
    """Freeze train-only workpacks in a round-robin workflow order."""
    rows = {item['id']: item for item in list_workpacks(bank)}
    selected = []
    for position in positions:
        for workflow_id in workflows:
            row = rows.get(f'{workflow_id}-{position:02d}')
            if not row or row.get('split') != 'train':
                raise ValueError(f'{label}缺少连续 train 实例：' + workflow_id)
            selected.append({
                'workpackId': row['id'],
                'scenario': row['scenario'],
                'workflowType': row['workflowType'],
                'sourceTaskId': row['sourceTaskId'],
                'recordCount': row['recordCount'],
                'difficulty': row['difficulty'],
                'round': position,
            })
    return selected


def precheck_manifest(bank) -> list[dict]:
    """Freeze two naturally consecutive train instances for six workflows."""
    return _frozen_manifest(
        bank,
        workflows=PRECHECK_WORKFLOWS,
        positions=(1, 2),
        label='冻结工作包预检',
    )


def smoke_manifest(bank) -> list[dict]:
    """Freeze one complete, representative workpack per public scenario."""
    rows = {item['id']: item for item in list_workpacks(bank)}
    selected = []
    for workflow_id in ('finance-reconciliation', 'support-health-rollup', 'tickets-triage'):
        row = rows.get(f'{workflow_id}-01')
        if not row or row.get('split') != 'train':
            raise ValueError('三场景 smoke 缺少冻结 train 工作包：' + workflow_id)
        selected.append({
            'workpackId': row['id'],
            'scenario': row['scenario'],
            'workflowType': row['workflowType'],
            'sourceTaskId': row['sourceTaskId'],
            'recordCount': row['recordCount'],
            'difficulty': row['difficulty'],
            'round': 1,
        })
    return selected


def smoke_manifest_v9(bank) -> list[dict]:
    """Freeze one ratio-rule task plus one task from each other scenario.

    V9 exists specifically because the old arithmetic-only reconciliation
    interface could not express this public ratio condition.  The smoke must
    exercise that capability in a real Agent trace, rather than inheriting a
    generic finance reconciliation sample that cannot prove it.
    """
    rows = {item['id']: item for item in list_workpacks(bank)}
    selected = []
    for workflow_id in ('finance-freight-contribution', 'support-health-rollup', 'tickets-triage'):
        row = rows.get(f'{workflow_id}-01')
        if not row or row.get('split') != 'train':
            raise ValueError('V9 三场景 smoke 缺少冻结 train 工作包：' + workflow_id)
        selected.append({
            'workpackId': row['id'],
            'scenario': row['scenario'],
            'workflowType': row['workflowType'],
            'sourceTaskId': row['sourceTaskId'],
            'recordCount': row['recordCount'],
            'difficulty': row['difficulty'],
            'round': 1,
        })
    return selected


def smoke_manifest_v16(bank) -> list[dict]:
    """Exercise both public fact-recovery capabilities in real arm traces."""
    rows = {item['id']: item for item in list_workpacks(bank)}
    selected = []
    for workflow_id in (
        'finance-freight-contribution',
        'support-policy-draft',
        'support-period-comparison',
        'tickets-triage',
    ):
        row = rows.get(f'{workflow_id}-01')
        if not row or row.get('split') != 'train':
            raise ValueError('V16 smoke 缺少冻结 train 工作包：' + workflow_id)
        selected.append({
            'workpackId': row['id'], 'scenario': row['scenario'], 'workflowType': row['workflowType'],
            'sourceTaskId': row['sourceTaskId'], 'recordCount': row['recordCount'],
            'difficulty': row['difficulty'], 'round': 1,
        })
    return selected


def precheck_manifest_v16(bank) -> list[dict]:
    """Keep consecutive family reuse while including both repaired support flows."""
    return _frozen_manifest(
        bank,
        workflows=PRECHECK_WORKFLOWS_V16,
        positions=(1, 2),
        label='V16 冻结工作包预检',
    )


def full_train_manifest(bank) -> list[dict]:
    """Freeze all four train instances for every source-traceable workflow."""
    return _frozen_manifest(
        bank,
        workflows=ALL_TRAIN_WORKFLOWS,
        positions=(1, 2, 3, 4),
        label='冻结工作包正式 train 流',
    )


class WorkpackExperiment:
    """Runs a frozen serial Baseline/RSI comparison with independent stores."""

    def __init__(self, bank, root: Path, provider_factory=None):
        self.bank = bank
        self.root = Path(root) / 'artifacts' / 'workpack-experiments'
        self.provider_factory = provider_factory
        self.items: dict[str, dict] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.runners: dict[str, dict[str, TaskRunner]] = {}
        self.active_runs: dict[str, tuple[TaskRunner, str]] = {}

    def _path(self, key: str) -> Path:
        return self.root / key / 'experiment.json'

    def _save(self, item: dict) -> None:
        write_private(self._path(item['id']), item)

    def _runtime_fingerprint(self) -> dict:
        """Persist an auditable source snapshot without copying user artifacts.

        The current worktree can be uncommitted during an experiment.  Per-file
        SHA-256 values make that explicit and allow the V4 precheck gate to
        reject a later full run after a relevant runtime change.
        """
        files = {}
        for relative in RUNTIME_SOURCE_FILES:
            path = Path(self.bank.root) / relative
            if not path.exists():
                raise ValueError('运行时源文件缺失：' + relative)
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        serialized = json.dumps(files, sort_keys=True, ensure_ascii=True).encode('utf-8')
        execution_files = {key: value for key, value in files.items() if key != EXPERIMENT_CONTROLLER_FILE}
        execution_serialized = json.dumps(execution_files, sort_keys=True, ensure_ascii=True).encode('utf-8')
        return {
            'files': files,
            'digest': hashlib.sha256(serialized).hexdigest(),
            'executionDigest': hashlib.sha256(execution_serialized).hexdigest(),
            'controllerBehaviorVersion': EXPERIMENT_CONTROLLER_BEHAVIOR_VERSION,
        }

    @staticmethod
    def _runtime_matches(prior: dict, current: dict) -> bool:
        """Allow a summary-only controller repair to reuse staged evidence.

        Older artifacts contain only the complete file digest. Their persisted
        per-file hashes still let us reconstruct the execution digest. A
        changed execution source, or a bumped controller behavior version,
        always requires a fresh predecessor experiment.
        """
        if prior.get('digest') == current.get('digest'):
            return True
        prior_files = prior.get('files') or {}
        current_files = current.get('files') or {}
        if not prior_files or not current_files:
            return False
        prior_execution = prior.get('executionDigest')
        if not prior_execution:
            files = {key: value for key, value in prior_files.items() if key != EXPERIMENT_CONTROLLER_FILE}
            prior_execution = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=True).encode('utf-8')).hexdigest()
        current_execution = current.get('executionDigest')
        if not current_execution:
            files = {key: value for key, value in current_files.items() if key != EXPERIMENT_CONTROLLER_FILE}
            current_execution = hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=True).encode('utf-8')).hexdigest()
        return (prior_execution == current_execution
                and int(prior.get('controllerBehaviorVersion', 1))
                == int(current.get('controllerBehaviorVersion', 1)))

    @staticmethod
    def _quality_gate(item: dict, summary: dict) -> dict:
        expected = int((item.get('protocol') or {}).get('taskCountPerArm') or 0)
        baseline, rsi = summary.get('baseline') or {}, summary.get('rsi') or {}
        complete_coverage = bool(expected and summary.get('pairedCompleted') == expected
                                 and baseline.get('attempts') == expected and rsi.get('attempts') == expected)
        all_started_passed = (baseline.get('attempts', 0) == baseline.get('passed', 0)
                               and rsi.get('attempts', 0) == rsi.get('passed', 0)
                               and baseline.get('attempts', 0) > 0 and rsi.get('attempts', 0) > 0)
        status = 'passed' if complete_coverage and all_started_passed else (
            'incomplete' if not complete_coverage else 'failed')
        return {
            'status': status,
            'expectedPerArm': expected,
            'pairedCompleted': summary.get('pairedCompleted', 0),
            'baselinePassed': baseline.get('passed', 0),
            'baselineAttempts': baseline.get('attempts', 0),
            'rsiPassed': rsi.get('passed', 0),
            'rsiAttempts': rsi.get('attempts', 0),
            'requirement': '两臂每个已启动任务均通过私有结构化事实与证据校验，且完成冻结范围。',
            'sameQualityCostClaim': status == 'passed',
            'reason': ('可比较的同质量 token 结论' if status == 'passed'
                       else '存在未完成或结构化失败任务；token 仅作瓶颈诊断，不能代表同质量经济性。'),
        }

    def _eligible_predecessor(self, mode: str, runtime: dict) -> dict | None:
        required = {
            PRECHECK_MODE_V4: SMOKE_MODE_V4,
            FULL_TRAIN_MODE_V2: PRECHECK_MODE_V4,
            PRECHECK_MODE_V5: SMOKE_MODE_V5,
            FULL_TRAIN_MODE_V3: PRECHECK_MODE_V5,
            PRECHECK_MODE_V6: SMOKE_MODE_V6,
            FULL_TRAIN_MODE_V4: PRECHECK_MODE_V6,
            PRECHECK_MODE_V7: SMOKE_MODE_V7,
            FULL_TRAIN_MODE_V5: PRECHECK_MODE_V7,
            PRECHECK_MODE_V8: SMOKE_MODE_V8,
            FULL_TRAIN_MODE_V6: PRECHECK_MODE_V8,
            PRECHECK_MODE_V9: SMOKE_MODE_V9,
            FULL_TRAIN_MODE_V7: PRECHECK_MODE_V9,
            PRECHECK_MODE_V10: SMOKE_MODE_V10,
            FULL_TRAIN_MODE_V8: PRECHECK_MODE_V10,
            PRECHECK_MODE_V11: SMOKE_MODE_V11,
            FULL_TRAIN_MODE_V9: PRECHECK_MODE_V11,
            PRECHECK_MODE_V12: SMOKE_MODE_V12,
            FULL_TRAIN_MODE_V10: PRECHECK_MODE_V12,
            PRECHECK_MODE_V13: SMOKE_MODE_V13,
            FULL_TRAIN_MODE_V11: PRECHECK_MODE_V13,
            PRECHECK_MODE_V14: SMOKE_MODE_V14,
            FULL_TRAIN_MODE_V12: PRECHECK_MODE_V14,
            PRECHECK_MODE_V15: SMOKE_MODE_V15,
            FULL_TRAIN_MODE_V13: PRECHECK_MODE_V15,
            PRECHECK_MODE_V16: SMOKE_MODE_V16,
            FULL_TRAIN_MODE_V14: PRECHECK_MODE_V16,
            PRECHECK_MODE_V17: SMOKE_MODE_V17,
            FULL_TRAIN_MODE_V15: PRECHECK_MODE_V17,
        }.get(mode)
        if not required:
            return None
        matches = []
        for item in self.items.values():
            if item.get('mode') != required or item.get('status') != 'completed':
                continue
            summary = self._summary(item)
            if self._quality_gate(item, summary).get('status') != 'passed':
                continue
            if mode in {PRECHECK_MODE_V11, PRECHECK_MODE_V12, PRECHECK_MODE_V13, PRECHECK_MODE_V14,
                        PRECHECK_MODE_V15, PRECHECK_MODE_V16, PRECHECK_MODE_V17}:
                weighted = (item.get('coverage') or {}).get('weightedRatioReconcile') or {}
                if weighted.get('arms') != ['baseline', 'rsi']:
                    continue
            prior = (item.get('protocol') or {}).get('runtimeFingerprint') or {}
            if self._runtime_matches(prior, runtime):
                matches.append(item)
        return max(matches, key=lambda row: row.get('finishedAt') or row.get('createdAt') or '') if matches else None

    def restore(self) -> None:
        if not self.root.exists():
            return
        for path in self.root.glob('*/experiment.json'):
            try:
                item = json.loads(path.read_text(encoding='utf-8'))
                if item.get('id') != path.parent.name:
                    continue
                if item.get('status') in ['queued', 'running']:
                    item.update(status='interrupted', finishedAt=now(),
                                error='服务重启；已保存的对照保持原样，不能在未知状态下自动续跑')
                    self._save(item)
                self.items[item['id']] = item
            except (OSError, ValueError, TypeError, KeyError):
                continue

    @staticmethod
    def _experience_snapshot(runner: TaskRunner, *, kind: str, pair: dict, arm: str) -> dict:
        evolution = runner.evolution
        return {
            'id': str(uuid4()), 'at': now(), 'kind': kind, 'arm': arm,
            'pairIndex': pair['index'], 'workpackId': pair['workpackId'],
            'versions': [
                {'id': row['id'], 'parentGraphId': row.get('parentGraphId'), 'generation': row.get('generation'),
                 'scenario': row.get('scenario'), 'family': row.get('family'), 'status': row.get('status'),
                 'sourceRunId': row.get('sourceRunId'), 'sourceTaskId': row.get('sourceTaskId'),
                 'evidenceCount': len(row.get('evidence') or []),
                 'patches': deepcopy(row.get('patches') or [])}
                for row in evolution.versions
            ],
            'workflows': [
                {'id': row['id'], 'sourceRunId': row.get('sourceRunId'), 'sourceTaskId': row.get('sourceTaskId'),
                 'scenario': row.get('scenario'), 'family': row.get('family'), 'contractHash': row.get('contractHash')}
                for row in evolution.workflows
            ],
            'tinyEdges': [
                {'id': row['id'], 'scenario': row.get('scenario'), 'support': row.get('support'),
                 'length': row.get('length'), 'sourceWorkflowIds': row.get('sourceWorkflowIds')}
                for row in evolution.tiny_edges
            ],
        }

    @staticmethod
    def _summary(item: dict) -> dict:
        def arm_summary(runs: list[dict]) -> dict:
            metrics = [run.get('metrics') or {} for run in runs]
            durations = [float(metric.get('durationMs') or 0) for metric in metrics]
            tokens = [_total(metric) for metric in metrics]
            passed = sum(run.get('status') == 'completed' and run.get('evaluation', {}).get('status') == 'passed' for run in runs)
            report_attempts = sum(int(metric.get('reportAttempts') or 0) for metric in metrics)
            failed_reports = sum(int(metric.get('failedReportAttempts') or 0) for metric in metrics)
            categories = _counter([category for run in runs for category in _failure_category(run)])
            return {
                'attempts': len(runs),
                'completed': sum(run.get('status') == 'completed' for run in runs),
                'passed': passed,
                'totalTokens': sum(tokens),
                'maxTokens': max(tokens, default=0),
                'tokensPerPassed': round(sum(tokens) / passed, 3) if passed else None,
                'modelRequests': sum(int(metric.get('modelRequests') or 0) for metric in metrics),
                'modelProviderAttempts': sum(int(metric.get('modelProviderAttempts') or metric.get('modelRequests') or 0) for metric in metrics),
                'modelTransportRetries': sum(int(metric.get('modelTransportRetries') or 0) for metric in metrics),
                'toolCalls': sum(int(metric.get('toolCalls') or 0) for metric in metrics),
                'toolErrors': sum(int(metric.get('toolErrors') or 0) for metric in metrics),
                'controlErrors': sum(int(metric.get('controlErrors') or 0) for metric in metrics),
                'durationMs': round(sum(durations), 3),
                'p50DurationMs': _percentile(durations, .5),
                'p95DurationMs': _percentile(durations, .95),
                'maxDurationMs': max(durations, default=0),
                'runtimeOverheadMs': round(sum(float(metric.get('runtimeOverheadMs') or 0) for metric in metrics), 3),
                'usageIncomplete': sum(not bool(metric.get('usageComplete', True)) for metric in metrics),
                'maintenanceErrors': sum(bool((run.get('evolution') or {}).get('maintenanceError')) for run in runs),
                'reportAttempts': report_attempts,
                'failedReportAttempts': failed_reports,
                'runsWithReportRecovery': sum(int(metric.get('reportAttempts') or 0) > 1 for metric in metrics),
                'runsWithRepeatedReportFailures': sum(int(metric.get('failedReportAttempts') or 0) > 1 for metric in metrics),
                'reportEvidenceCoverageGaps': sum(int(metric.get('reportEvidenceCoverageGaps') or 0) for metric in metrics),
                'reportEvidenceFormatFailures': sum(int(metric.get('reportEvidenceFormatFailures') or 0) for metric in metrics),
                'reportRecoveryBlockedReads': sum(int(metric.get('reportRecoveryBlockedReads') or 0) for metric in metrics),
                'duplicateReadGuardRejects': sum(int(metric.get('duplicateReadGuardRejects') or 0) for metric in metrics),
                'duplicateComputeGuardRejects': sum(int(metric.get('duplicateComputeGuardRejects') or 0) for metric in metrics),
                'observedScopeCompletions': sum(int(metric.get('observedScopeCompletions') or 0) for metric in metrics),
                'contextEvidenceReferenceCompactions': sum(int(metric.get('contextEvidenceReferenceCompactions') or 0) for metric in metrics),
                'contextCompactedCharacters': sum(int(metric.get('contextCompactedCharacters') or 0) for metric in metrics),
                'deterministicScopeRecoveryReads': sum(int(metric.get('deterministicScopeRecoveryReads') or 0) for metric in metrics),
                'deterministicReportResubmits': sum(int(metric.get('deterministicReportResubmits') or 0) for metric in metrics),
                'deterministicFactRecoveryComputes': sum(int(metric.get('deterministicFactRecoveryComputes') or 0) for metric in metrics),
                'deterministicFactRecoveryFailures': sum(int(metric.get('deterministicFactRecoveryFailures') or 0) for metric in metrics),
                'deadlineFinalizationGuards': sum(int(metric.get('deadlineFinalizationGuards') or 0) for metric in metrics),
                'missingReports': sum(not _has_submission(run) for run in runs),
                'failureCategories': categories,
            }

        def local_overhead(runs: list[dict]) -> dict:
            keys = ['lookupMs', 'retrievalMs', 'selectionMs', 'compileMs', 'localCompileMs', 'bindingMs',
                    'maintenanceMs', 'persistMs', 'compositionLocalMs', 'compositionModelWallMs']
            return {key: round(sum(float((run.get('evolution') or {}).get(key) or 0) for run in runs), 3) for key in keys}

        result = {}
        completed = []
        for arm in ['baseline', 'rsi']:
            runs = [pair.get('runs', {}).get(arm) for pair in item['pairs']]
            runs = [run for run in runs if run]
            result[arm] = arm_summary(runs)
            if arm == 'rsi':
                result[arm]['localOrchestration'] = local_overhead(runs)

        def grouped(key: str) -> list[dict]:
            groups: dict[str, list[dict]] = {}
            for pair in item['pairs']:
                groups.setdefault(str(pair.get(key) or 'unknown'), []).append(pair)
            rows = []
            for name, pairs in sorted(groups.items()):
                summary = {'key': name, 'taskCount': len(pairs), 'baseline': {}, 'rsi': {}}
                for arm in ['baseline', 'rsi']:
                    runs = [pair.get('runs', {}).get(arm) for pair in pairs]
                    runs = [run for run in runs if run]
                    metrics = [run.get('metrics') or {} for run in runs]
                    summary[arm] = {
                        'attempts': len(runs),
                        'passed': sum(run.get('status') == 'completed' and run.get('evaluation', {}).get('status') == 'passed' for run in runs),
                        'totalTokens': sum(_total(metric) for metric in metrics),
                        'modelRequests': sum(int(metric.get('modelRequests') or 0) for metric in metrics),
                        'modelProviderAttempts': sum(int(metric.get('modelProviderAttempts') or metric.get('modelRequests') or 0) for metric in metrics),
                        'modelTransportRetries': sum(int(metric.get('modelTransportRetries') or 0) for metric in metrics),
                        'toolCalls': sum(int(metric.get('toolCalls') or 0) for metric in metrics),
                        'durationMs': round(sum(float(metric.get('durationMs') or 0) for metric in metrics), 3),
                    }
                baseline_tokens, rsi_tokens = summary['baseline']['totalTokens'], summary['rsi']['totalTokens']
                summary['tokenSavingRate'] = round(1 - rsi_tokens / baseline_tokens, 6) if baseline_tokens else None
                summary['fastReuse'] = sum((pair.get('runs', {}).get('rsi', {}).get('evolution') or {}).get('planningPath') == 'fast' for pair in pairs)
                summary['workflowCreated'] = sum(len((pair.get('runs', {}).get('rsi', {}).get('evolution') or {}).get('generatedVersionIds') or []) for pair in pairs)
                rows.append(summary)
            return rows

        curve = []
        base_tokens = rsi_tokens = 0
        for pair in item['pairs']:
            baseline, rsi = pair.get('runs', {}).get('baseline'), pair.get('runs', {}).get('rsi')
            # A cancelled pair can have two terminal arm records when the
            # cancellation arrives between arms. Keep those arm attempts in
            # the per-arm accounting, but never treat them as a completed,
            # comparable pair or include them in paired cost curves.
            if (pair.get('status') not in [None, 'completed'] or not baseline or not rsi
                    or baseline.get('status') in ['queued', 'running']
                    or rsi.get('status') in ['queued', 'running']):
                continue
            completed.append(pair)
            base_tokens += _total(baseline.get('metrics'))
            rsi_tokens += _total(rsi.get('metrics'))
            curve.append({
                'index': pair['index'], 'workpackId': pair['workpackId'], 'workflowType': pair['workflowType'],
                'round': pair['round'], 'baselineTokens': _total(baseline.get('metrics')),
                'rsiTokens': _total(rsi.get('metrics')), 'baselineCumulativeTokens': base_tokens,
                'rsiCumulativeTokens': rsi_tokens,
                'tokenSavingRate': round(1 - rsi_tokens / base_tokens, 6) if base_tokens else None,
                'rsiPlanningPath': (rsi.get('evolution') or {}).get('planningPath'),
                'usedVersionId': (rsi.get('evolution') or {}).get('usedVersionId'),
                'rsiPassed': rsi.get('evaluation', {}).get('status') == 'passed',
                'baselinePassed': baseline.get('evaluation', {}).get('status') == 'passed',
            })
        windows = []
        for start in range(0, len(curve), 4):
            segment = curve[start:start + 4]
            if len(segment) != 4:
                continue
            baseline_window = sum(point['baselineTokens'] for point in segment)
            rsi_window = sum(point['rsiTokens'] for point in segment)
            windows.append({
                'startIndex': segment[0]['index'], 'endIndex': segment[-1]['index'],
                'taskCount': len(segment), 'baselineTokens': baseline_window, 'rsiTokens': rsi_window,
                'tokenSavingRate': round(1 - rsi_window / baseline_window, 6) if baseline_window else None,
                'fastCoverage': round(sum(point['rsiPlanningPath'] == 'fast' for point in segment) / len(segment), 6),
                'baselinePassRate': round(sum(point['baselinePassed'] for point in segment) / len(segment), 6),
                'rsiPassRate': round(sum(point['rsiPassed'] for point in segment) / len(segment), 6),
            })
        plateau_matches = []
        for previous, current in zip(windows, windows[1:]):
            saving_delta = abs((current['tokenSavingRate'] or 0) - (previous['tokenSavingRate'] or 0))
            fast_delta = abs(current['fastCoverage'] - previous['fastCoverage'])
            success_delta = abs(current['rsiPassRate'] - previous['rsiPassRate'])
            matched = saving_delta < .03 and fast_delta < .10 and success_delta == 0
            plateau_matches.append({
                'previousEndIndex': previous['endIndex'], 'currentEndIndex': current['endIndex'],
                'tokenSavingRateDelta': round(saving_delta, 6), 'fastCoverageDelta': round(fast_delta, 6),
                'rsiPassRateDelta': round(success_delta, 6), 'matchesRule': matched,
            })
        consecutive_matches = 0
        possible_plateau = False
        for row in plateau_matches:
            consecutive_matches = consecutive_matches + 1 if row['matchesRule'] else 0
            possible_plateau = possible_plateau or consecutive_matches >= 2
        result.update({
            'pairedCompleted': len(completed),
            'tokenSavingRate': round(1 - rsi_tokens / base_tokens, 6) if base_tokens else None,
            'curve': curve,
            'byScenario': grouped('scenario'),
            'byWorkflow': grouped('workflowType'),
            'byRound': grouped('round'),
            'learning': {
                'workflowCreated': sum(len((pair.get('runs', {}).get('rsi', {}).get('evolution') or {}).get('generatedVersionIds') or []) for pair in item['pairs']),
                'fastReuse': sum((pair.get('runs', {}).get('rsi', {}).get('evolution') or {}).get('planningPath') == 'fast' for pair in item['pairs']),
                'composition': sum((pair.get('runs', {}).get('rsi', {}).get('evolution') or {}).get('planningPath') == 'composition' for pair in item['pairs']),
                'fallback': sum((pair.get('runs', {}).get('rsi', {}).get('evolution') or {}).get('planningPath') == 'fallback' for pair in item['pairs']),
            },
            'reliability': {
                'allUsageComplete': all(result[arm]['usageIncomplete'] == 0 for arm in ['baseline', 'rsi']),
                'note': ('每臂包含所有已启动任务的失败、恢复和 timeout；不是只统计初次报告失败。'
                         '报告修复次数以保存的 reportAttempts / failedReportAttempts 为准。'),
            },
            'saturation': {
                'windowSize': 4,
                'windows': windows,
                'comparisons': plateau_matches,
                'possiblePlateau': possible_plateau,
                'familyAssessment': ('每个 workflow 只有四个 train 实例，缺少两个相邻的四任务窗口；'
                                     '不能在单一任务族上判断平台期。'),
                'note': ('全局窗口交错了不同场景和工作流，只能作为描述性成本/覆盖检查，'
                         '不证明单一 workflow 或理论学习上限。'),
            },
        })
        result['qualityGate'] = WorkpackExperiment._quality_gate(item, result)
        return result

    def protocol(self, mode: str = SMOKE_MODE_V17) -> dict:
        if mode not in EXPERIMENT_MODES:
            raise ValueError('未知工作包实验模式')
        is_legacy_precheck = mode == PRECHECK_MODE
        is_precheck = mode in {PRECHECK_MODE, PRECHECK_MODE_V4, PRECHECK_MODE_V5, PRECHECK_MODE_V6, PRECHECK_MODE_V7, PRECHECK_MODE_V8, PRECHECK_MODE_V9, PRECHECK_MODE_V10, PRECHECK_MODE_V11, PRECHECK_MODE_V12, PRECHECK_MODE_V13, PRECHECK_MODE_V14, PRECHECK_MODE_V15, PRECHECK_MODE_V16, PRECHECK_MODE_V17}
        is_smoke = mode in {SMOKE_MODE_V4, SMOKE_MODE_V5, SMOKE_MODE_V6, SMOKE_MODE_V7, SMOKE_MODE_V8, SMOKE_MODE_V9, SMOKE_MODE_V10, SMOKE_MODE_V11, SMOKE_MODE_V12, SMOKE_MODE_V13, SMOKE_MODE_V14, SMOKE_MODE_V15, SMOKE_MODE_V16, SMOKE_MODE_V17}
        manifest = (smoke_manifest_v16(self.bank) if mode in {SMOKE_MODE_V16, SMOKE_MODE_V17}
                    else smoke_manifest_v9(self.bank) if mode in {SMOKE_MODE_V9, SMOKE_MODE_V10, SMOKE_MODE_V11, SMOKE_MODE_V12, SMOKE_MODE_V13, SMOKE_MODE_V14, SMOKE_MODE_V15} else smoke_manifest(self.bank)
                    if is_smoke else precheck_manifest_v16(self.bank) if mode in {PRECHECK_MODE_V16, PRECHECK_MODE_V17} else precheck_manifest(self.bank)
                    if is_precheck else full_train_manifest(self.bank))
        # V3 showed that the earlier historical-token estimate was too low.
        # The formal estimate uses its observed 12-pair cost, not a promise of
        # a saving. Provider time and output length can still vary by task.
        multiplier = len(manifest) / 12
        estimated_requests = round(128 * multiplier)
        estimated_tokens = round(986_053 * multiplier)
        estimated_duration_ms = round(1_259_315 * multiplier)
        return {
            'id': ({SMOKE_MODE_V4: 'workspace-workpack-online-smoke-v4',
                    PRECHECK_MODE_V4: 'workspace-workpack-online-precheck-v4',
                    FULL_TRAIN_MODE_V2: 'workspace-workpack-online-full-train-v2',
                    SMOKE_MODE_V5: 'workspace-workpack-online-smoke-v5',
                    PRECHECK_MODE_V5: 'workspace-workpack-online-precheck-v5',
                    FULL_TRAIN_MODE_V3: 'workspace-workpack-online-full-train-v3',
                    SMOKE_MODE_V6: 'workspace-workpack-online-smoke-v6',
                    PRECHECK_MODE_V6: 'workspace-workpack-online-precheck-v6',
                    FULL_TRAIN_MODE_V4: 'workspace-workpack-online-full-train-v4',
                    SMOKE_MODE_V7: 'workspace-workpack-online-smoke-v7',
                    PRECHECK_MODE_V7: 'workspace-workpack-online-precheck-v7',
                    FULL_TRAIN_MODE_V5: 'workspace-workpack-online-full-train-v5',
                    SMOKE_MODE_V8: 'workspace-workpack-online-smoke-v8',
                    PRECHECK_MODE_V8: 'workspace-workpack-online-precheck-v8',
                    FULL_TRAIN_MODE_V6: 'workspace-workpack-online-full-train-v6',
                    SMOKE_MODE_V9: 'workspace-workpack-online-smoke-v9',
                    PRECHECK_MODE_V9: 'workspace-workpack-online-precheck-v9',
                    FULL_TRAIN_MODE_V7: 'workspace-workpack-online-full-train-v7',
                    SMOKE_MODE_V10: 'workspace-workpack-online-smoke-v10',
                    PRECHECK_MODE_V10: 'workspace-workpack-online-precheck-v10',
                    FULL_TRAIN_MODE_V8: 'workspace-workpack-online-full-train-v8',
                    SMOKE_MODE_V11: 'workspace-workpack-online-smoke-v11',
                    PRECHECK_MODE_V11: 'workspace-workpack-online-precheck-v11',
                    FULL_TRAIN_MODE_V9: 'workspace-workpack-online-full-train-v9',
                    SMOKE_MODE_V12: 'workspace-workpack-online-smoke-v12',
                    PRECHECK_MODE_V12: 'workspace-workpack-online-precheck-v12',
                    FULL_TRAIN_MODE_V10: 'workspace-workpack-online-full-train-v10',
                    SMOKE_MODE_V13: 'workspace-workpack-online-smoke-v13',
                    PRECHECK_MODE_V13: 'workspace-workpack-online-precheck-v13',
                    FULL_TRAIN_MODE_V11: 'workspace-workpack-online-full-train-v11',
                    SMOKE_MODE_V14: 'workspace-workpack-online-smoke-v14',
                    PRECHECK_MODE_V14: 'workspace-workpack-online-precheck-v14',
                    FULL_TRAIN_MODE_V12: 'workspace-workpack-online-full-train-v12',
                    SMOKE_MODE_V15: 'workspace-workpack-online-smoke-v15',
                    PRECHECK_MODE_V15: 'workspace-workpack-online-precheck-v15',
                    FULL_TRAIN_MODE_V13: 'workspace-workpack-online-full-train-v13',
                    SMOKE_MODE_V16: 'workspace-workpack-online-smoke-v16',
                    PRECHECK_MODE_V16: 'workspace-workpack-online-precheck-v16',
                    FULL_TRAIN_MODE_V14: 'workspace-workpack-online-full-train-v14',
                    SMOKE_MODE_V17: 'workspace-workpack-online-smoke-v17',
                    PRECHECK_MODE_V17: 'workspace-workpack-online-precheck-v17',
                    FULL_TRAIN_MODE_V15: 'workspace-workpack-online-full-train-v15'}.get(
                        mode,
                        'workspace-workpack-online-precheck-v3' if is_legacy_precheck else 'workspace-workpack-online-full-train-v1')),
            'mode': mode,
            'purpose': ('serial_three_scenario_workspace_smoke_via_generic_runtime' if is_smoke
                        else 'serial_online_precheck_via_generic_workspace_planning_and_runtime'
                        if is_precheck else 'serial_online_full_train_via_generic_workspace_planning_and_runtime'),
            'taskCountPerArm': len(manifest),
            'agentRuns': len(manifest) * 2,
            'estimatedAgentModelRequests': estimated_requests,
            'estimatedAgentTokens': estimated_tokens,
            'estimatedSerialDurationMs': estimated_duration_ms,
            'estimateBasis': 'V3 completed precheck actual aggregate; provider/model output variation remains possible',
            'judge': 'not_run; separate explicit cost if requested after Agent stability',
            'limits': {'run': 1, 'model': 1, 'read': 1},
            'baseline': 'plan_react_without_cross_task_learning',
            'rsi': 'graph_rsi_empty_isolated_experience_train_only',
            'graphCompilation': ('Planner sourceTable slots are validated against the current workspace schema and '
                                 'compiled locally; no frozen workpack graph or task-specific read prefix is injected.'),
            'runtimeFingerprint': self._runtime_fingerprint(),
            'qualityGate': {
                'requires': '两臂每个已启动任务均通过私有结构化事实与证据校验，且完成冻结范围。',
                'blocksSameQualityCostClaimWhenFailed': True,
                'blocksNextStage': mode in {SMOKE_MODE_V4, PRECHECK_MODE_V4, SMOKE_MODE_V5, PRECHECK_MODE_V5,
                                             SMOKE_MODE_V6, PRECHECK_MODE_V6, SMOKE_MODE_V7, PRECHECK_MODE_V7,
                                             SMOKE_MODE_V8, PRECHECK_MODE_V8, SMOKE_MODE_V9, PRECHECK_MODE_V9,
                                             SMOKE_MODE_V10, PRECHECK_MODE_V10, SMOKE_MODE_V11, PRECHECK_MODE_V11,
                                             SMOKE_MODE_V12, PRECHECK_MODE_V12, SMOKE_MODE_V13, PRECHECK_MODE_V13,
                                             SMOKE_MODE_V14, PRECHECK_MODE_V14, SMOKE_MODE_V15, PRECHECK_MODE_V15,
                                             SMOKE_MODE_V16, PRECHECK_MODE_V16,
                                             SMOKE_MODE_V17, PRECHECK_MODE_V17},
            },
            'requiredSmokeCoverage': ('baseline_and_rsi_must_call_workspace_reconcile_keyed_sums_with_rightTerms '
                                      'for_finance_freight_contribution; declared_fact_recovery_is_observed_only_after_a_real_first_business_fact_failure '
                                      'and_never_forced_by_a_synthetic_failure' if mode in {SMOKE_MODE_V16, SMOKE_MODE_V17}
                                      else 'baseline_and_rsi_must_call_workspace_reconcile_keyed_sums_with_rightTerms '
                                      'for_finance_freight_contribution' if mode in {SMOKE_MODE_V11, SMOKE_MODE_V12, SMOKE_MODE_V13, SMOKE_MODE_V14, SMOKE_MODE_V15} else None),
            'order': (f'{len(set(item["round"] for item in manifest))} rounds; '
                      f'{len({item["workflowType"] for item in manifest})} workflows per round; '
                      'each arm sees the same workpack order; pair arm order alternates'),
            'manifest': manifest,
            'saturationRule': {
                'window': 4,
                'requires': 'two adjacent fixed windows',
                'tokenSavingRateDelta': '< 0.03',
                'fastCoverageDelta': '< 0.10',
                'successRateDelta': '= 0',
                'interpretation': ('descriptive only; this 12-task precheck is normally too small to establish a platform'
                                   if is_precheck else 'descriptive only; a fixed 48-task train flow can indicate a possible plateau, not a theoretical limit'),
            },
        }

    async def start(self, mode: str = SMOKE_MODE_V17) -> dict:
        if self.tasks:
            raise ValueError('已有工作包在线实验在运行')
        if mode not in STARTABLE_MODES:
            raise ValueError('旧工作包实验仅保留只读记录；请选择当前 V8 smoke、预检或正式流')
        protocol = self.protocol(mode)
        if mode in {PRECHECK_MODE_V4, FULL_TRAIN_MODE_V2, PRECHECK_MODE_V5, FULL_TRAIN_MODE_V3,
                    PRECHECK_MODE_V6, FULL_TRAIN_MODE_V4, PRECHECK_MODE_V7, FULL_TRAIN_MODE_V5,
                    PRECHECK_MODE_V8, FULL_TRAIN_MODE_V6, PRECHECK_MODE_V9, FULL_TRAIN_MODE_V7,
                    PRECHECK_MODE_V10, FULL_TRAIN_MODE_V8, PRECHECK_MODE_V11, FULL_TRAIN_MODE_V9,
                    PRECHECK_MODE_V12, FULL_TRAIN_MODE_V10, PRECHECK_MODE_V13, FULL_TRAIN_MODE_V11,
                    PRECHECK_MODE_V14, FULL_TRAIN_MODE_V12, PRECHECK_MODE_V15, FULL_TRAIN_MODE_V13,
                    PRECHECK_MODE_V16, FULL_TRAIN_MODE_V14,
                    PRECHECK_MODE_V17, FULL_TRAIN_MODE_V15}:
            predecessor = self._eligible_predecessor(mode, protocol['runtimeFingerprint'])
            if not predecessor:
                stage = {
                    PRECHECK_MODE_V4: 'V4 三场景 smoke',
                    FULL_TRAIN_MODE_V2: 'V4 质量通过的在线预检',
                    PRECHECK_MODE_V5: 'V5 三场景 smoke',
                    FULL_TRAIN_MODE_V3: 'V5 质量通过的在线预检',
                    PRECHECK_MODE_V6: 'V6 三场景 smoke',
                    FULL_TRAIN_MODE_V4: 'V6 质量通过的在线预检',
                    PRECHECK_MODE_V7: 'V7 三场景 smoke',
                    FULL_TRAIN_MODE_V5: 'V7 质量通过的在线预检',
                    PRECHECK_MODE_V8: 'V8 三场景 smoke',
                    FULL_TRAIN_MODE_V6: 'V8 质量通过的在线预检',
                    PRECHECK_MODE_V9: 'V9 三场景 smoke',
                    FULL_TRAIN_MODE_V7: 'V9 质量通过的在线预检',
                    PRECHECK_MODE_V10: 'V10 三场景 smoke',
                    FULL_TRAIN_MODE_V8: 'V10 质量通过的在线预检',
                    PRECHECK_MODE_V11: 'V11 三场景 smoke',
                    FULL_TRAIN_MODE_V9: 'V11 质量通过的在线预检',
                    PRECHECK_MODE_V12: 'V12 三场景 smoke',
                    FULL_TRAIN_MODE_V10: 'V12 质量通过的在线预检',
                    PRECHECK_MODE_V13: 'V13 三场景 smoke',
                    FULL_TRAIN_MODE_V11: 'V13 质量通过的在线预检',
                    PRECHECK_MODE_V14: 'V14 三场景 smoke',
                    FULL_TRAIN_MODE_V12: 'V14 质量通过的在线预检',
                    PRECHECK_MODE_V15: 'V15 三场景 smoke',
                    FULL_TRAIN_MODE_V13: 'V15 质量通过的在线预检',
                    PRECHECK_MODE_V16: 'V16 四项 smoke（含两种公开事实恢复计算）',
                    FULL_TRAIN_MODE_V14: 'V16 质量通过的在线预检',
                    PRECHECK_MODE_V17: 'V17 四项 smoke（含截止时间报告保护）',
                    FULL_TRAIN_MODE_V15: 'V17 质量通过的在线预检',
                }[mode]
                raise ValueError('启动前置条件未满足：需要当前 runtime 下已完成且质量门槛通过的' + stage)
            protocol['predecessorExperimentId'] = predecessor['id']
        item_id = str(uuid4())
        directory = self.root / item_id
        managers = {arm: WorkspaceManager(directory / arm) for arm in ['baseline', 'rsi']}
        runners = {
            'baseline': TaskRunner(WorkspaceBank(managers['baseline']), self.provider_factory, run_limit=1, model_limit=1, read_limit=1,
                                   run_directory=directory / 'baseline' / 'runs', evolution_path=directory / 'baseline' / 'experience.json', learning_enabled=False),
            'rsi': TaskRunner(WorkspaceBank(managers['rsi']), self.provider_factory, run_limit=1, model_limit=1, read_limit=1,
                              run_directory=directory / 'rsi' / 'runs', evolution_path=directory / 'rsi' / 'experience.json', learning_enabled=True),
        }
        item = {
            'id': item_id, 'mode': mode, 'status': 'queued', 'createdAt': now(), 'protocol': protocol,
            'artifacts': {'root': str(directory), 'baselineExperience': str(directory / 'baseline' / 'experience.json'),
                          'rsiExperience': str(directory / 'rsi' / 'experience.json')},
            'pairs': [dict(index=index, **deepcopy(row), status='pending', runs={}, snapshots=[])
                      for index, row in enumerate(protocol['manifest'], start=1)],
            'coverage': {
                'weightedRatioReconcile': {'arms': [], 'workpackId': None},
                'deterministicFactRecovery': {
                    'workspace_aggregate_rows': {'arms': [], 'workpackId': None},
                    'workspace_ordered_partition': {'arms': [], 'workpackId': None},
                },
            },
            'cancelRequested': False, 'events': [], 'summary': self._summary({'pairs': []}),
        }
        self.items[item_id] = item
        self.runners[item_id] = runners
        self._save(item)

        async def work():
            item.update(status='running', startedAt=now())
            self._save(item)
            try:
                for pair in item['pairs']:
                    if item.get('cancelRequested'):
                        raise ExperimentCancelled()
                    pair['status'] = 'running'
                    # Alternate the inter-arm order; each arm itself still sees
                    # exactly the frozen manifest order.
                    arm_order = ['baseline', 'rsi'] if pair['index'] % 2 else ['rsi', 'baseline']
                    pair['armOrder'] = arm_order
                    item['events'].append({'at': now(), 'kind': 'pair_start', 'pairIndex': pair['index'],
                                           'workpackId': pair['workpackId'], 'armOrder': arm_order})
                    self._save(item)
                    for arm in arm_order:
                        if item.get('cancelRequested'):
                            raise ExperimentCancelled()
                        manager, runner = managers[arm], runners[arm]
                        workspace, task = install_workpack(manager, self.bank, pair['workpackId'])
                        before = self._experience_snapshot(runner, kind='before', pair=pair, arm=arm)
                        pair['snapshots'].append(before)
                        write_private(directory / arm / 'snapshots' / f'{pair["index"]:02d}-before.json', before)
                        strategy = 'plan_react' if arm == 'baseline' else 'graph_rsi'
                        item['events'].append({'at': now(), 'kind': 'arm_start', 'pairIndex': pair['index'], 'arm': arm,
                                               'strategy': strategy, 'workspaceId': workspace['id'], 'taskId': task['id']})
                        self._save(item)
                        run = await runner.start(TaskRunRequest(taskId=task['id'], strategy=strategy))
                        pair['runs'][arm] = _compact(run)
                        pair['runs'][arm]['hasSubmission'] = bool(run.get('submission'))
                        self.active_runs[item_id] = (runner, run['id'])
                        item['protocol']['model'] = run.get('models', {}).get('executor')
                        item['summary'] = self._summary(item)
                        self._save(item)
                        await runner.tasks[run['id']]
                        self.active_runs.pop(item_id, None)
                        pair['runs'][arm] = _compact(run)
                        pair['runs'][arm]['hasSubmission'] = bool(run.get('submission'))
                        if pair['workpackId'].startswith('finance-freight-contribution-'):
                            used_weighted = any(
                                trace.get('tool') == 'workspace_reconcile_keyed_sums'
                                and any((comparison or {}).get('rightTerms')
                                        for comparison in (trace.get('arguments') or {}).get('comparisons') or [])
                                for trace in run.get('toolTrace') or []
                            )
                            if used_weighted:
                                coverage = item['coverage']['weightedRatioReconcile']
                                coverage['workpackId'] = pair['workpackId']
                                if arm not in coverage['arms']:
                                    coverage['arms'].append(arm)
                                coverage['arms'].sort()
                        expected_fact_tool = {
                            'support-policy-draft': 'workspace_aggregate_rows',
                            'support-period-comparison': 'workspace_ordered_partition',
                        }.get(pair['workflowType'])
                        if expected_fact_tool and any(
                            trace.get('executor') == 'runtime'
                            and trace.get('tool') == expected_fact_tool
                            and trace.get('ok') is True
                            for trace in run.get('toolTrace') or []
                        ):
                            coverage = item['coverage']['deterministicFactRecovery'][expected_fact_tool]
                            coverage['workpackId'] = pair['workpackId']
                            if arm not in coverage['arms']:
                                coverage['arms'].append(arm)
                            coverage['arms'].sort()
                        after = self._experience_snapshot(runner, kind='after', pair=pair, arm=arm)
                        pair['snapshots'].append(after)
                        write_private(directory / arm / 'snapshots' / f'{pair["index"]:02d}-after.json', after)
                        item['events'].append({'at': now(), 'kind': 'arm_finished', 'pairIndex': pair['index'], 'arm': arm,
                                               'runId': run['id'], 'status': run.get('status'),
                                               'evaluation': run.get('evaluation', {}).get('status'),
                                               'planningPath': (run.get('evolution') or {}).get('planningPath')})
                        item['summary'] = self._summary(item)
                        self._save(item)
                        if item.get('cancelRequested'):
                            raise ExperimentCancelled()
                    pair['status'] = 'completed'
                    item['summary'] = self._summary(item)
                    self._save(item)
                item['status'] = 'completed'
            except ExperimentCancelled:
                active_pair = next((pair for pair in item['pairs'] if pair.get('status') == 'running'), None)
                if active_pair:
                    active_pair['status'] = 'cancelled'
                item['events'].append({'at': now(), 'kind': 'cancelled', 'pairIndex': active_pair.get('index') if active_pair else None,
                                       'reason': '已请求取消；不再启动新的 pair 或 arm'})
                item['status'] = 'cancelled'
            except asyncio.CancelledError:
                item.update(status='interrupted', error='服务关闭时实验任务被中断；已保存的运行不自动续跑')
                raise
            except Exception as error:
                item.update(status='failed', error=str(error)[:1200])
            finally:
                item['finishedAt'] = now()
                item['summary'] = self._summary(item)
                self._save(item)
                self.active_runs.pop(item_id, None)
                self.tasks.pop(item_id, None)

        self.tasks[item_id] = asyncio.create_task(work())
        return deepcopy(item)

    def get(self, item_id: str) -> dict:
        if item_id not in self.items:
            path = self._path(item_id)
            if not path.exists():
                raise KeyError(item_id)
            self.items[item_id] = json.loads(path.read_text(encoding='utf-8'))
        # Older completed artifacts predate grouped display statistics. Derive
        # them at read time from their unchanged raw pair records; do not
        # rewrite those historical artifacts merely for a dashboard field.
        if 'reliability' not in (self.items[item_id].get('summary') or {}):
            self.items[item_id]['summary'] = self._summary(self.items[item_id])
        return deepcopy(self.items[item_id])

    @staticmethod
    def _dashboard_protocol(protocol: dict) -> dict:
        """Expose the frozen public experiment contract, not source hashes or paths."""
        return {
            key: deepcopy(protocol.get(key)) for key in [
                'id', 'mode', 'purpose', 'taskCountPerArm', 'agentRuns',
                'estimatedAgentModelRequests', 'estimatedAgentTokens',
                'estimatedSerialDurationMs', 'estimateBasis', 'judge', 'limits',
                'baseline', 'rsi', 'graphCompilation', 'qualityGate',
                'requiredSmokeCoverage', 'order', 'manifest', 'saturationRule',
                'predecessorExperimentId', 'model',
            ]
        }

    @staticmethod
    def _dashboard_pair(pair: dict) -> dict:
        """Keep just the immutable task identity, accounting, and experience lineage."""
        rsi_run = (pair.get('runs') or {}).get('rsi') or {}
        used_version_id = (rsi_run.get('evolution') or {}).get('usedVersionId')
        before = next((snapshot for snapshot in pair.get('snapshots') or []
                       if snapshot.get('kind') == 'before' and snapshot.get('arm') == 'rsi'), None)
        snapshots = []
        if before and used_version_id:
            version = next((row for row in before.get('versions') or [] if row.get('id') == used_version_id), None)
            if version:
                source_run_id = version.get('sourceRunId')
                source = next((row for row in before.get('workflows') or []
                               if row.get('id') == source_run_id or row.get('sourceRunId') == source_run_id), {})
                snapshots.append({
                    key: deepcopy(before.get(key)) for key in ['id', 'at', 'kind', 'arm', 'pairIndex', 'workpackId']
                } | {
                    'versions': [{
                        key: deepcopy(version.get(key)) for key in [
                            'id', 'parentGraphId', 'generation', 'scenario', 'family', 'status',
                            'sourceRunId', 'sourceTaskId', 'evidenceCount',
                        ]
                    } | {'sourceTaskId': version.get('sourceTaskId') or source.get('sourceTaskId')}],
                })
        return {
            key: deepcopy(pair.get(key)) for key in [
                'index', 'workpackId', 'scenario', 'workflowType', 'sourceTaskId',
                'recordCount', 'difficulty', 'round', 'status', 'armOrder',
            ]
        } | {
            'runs': {arm: _dashboard_run((pair.get('runs') or {}).get(arm)) for arm in ['baseline', 'rsi']},
            'snapshots': snapshots,
        }

    def dashboard(self, item_id: str) -> dict:
        """Return the compact experiment-center view; full trace retrieval is per run."""
        item = self.get(item_id)
        return {
            key: deepcopy(item.get(key)) for key in [
                'id', 'mode', 'status', 'createdAt', 'startedAt', 'finishedAt', 'error',
            ]
        } | {
            'protocol': self._dashboard_protocol(item.get('protocol') or {}),
            'pairs': [self._dashboard_pair(pair) for pair in item.get('pairs') or []],
            'summary': deepcopy(item.get('summary') or {}),
            'coverage': deepcopy(item.get('coverage') or {}),
        }

    def showcase_comparison(self, workpack_id: str) -> dict:
        """Return one saved, quality-gated V17 pair for the interactive workspace.

        The workspace must not download the full 48-pair dashboard merely to
        show a loaded example's historical comparison.  This projection is
        deliberately read-only: it contains the same frozen prompt/material
        identity and compact arm accounting, while traces and reports remain
        behind the existing per-run endpoints.
        """
        spec = next((row for row in list_workpacks(self.bank) if row['id'] == workpack_id), None)
        if not spec:
            raise KeyError(workpack_id)

        candidates = []
        for item in self.items.values():
            if item.get('mode') != FULL_TRAIN_MODE_V15 or item.get('status') != 'completed':
                continue
            summary = item.get('summary') or self._summary(item)
            if self._quality_gate(item, summary).get('status') != 'passed':
                continue
            pair = next((row for row in item.get('pairs') or [] if row.get('workpackId') == workpack_id), None)
            if pair and pair.get('status') == 'completed':
                candidates.append((item, pair, summary))

        public_spec = {
            key: deepcopy(spec.get(key)) for key in [
                'id', 'workflowType', 'scenario', 'title', 'split', 'difficulty',
                'sourceTaskId', 'sourceUrl', 'recordCount', 'task',
                'deliveryContract', 'sourceProvenance',
            ]
        }
        if not candidates:
            return {
                'available': False,
                'reason': '该工作包没有保存的、同质量门槛通过的 V17 双臂运行；不会自动发起另一侧 Agent。',
                'workpack': public_spec,
            }

        item, pair, summary = max(
            candidates,
            key=lambda row: row[0].get('finishedAt') or row[0].get('createdAt') or '',
        )
        baseline = (pair.get('runs') or {}).get('baseline') or {}
        rsi = (pair.get('runs') or {}).get('rsi') or {}
        baseline_tokens = _total(baseline.get('metrics'))
        rsi_tokens = _total(rsi.get('metrics'))
        return {
            'available': True,
            'workpack': public_spec,
            'experiment': {
                'id': item['id'],
                'mode': item.get('mode'),
                'finishedAt': item.get('finishedAt'),
                'limits': deepcopy((item.get('protocol') or {}).get('limits') or {}),
                'qualityGate': deepcopy((summary or {}).get('qualityGate') or self._quality_gate(item, summary)),
            },
            'pair': self._dashboard_pair(pair),
            'comparison': {
                'baselineTokens': baseline_tokens,
                'rsiTokens': rsi_tokens,
                'tokenSavingRate': round(1 - rsi_tokens / baseline_tokens, 6) if baseline_tokens else None,
                'sameFrozenInput': True,
                'note': '保存的 V17 串行双臂回放；不是当前工作区刚发起的实时 A/B 运行。',
            },
        }

    def list_summaries(self) -> list[dict]:
        """List experiments without downloading pair traces, reports, or raw events."""
        rows = []
        for key in sorted(self.items, reverse=True):
            item = self.get(key)
            rows.append({
                name: deepcopy(item.get(name)) for name in [
                    'id', 'mode', 'status', 'createdAt', 'startedAt', 'finishedAt', 'error',
                ]
            } | {
                'protocol': {
                    name: deepcopy((item.get('protocol') or {}).get(name)) for name in [
                        'id', 'mode', 'taskCountPerArm', 'agentRuns', 'limits', 'model',
                    ]
                },
                'summary': {
                    name: deepcopy((item.get('summary') or {}).get(name)) for name in [
                        'pairedCompleted', 'tokenSavingRate', 'learning', 'qualityGate',
                    ]
                },
            })
        return rows

    def list(self) -> list[dict]:
        """Compatibility method for local callers that still need the raw ledger."""
        return [self.get(key) for key in sorted(self.items, reverse=True)]

    def run(self, item_id: str, arm: str, run_id: str) -> dict:
        if arm not in ['baseline', 'rsi']:
            raise KeyError(run_id)
        item = self.get(item_id)
        if not any(pair.get('runs', {}).get(arm, {}).get('id') == run_id for pair in item.get('pairs') or []):
            raise KeyError(run_id)
        path = self.root / item_id / arm / 'runs' / f'{run_id}.json'
        if not path.exists():
            raise KeyError(run_id)
        return json.loads(path.read_text(encoding='utf-8'))

    def run_with_task(self, item_id: str, arm: str, run_id: str) -> tuple[dict, dict]:
        run = self.run(item_id, arm, run_id)
        manager = WorkspaceManager(self.root / item_id / arm)
        manager.restore()
        return run, manager.task(run['taskId'])

    def cancel(self, item_id: str) -> bool:
        """Persist cancellation and stop at most the currently active Agent run.

        The outer controller deliberately does not depend on cancellation
        propagation through a nested TaskRunner: that runner can finalize its
        own cancellation and return normally.  The persisted flag is checked
        before every pair and arm, so a cancellation cannot advance to another
        task even in that case.
        """
        if item_id not in self.items:
            self.get(item_id)
        item = self.items[item_id]
        if item.get('status') in ['completed', 'cancelled', 'interrupted', 'failed']:
            return False
        if not item.get('cancelRequested'):
            item.update(cancelRequested=True, cancelRequestedAt=now())
            item['events'].append({'at': now(), 'kind': 'cancel_requested',
                                   'reason': '停止当前 Agent 并禁止启动后续 pair 或 arm'})
            self._save(item)
        active = self.active_runs.get(item_id)
        if active:
            runner, run_id = active
            job = runner.tasks.get(run_id)
            if job:
                job.cancel()
        return True

    async def shutdown(self) -> None:
        for item_id in list(self.tasks):
            self.cancel(item_id)
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        for runners in self.runners.values():
            for runner in runners.values():
                await runner.shutdown()
