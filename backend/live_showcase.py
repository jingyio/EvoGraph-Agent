"""Isolated, real-time comparison runs used only by the recording UI.

The live demonstration is intentionally separate from frozen evaluations.  It
uses train tasks or an explicitly marked showcase task, writes to its own
artifact tree and starts RSI with an empty experience store.  Showcase tasks
always run as one cold-start pair and never update experience.  Results are
replayable but never merged into a formal experiment summary.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import time
from uuid import uuid4

from .domain import now
from .graph_store import write_private
from .task_runner import TaskRunner, TaskRunRequest


class LiveShowcase:
    def __init__(self, bank, root: Path, provider_factory=None):
        self.bank = bank
        self.root = Path(root) / 'artifacts' / 'live-showcase'
        self.provider_factory = provider_factory
        self.items: dict[str, dict] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.runners: dict[str, dict[str, TaskRunner]] = {}

    def _path(self, item_id: str) -> Path:
        return self.root / item_id / 'session.json'

    @staticmethod
    def _compact(run: dict) -> dict:
        return {key: deepcopy(run.get(key)) for key in [
            'id', 'taskId', 'strategy', 'status', 'phase', 'createdAt', 'startedAt',
            'finishedAt', 'models', 'metrics', 'evaluation', 'evolution', 'runtimeOverhead',
            'error', 'graph', 'plan', 'submission', 'events', 'phaseMetrics',
        ]}

    @staticmethod
    def _total(metrics: dict | None) -> int:
        metrics = metrics or {}
        return int(metrics.get('inputTokens') or 0) + int(metrics.get('outputTokens') or 0)

    def _save(self, item: dict) -> None:
        write_private(self._path(item['id']), item)

    def _family_sequence(self, task_id: str, steps: int) -> list[str]:
        task = self.bank.task(task_id)
        if task.get('split') == 'showcase':
            if steps != 1:
                raise ValueError('进阶展示任务只运行单条冷启动对照，不建立或复用经验')
            return [task_id]
        if task.get('split') != 'train':
            raise ValueError('在线展示仅允许 train 或 showcase 任务，避免验证/测试数据进入 RSI 经验')
        peers = sorted(
            (row for row in self.bank.tasks.values()
             if row.get('split') == 'train' and row.get('scenario') == task['scenario'] and row.get('family') == task.get('family')),
            key=lambda row: row['id'],
        )
        index = next(index for index, row in enumerate(peers) if row['id'] == task_id)
        if steps == 1:
            return [task_id]
        if len(peers) < 2:
            raise ValueError('当前任务族没有两个不同的 train 实例')
        # Prefer current then its natural successor.  At the end of a family,
        # use the preceding task so the selected task remains the warm run.
        start = min(index, len(peers) - 2)
        return [row['id'] for row in peers[start:start + steps]]

    def _summary(self, item: dict) -> dict:
        result = {}
        for arm in ['baseline', 'rsi']:
            runs = [entry['runs'].get(arm) for entry in item['pairs'] if entry['runs'].get(arm)]
            metrics = [run.get('metrics') or {} for run in runs]
            result[arm] = {
                'attempts': len(runs),
                'passed': sum(run.get('status') == 'completed' and (run.get('evaluation') or {}).get('status') == 'passed' for run in runs),
                'totalTokens': sum(self._total(metric) for metric in metrics),
                'modelRequests': sum(int(metric.get('modelRequests') or 0) for metric in metrics),
                'toolCalls': sum(int(metric.get('toolCalls') or 0) for metric in metrics),
                'durationMs': round(sum(float(metric.get('durationMs') or 0) for metric in metrics), 3),
                'runtimeOverheadMs': round(sum(float(metric.get('runtimeOverheadMs') or 0) for metric in metrics), 3),
            }
        completed_pairs = [pair for pair in item['pairs'] if all(
            arm in pair.get('runs', {}) and pair['runs'][arm].get('status') not in ['queued', 'running']
            for arm in ['baseline', 'rsi'])]
        # A token difference has meaning only after the same task completed in
        # both arms. Do not show an apparent saving while the second arm is
        # merely queued or still streaming its real trace.
        if completed_pairs:
            base_tokens = sum(self._total(pair['runs']['baseline'].get('metrics')) for pair in completed_pairs)
            rsi_tokens = sum(self._total(pair['runs']['rsi'].get('metrics')) for pair in completed_pairs)
            base_requests = sum(int(pair['runs']['baseline'].get('metrics', {}).get('modelRequests') or 0) for pair in completed_pairs)
            rsi_requests = sum(int(pair['runs']['rsi'].get('metrics', {}).get('modelRequests') or 0) for pair in completed_pairs)
            result['tokenSavingRate'] = 1 - rsi_tokens / base_tokens if base_tokens else None
            result['modelRequestSavingRate'] = 1 - rsi_requests / base_requests if base_requests else None
        else:
            result['tokenSavingRate'] = None
            result['modelRequestSavingRate'] = None
        return result

    async def start(self, task_id: str, steps: int = 2) -> dict:
        if steps not in [1, 2]:
            raise ValueError('steps_must_be_1_or_2')
        sequence = self._family_sequence(task_id, steps)
        source_task = self.bank.task(task_id)
        is_showcase = source_task.get('split') == 'showcase'
        item_id = str(uuid4())
        directory = self.root / item_id
        baseline = TaskRunner(self.bank, self.provider_factory, run_limit=1, model_limit=1, read_limit=1,
                              run_directory=directory / 'baseline' / 'runs',
                              evolution_path=directory / 'baseline' / 'experience.json', learning_enabled=False)
        rsi = TaskRunner(self.bank, self.provider_factory, run_limit=1, model_limit=1, read_limit=1,
                         run_directory=directory / 'rsi' / 'runs',
                         evolution_path=directory / 'rsi' / 'experience.json', learning_enabled=not is_showcase)
        item = {
            'id': item_id,
            'status': 'queued',
            'createdAt': now(),
            'taskIds': sequence,
            'protocol': {
                'purpose': 'recording_demo_only_not_formal_evaluation',
                'split': source_task['split'],
                'runLimit': 1,
                'modelLimit': 1,
                'readLimit': 1,
                'baseline': 'plan_react_without_cross_task_learning',
                'rsi': ('graph_rsi_empty_isolated_cold_start_no_learning' if is_showcase
                        else 'graph_rsi_empty_isolated_experience_then_sequential_updates'),
                'judge': 'not_run',
                'shadowRollouts': 0,
                'model': None,
            },
            'events': [],
            'pairs': [dict(index=index, taskId=value, runs={}, status='pending') for index, value in enumerate(sequence)],
            'summary': self._summary(dict(pairs=[])),
        }
        self.items[item_id] = item
        self.runners[item_id] = {'baseline': baseline, 'rsi': rsi}
        self._save(item)

        async def work():
            item['status'] = 'running'
            item['startedAt'] = now()
            self._save(item)
            try:
                for pair in item['pairs']:
                    pair['status'] = 'running'
                    item['events'].append(dict(at=now(), kind='task_start', taskId=pair['taskId'], detail='同一 train 任务开始严格串行 Baseline → RSI'))
                    self._save(item)
                    # The two agents are intentionally sequential.  This keeps
                    # provider/model/read limits at one and prevents a shared
                    # service burst from being presented as an RSI advantage.
                    for arm, runner, strategy in [
                        ('baseline', baseline, 'plan_react'),
                        ('rsi', rsi, 'graph_rsi'),
                    ]:
                        item['events'].append(dict(at=now(), kind='arm_start', taskId=pair['taskId'], arm=arm, detail=strategy))
                        run = await runner.start(TaskRunRequest(taskId=pair['taskId'], strategy=strategy))
                        pair['runs'][arm] = self._compact(run)
                        item['protocol']['model'] = run.get('models', {}).get('executor')
                        item['summary'] = self._summary(item)
                        self._save(item)
                        await runner.tasks[run['id']]
                        pair['runs'][arm] = self._compact(run)
                        item['events'].append(dict(at=now(), kind='arm_finished', taskId=pair['taskId'], arm=arm,
                                                   detail=run.get('status'), runId=run['id']))
                        item['summary'] = self._summary(item)
                        self._save(item)
                    pair['status'] = 'completed'
                    rsi_run = pair['runs']['rsi']
                    item['events'].append(dict(at=now(), kind='task_finished', taskId=pair['taskId'],
                                               detail={'rsiPlanningPath': (rsi_run.get('evolution') or {}).get('planningPath'),
                                                       'usedWorkflowId': (rsi_run.get('evolution') or {}).get('usedVersionId')}))
                    item['summary'] = self._summary(item)
                    self._save(item)
                item['status'] = 'completed'
            except asyncio.CancelledError:
                item['status'] = 'cancelled'
                raise
            except Exception as error:
                item['status'] = 'failed'
                item['error'] = str(error)[:1000]
            finally:
                item['finishedAt'] = now()
                item['summary'] = self._summary(item)
                self._save(item)
                self.tasks.pop(item_id, None)

        self.tasks[item_id] = asyncio.create_task(work())
        return deepcopy(item)

    def get(self, item_id: str) -> dict:
        if item_id in self.items:
            return deepcopy(self.items[item_id])
        path = self._path(item_id)
        if not path.exists():
            raise KeyError(item_id)
        item = json.loads(path.read_text(encoding='utf-8'))
        self.items[item_id] = item
        return deepcopy(item)

    def run(self, item_id: str, arm: str, run_id: str) -> dict:
        if arm not in ['baseline', 'rsi']:
            raise KeyError(run_id)
        item = self.get(item_id)
        if not any(pair['runs'].get(arm, {}).get('id') == run_id for pair in item.get('pairs') or []):
            raise KeyError(run_id)
        path = self.root / item_id / arm / 'runs' / f'{run_id}.json'
        if not path.exists():
            raise KeyError(run_id)
        return json.loads(path.read_text(encoding='utf-8'))

    async def shutdown(self) -> None:
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        for runners in self.runners.values():
            for runner in runners.values():
                await runner.shutdown()
