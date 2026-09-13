"""Separate-cost, order-swapped judging for saved workspace workpack reports.

The Judge reads only reports and evidence already observed in the two saved
Agent traces.  It never reads private workpack validation, changes the online
experience store, or mutates the original experiment artifact.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import random
import time
from pathlib import Path
from uuid import uuid4

from jsonschema import ValidationError

from . import config
from .autotool import canonical, digest
from .domain import now
from .graph_store import write_private
from .llm_judge import JUDGE_PROMPT, WEIGHTS, aggregate_verdicts, report_reward, verdict_tool
from .model_client import ModelClient, ModelOptions


MAX_INPUT_CHARS = 200_000


def _public_task(task: dict) -> dict:
    """Exclude private validator/gold-like fields from a judge payload."""
    return {key: deepcopy(task[key]) for key in ['scenario', 'title', 'task', 'asOf', 'clarifications'] if key in task}


def _walk_refs(value, refs: set[str]) -> None:
    if isinstance(value, dict):
        reference = value.get('_evidenceRef')
        if isinstance(reference, str) and reference.startswith('workspace:'):
            refs.add(reference)
        for child in value.values():
            _walk_refs(child, refs)
    elif isinstance(value, list):
        for child in value:
            _walk_refs(child, refs)


def _observed_refs(run: dict) -> set[str]:
    refs: set[str] = set()
    for event in run.get('events') or []:
        detail = event.get('detail') or {}
        _walk_refs(detail, refs)
        if event.get('type') == 'report_evidence':
            for reference in detail.get('requiredEvidenceIds') or []:
                if isinstance(reference, str) and reference.startswith('workspace:'):
                    refs.add(reference)
    return refs


def _workspace_evidence(manager, refs: set[str]) -> dict[str, dict]:
    """Resolve only trace-observed references into readable evidence rows."""
    rows = {}
    for workspace in manager.workspaces.values():
        for table in workspace.get('tables', {}).values():
            for row in table.get('rows', []):
                reference = f'workspace:{workspace["id"]}:{row["rowId"]}'
                if reference in refs:
                    rows[reference] = {'source': table['sheet'], 'rowId': row['rowId'],
                                       'values': deepcopy(row['values'])}
    return dict(sorted(rows.items()))


class WorkpackJudge:
    """Runs one saved batch per workpack experiment, sequentially and visibly."""

    def __init__(self, experiments, root: Path, provider_factory=None):
        self.experiments = experiments
        self.root = Path(root) / 'artifacts' / 'workpack-judgements'
        self.factory = provider_factory
        self.items: dict[str, dict] = {}
        self.tasks: dict[str, asyncio.Task] = {}

    def _path(self, key: str) -> Path:
        return self.root / f'{key}.json'

    def _input_path(self, key: str, pair_index: int) -> Path:
        return self.root / 'inputs' / key / f'{pair_index:02d}.json'

    def _save(self, item: dict) -> None:
        write_private(self._path(item['id']), item)

    def restore(self) -> None:
        if not self.root.exists():
            return
        for path in self.root.glob('*.json'):
            try:
                item = json.loads(path.read_text(encoding='utf-8'))
                if item.get('id') != path.stem:
                    continue
                if item.get('status') in ['queued', 'running']:
                    item.update(status='interrupted', finishedAt=now(),
                                error='服务重启；保留已完成裁判和已消耗用量，不自动续跑')
                    item['metrics']['usageComplete'] = False
                    self._save(item)
                self.items[item['id']] = item
            except (OSError, ValueError, TypeError, KeyError):
                continue

    def provider(self):
        return self.factory() if self.factory else ModelClient(ModelOptions(
            config.JUDGE_BASE_URL, config.JUDGE_API_KEY, config.JUDGE_MODEL, config.MODEL_TIMEOUT))

    def protocol(self, experiment_id: str) -> dict:
        experiment = self.experiments.get(experiment_id)
        pairs = experiment.get('pairs') or []
        eligible = sum(bool((pair.get('runs', {}).get('baseline') or {}).get('submission')) and
                       bool((pair.get('runs', {}).get('rsi') or {}).get('submission')) for pair in pairs)
        return {
            'experimentId': experiment_id,
            'pairCount': len(pairs),
            'eligiblePairs': eligible,
            'notScoredMissingReport': len(pairs) - eligible,
            'normalModelRequests': eligible * 2,
            'maximumModelRequestsWithOneFormatRepairPerOrder': eligible * 4,
            'inputEvidence': 'union_of_rows_observed_in_saved_baseline_and_rsi_traces',
            'judgeCost': 'separate_from_agent_cost',
            'order': 'anonymous_A_B_and_B_A',
            'sameModelMustBeDisclosed': True,
        }

    def _pair_payload(self, experiment_id: str, pair: dict) -> tuple[dict, dict]:
        reports = {}
        evidence = {}
        public_task = None
        for arm in ['baseline', 'rsi']:
            run_row = pair.get('runs', {}).get(arm) or {}
            if not run_row.get('submission'):
                raise ValueError('missing_report')
            run, task = self.experiments.run_with_task(experiment_id, arm, run_row['id'])
            public_task = public_task or _public_task(task)
            submission = run.get('submission') or {}
            reports[arm] = {key: deepcopy(submission.get(key)) for key in ['metrics', 'selectedIds', 'evidenceIds', 'summary']}
            refs = _observed_refs(run)
            evidence.update(_workspace_evidence(self._manager(experiment_id, arm), refs))
        payload = {'task': public_task, 'evidence': dict(sorted(evidence.items()))}
        if len(canonical(dict(payload, reports=reports))) > MAX_INPUT_CHARS:
            raise ValueError('input_too_large')
        return payload, reports

    def _manager(self, experiment_id: str, arm: str):
        # ``run_with_task`` restores a fresh manager internally. Reuse the
        # same public file-backed source, still read-only, to map observed refs.
        from .workspace import WorkspaceManager
        manager = WorkspaceManager(self.experiments.root / experiment_id / arm)
        manager.restore()
        return manager

    @staticmethod
    def _same_as_executor(experiment: dict, model: str | None) -> bool:
        observed = {
            (run.get('models') or {}).get('executor')
            for pair in experiment.get('pairs') or []
            for run in (pair.get('runs') or {}).values()
            if run
        }
        return bool(observed) and observed == {model}

    @staticmethod
    def _summary(item: dict) -> dict:
        completed = [row for row in item.get('pairs') or [] if row.get('status') == 'completed' and row.get('result')]
        not_scored = [row for row in item.get('pairs') or [] if row.get('status', '').startswith('not_scored')]
        failed = [row for row in item.get('pairs') or [] if row.get('status') == 'failed']
        scores = {}
        for arm in ['baseline', 'rsi']:
            if completed:
                dimensions = {key: round(sum(row['result']['reports'][arm]['dimensions'][key] for row in completed) / len(completed), 4)
                              for key in WEIGHTS}
                scores[arm] = {'dimensions': dimensions, 'reward': report_reward(dimensions)}
            else:
                scores[arm] = None
        return {
            'eligiblePairs': len(completed) + len(failed),
            'completedPairs': len(completed),
            'failedPairs': len(failed),
            'notScoredPairs': len(not_scored),
            'notScoredReasons': {reason: sum(row.get('reason') == reason for row in not_scored)
                                 for reason in sorted({row.get('reason') for row in not_scored})},
            'orderDisagreements': sum(not row['result'].get('orderConsistent') for row in completed),
            'reports': scores,
            'note': ('只汇总完成双顺序裁判的报告。缺报告或 provider/格式失败保留，不以零分或重试替代；'
                     'Judge reward 不覆盖 Agent 的确定性事实校验。'),
        }

    def get(self, key: str) -> dict:
        if key not in self.items:
            path = self._path(key)
            if not path.exists():
                raise KeyError(key)
            self.items[key] = json.loads(path.read_text(encoding='utf-8'))
        return deepcopy(self.items[key])

    def list(self, experiment_id: str) -> list[dict]:
        return [self.get(key) for key in sorted(self.items) if self.items[key].get('experimentId') == experiment_id]

    async def start(self, experiment_id: str) -> dict:
        if self.tasks or self.experiments.tasks:
            raise ValueError('请等待 Agent 实验或现有 Judge 结束')
        experiment = self.experiments.get(experiment_id)
        if experiment.get('status') != 'completed':
            raise ValueError('只有完成的 Agent 实验可启动独立 Judge')
        provider = self.provider()
        matching = next((item for item in self.items.values()
                         if item.get('experimentId') == experiment_id and item.get('model') == provider.model
                         and item.get('rubricHash') == digest(JUDGE_PROMPT)), None)
        if matching:
            return deepcopy(matching)
        protocol = self.protocol(experiment_id)
        item = {
            'id': str(uuid4()), 'experimentId': experiment_id, 'status': 'queued', 'createdAt': now(),
            'model': provider.model, 'sameAsExecutor': self._same_as_executor(experiment, provider.model),
            'rubricHash': digest(JUDGE_PROMPT), 'weights': deepcopy(WEIGHTS), 'scoreScale': [0, 10],
            'protocol': protocol, 'pairs': [], 'metrics': {
                'modelRequests': 0, 'inputTokens': 0, 'outputTokens': 0, 'usageComplete': True,
                'durationMs': 0, 'normalRequestBudget': protocol['normalModelRequests'],
                'maximumRequestBudget': protocol['maximumModelRequestsWithOneFormatRepairPerOrder'],
            }, 'summary': {},
        }
        self.items[item['id']] = item
        self._save(item)

        async def work():
            started = time.monotonic()
            item.update(status='running', startedAt=now())
            self._save(item)
            try:
                for pair in experiment.get('pairs') or []:
                    row = {'pairIndex': pair['index'], 'workpackId': pair['workpackId']}
                    if not (pair.get('runs', {}).get('baseline') or {}).get('submission') or not (pair.get('runs', {}).get('rsi') or {}).get('submission'):
                        row.update(status='not_scored_missing_report', reason='missing_report')
                        item['pairs'].append(row)
                        self._save(item)
                        continue
                    try:
                        payload, reports = self._pair_payload(experiment_id, pair)
                    except ValueError as error:
                        row.update(status='not_scored_input_too_large' if str(error) == 'input_too_large' else 'not_scored_missing_report',
                                   reason=str(error))
                        item['pairs'].append(row)
                        self._save(item)
                        continue
                    row.update(status='running', task=payload['task'], inputHash=digest(dict(payload, reports=reports)),
                               mappings=[], passes=[], result=None)
                    item['pairs'].append(row)
                    write_private(self._input_path(item['id'], pair['index']), {'payload': payload, 'reports': reports})
                    self._save(item)
                    try:
                        order = ['baseline', 'rsi']
                        random.SystemRandom().shuffle(order)
                        row['mappings'] = [dict(zip(['A', 'B'], order)), dict(zip(['A', 'B'], reversed(order)))]
                        for mapping in row['mappings']:
                            entry = {'mapping': mapping, 'attempts': []}
                            row['passes'].append(entry)
                            tool = verdict_tool()
                            history = [
                                {'role': 'system', 'content': JUDGE_PROMPT},
                                {'role': 'user', 'content': canonical({'task': payload['task'], 'evidence': payload['evidence'],
                                                                        'reports': {label: reports[arm] for label, arm in mapping.items()}})},
                            ]
                            verdict = None
                            for attempt in range(2):
                                item['metrics']['modelRequests'] += 1
                                try:
                                    response = await provider.complete(history, [tool])
                                except BaseException:
                                    item['metrics']['usageComplete'] = False
                                    raise
                                usage = response.get('usage')
                                entry['attempts'].append({'response': deepcopy(response['message']), 'usage': usage})
                                if usage:
                                    item['metrics']['inputTokens'] += int(usage.get('input') or 0)
                                    item['metrics']['outputTokens'] += int(usage.get('output') or 0)
                                else:
                                    item['metrics']['usageComplete'] = False
                                calls = response['message'].get('tool_calls') or []
                                if response.get('finishReason') in ['length', 'content_filter'] or len(calls) != 1 or calls[0]['function']['name'] != tool.name:
                                    raise ValueError('裁判未返回完整的一次结构化评分')
                                try:
                                    verdict = json.loads(calls[0]['function']['arguments'])
                                    tool.validator.validate(verdict)
                                    break
                                except (ValueError, ValidationError) as error:
                                    entry['attempts'][-1]['formatError'] = str(error)[:500]
                                    if attempt:
                                        raise ValueError('裁判格式修正后仍不符合 schema') from error
                                    history.extend([response['message'], {
                                        'role': 'tool', 'tool_call_id': calls[0]['id'],
                                        'content': '格式不符合 schema；请重新提交。findings 必须为含 A/B 的原生对象；evidenceRef 是单个字符串。',
                                    }])
                                    self._save(item)
                            if any(finding['evidenceRef'] and finding['evidenceRef'] not in payload['evidence']
                                   for finding in verdict['findings'].values()):
                                raise ValueError('裁判引用了不存在的已观察证据')
                            scores = {mapping[label]: verdict[label] for label in ['A', 'B']}
                            rewards = {arm: report_reward(values) for arm, values in scores.items()}
                            entry.update(status='completed', verdict=verdict, scores=scores, rewards=rewards,
                                         winner=mapping['A'] if rewards[mapping['A']] > rewards[mapping['B']]
                                         else mapping['B'] if rewards[mapping['B']] > rewards[mapping['A']] else 'tie')
                            self._save(item)
                        row['result'] = aggregate_verdicts(row['passes'])
                        row['status'] = 'completed'
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        row.update(status='failed', error=str(error)[:1000])
                    self._save(item)
            except asyncio.CancelledError:
                item.update(status='cancelled', error='Judge 已取消；保留已消耗费用与已完成 pair')
                item['metrics']['usageComplete'] = False
            except Exception as error:
                item.update(status='failed', error=str(error)[:1000])
            finally:
                if item.get('status') == 'running':
                    item['status'] = 'completed'
                item['metrics']['durationMs'] = round((time.monotonic() - started) * 1000, 3)
                item['finishedAt'] = now()
                item['summary'] = self._summary(item)
                self._save(item)
                self.tasks.pop(item['id'], None)

        self.tasks[item['id']] = asyncio.create_task(work())
        return deepcopy(item)

    async def shutdown(self) -> None:
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
