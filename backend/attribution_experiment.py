"""Small serial experiment isolating cross-task trajectory learning."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from uuid import UUID, uuid4

from . import config
from .attribution_assets import VERSION, build, install
from .domain import now
from .graph_store import write_private
from .task_runner import TaskRunRequest, TaskRunner
from .trajectory_experiment import fingerprint
from .workspace import WorkspaceBank, WorkspaceManager


MODEL = 'qwen/qwen3.5-27b'
ARMS = ('no_learning', 'online_rsi')


def _tokens(run):
    metrics = run.get('metrics') or {}
    if metrics.get('usageComplete') is not True:
        return None
    return int(metrics.get('inputTokens') or 0) + int(metrics.get('outputTokens') or 0)


def summarize(item):
    arm_summary = {}
    for arm in ARMS:
        runs = [pair[arm] for pair in item.get('pairs') or [] if pair.get(arm)]
        metrics = [run.get('metrics') or {} for run in runs]
        arm_summary[arm] = {
            'attempts': len(runs),
            'passed': sum(run.get('status') == 'completed' and (run.get('evaluation') or {}).get('status') == 'passed' for run in runs),
            'usageComplete': all(metric.get('usageComplete') is True for metric in metrics),
            'inputTokens': sum(int(metric.get('inputTokens') or 0) for metric in metrics),
            'outputTokens': sum(int(metric.get('outputTokens') or 0) for metric in metrics),
            'modelRequests': sum(int(metric.get('modelRequests') or 0) for metric in metrics),
            'toolCalls': sum(int(metric.get('toolCalls') or 0) for metric in metrics),
            'toolErrors': sum(int(metric.get('toolErrors') or 0) for metric in metrics),
            'durationMs': round(sum(float(metric.get('durationMs') or 0) for metric in metrics), 3),
            'failedReportAttempts': sum(int(metric.get('failedReportAttempts') or 0) for metric in metrics),
        }
        arm_summary[arm]['tokens'] = arm_summary[arm]['inputTokens'] + arm_summary[arm]['outputTokens']
    points = []
    cumulative = {arm: {'tokens': 0, 'latency': 0.0} for arm in ARMS}
    token_chain_complete = True
    for pair in item.get('pairs') or []:
        if pair.get('status') != 'completed' or any(not pair.get(arm) for arm in ARMS):
            continue
        values = {arm: _tokens(pair[arm]) for arm in ARMS}
        if any(value is None for value in values.values()):
            token_chain_complete = False
        if token_chain_complete:
            for arm in ARMS:
                cumulative[arm]['tokens'] += values[arm]
        for arm in ARMS:
            cumulative[arm]['latency'] += float((pair[arm].get('metrics') or {}).get('durationMs') or 0)
        evolution = pair['online_rsi'].get('evolution') or {}
        points.append({
            'index': pair['spec']['position'],
            'taskId': pair['spec']['id'],
            'title': pair['spec']['title'],
            'opportunity': pair['spec']['opportunity'],
            'sourceTaskId': pair['spec']['sourceTaskId'],
            'status': pair['status'],
            'noLearning': pair['no_learning'],
            'onlineRsi': pair['online_rsi'],
            'usedVersionId': evolution.get('usedVersionId'),
            'usedVersionIds': evolution.get('usedVersionIds') or [],
            'generation': evolution.get('generation'),
            'matchVersion': evolution.get('matchVersion'),
            'generatedVersionIds': evolution.get('generatedVersionIds') or [],
            'generatedMatchVersions': evolution.get('generatedMatchVersions') or [],
            'tokenSaving': (1 - values['online_rsi'] / values['no_learning']) if all(value is not None for value in values.values()) and values['no_learning'] else None,
            'latencySaving': (1 - pair['online_rsi']['metrics']['durationMs'] / pair['no_learning']['metrics']['durationMs']) if pair['no_learning']['metrics']['durationMs'] else None,
            'cumulativeTokenSaving': (1 - cumulative['online_rsi']['tokens'] / cumulative['no_learning']['tokens']) if token_chain_complete and cumulative['no_learning']['tokens'] else None,
            'cumulativeLatencySaving': (1 - cumulative['online_rsi']['latency'] / cumulative['no_learning']['latency']) if cumulative['no_learning']['latency'] else None,
        })
    expected = len(item.get('manifest') or [])
    protocol_complete = item.get('status') == 'completed' and len(points) == expected
    quality = protocol_complete and all(
        arm_summary[arm]['attempts'] == expected
        and arm_summary[arm]['passed'] == expected
        and arm_summary[arm]['usageComplete']
        for arm in ARMS
    )
    versions = {version['id']: version for pair in item.get('pairs') or []
                for version in (pair.get('experienceAfter') or {}).get('onlineRsiVersions', [])}
    revision_ids = {key for key, version in versions.items() if version.get('parentGraphId') and version.get('generation', 0) > 0}
    revisions = [point for point in points if set(point['generatedVersionIds']) & revision_ids
                 or any(match.get('version', 0) > 0 for match in point['generatedMatchVersions'])]
    later_use, generated = [], set()
    for point in points:
        used = set(point['usedVersionIds'] or ([point['usedVersionId']] if point['usedVersionId'] else []))
        run = point['onlineRsi']
        actual = any(trace.get('ok') and trace.get('executor') == 'graph'
                     for trace in run.get('toolTrace', [])) or any(
                         state == 'completed' for state in (run.get('graph') or {}).get('nodeStates', {}).values())
        if used & generated and actual:
            later_use.append({'taskId': point['taskId'], 'versionIds': sorted(used & generated)})
        generated.update(point['generatedVersionIds'])
    return {
        'arms': arm_summary,
        'points': points,
        'protocolComplete': protocol_complete,
        'qualityGate': quality,
        'costConclusionAllowed': quality,
        'netTokenSaving': (1 - arm_summary['online_rsi']['tokens'] / arm_summary['no_learning']['tokens']) if arm_summary['no_learning']['tokens'] else None,
        'netLatencySaving': (1 - arm_summary['online_rsi']['durationMs'] / arm_summary['no_learning']['durationMs']) if arm_summary['no_learning']['durationMs'] else None,
        'learning': {
            'created': [point for point in points if point['generatedVersionIds'] and point['generation'] in (None, 0)],
            'revisions': revisions,
            'laterUse': later_use,
            'revisionWithLaterUse': any(set(use['versionIds']) & revision_ids for use in later_use),
        },
    }


class AttributionExperiment:
    def __init__(self, root):
        self.root = Path(root)
        self.directory = self.root / 'artifacts' / 'attribution-experiments'
        self.items = {}
        self.tasks = {}

    def restore(self):
        for path in self.directory.glob('*/experiment.json'):
            item = json.loads(path.read_text())
            if item.get('status') == 'running':
                item['status'] = 'interrupted'
            self.items[item['id']] = item

    def save(self, item):
        write_private(self.directory / item['id'] / 'experiment.json', item)

    def get(self, key):
        item = deepcopy(self.items[key])
        item['summary'] = summarize(item)
        return item

    def dashboard(self, key):
        item = self.get(key)
        for pair in item.get('pairs') or []:
            for arm in ARMS:
                if pair.get(arm):
                    pair[arm] = {name: deepcopy(pair[arm].get(name)) for name in ['id', 'status', 'metrics', 'phaseMetrics', 'evaluation', 'evolution', 'error', 'submission']}
        return item

    def run(self, key, arm, run_id):
        if key not in self.items or arm not in ARMS:
            raise KeyError(run_id)
        UUID(run_id)
        if not any((pair.get(arm) or {}).get('id') == run_id for pair in self.items[key].get('pairs') or []):
            raise KeyError(run_id)
        return json.loads((self.directory / key / arm / 'runs' / f'{run_id}.json').read_text())

    def task(self, key, run):
        manager = WorkspaceManager(self.directory / key)
        manager.restore()
        return manager.task(run['taskId'])

    def _validate_model(self):
        models = {config.MODEL, config.PLANNER_MODEL, config.COMPOSITION_MODEL}
        if models != {MODEL}:
            raise ValueError(f'归因实验要求执行、规划和组合统一使用 {MODEL}')

    async def start(self, mode='smoke'):
        if mode not in {'smoke', 'probe', 'formal'}:
            raise ValueError('unknown attribution stage')
        if self.tasks:
            raise ValueError('已有归因实验在途')
        self._validate_model()
        asset = build(self.root)
        runtime = fingerprint(self.root)
        predecessor = None
        if mode == 'formal':
            predecessor = next((
                item for item in reversed(list(self.items.values()))
                if item.get('mode') in {'smoke', 'probe'} and item.get('fingerprint') == runtime and summarize(item)['qualityGate']
            ), None)
            if not predecessor:
                raise ValueError('同一 runtime 的单对冒烟未通过，禁止启动正式六任务归因实验')
        task_limit = {'smoke': 1, 'probe': 2}.get(mode, len(asset['tasks']))
        manifest = deepcopy(asset['tasks'][:task_limit])
        key = str(uuid4())
        directory = self.directory / key
        item = {
            'id': key,
            'mode': mode,
            'status': 'running',
            'createdAt': now(),
            'assetVersion': VERSION,
            'fingerprint': runtime,
            'manifest': manifest,
            'pairs': [],
            'predecessorId': predecessor['id'] if predecessor else None,
            'protocol': {
                'id': 'finance-graph-rsi-learning-attribution-v4',
                'model': MODEL,
                'planner': MODEL,
                'composition': MODEL,
                'thinking': False,
                'computeInterface': 'granular-compute-v1',
                'maxModelRequestsPerRun': config.MAX_STEPS,
                'runTimeoutSeconds': config.RUN_TIMEOUT,
                'limits': {'run': 1, 'model': 1, 'read': 1},
                'taskCountPerArm': len(manifest),
                'taskOrder': [row['id'] for row in manifest],
                'armOrder': 'alternating per pair; same task order in each arm',
                'noLearning': 'graph_rsi with an empty isolated library; no cross-task reads or writes; cold plan and graph compile every task',
                'onlineRsi': 'same graph_rsi runtime from an independent empty library; learns only prior successful train tasks in this experiment',
                'shared': ['model', 'prompt', 'tools', 'cold planning', 'graph compilation', 'parameter binding', 'report recovery', 'budget', 'inputs'],
                'judge': 'not_run',
                'smokePolicy': ('one cold-start pair only; excluded from formal metrics' if mode == 'smoke'
                                else 'cold-start plus first reuse/rebind pair; excluded from formal metrics' if mode == 'probe'
                                else 'formal frozen six-task chain'),
                'failurePolicy': 'retain all attempts; formal continues business failures and stops only on runtime mutation, usage loss or maintenance failure',
            },
        }
        self.items[key] = item
        self.save(item)
        for relative in runtime['files']:
            write_private(directory / 'sources' / relative, (self.root / relative).read_text())
        write_private(directory / 'frozen-assets-manifest.json', asset)

        async def work():
            manager = WorkspaceManager(directory)
            bank = WorkspaceBank(manager)
            runners = {
                'no_learning': TaskRunner(bank, run_limit=1, model_limit=1, read_limit=1,
                                          learning_enabled=False, run_directory=directory / 'no_learning' / 'runs',
                                          evolution_path=directory / 'no_learning' / 'experience.json'),
                'online_rsi': TaskRunner(bank, run_limit=1, model_limit=1, read_limit=1,
                                        learning_enabled=True, run_directory=directory / 'online_rsi' / 'runs',
                                        evolution_path=directory / 'online_rsi' / 'experience.json'),
            }
            try:
                for index, spec in enumerate(manifest):
                    if fingerprint(self.root) != runtime:
                        raise ValueError('runtime changed after freeze')
                    if runners['no_learning'].evolution.versions:
                        raise ValueError('关闭学习臂读取了跨任务经验')
                    workspace, task = install(manager, self.root, spec)
                    pair = {'index': index + 1, 'spec': spec, 'workspaceId': workspace['id'], 'taskId': task['id'], 'status': 'running'}
                    item['pairs'].append(pair)
                    self.save(item)
                    order = ARMS if index % 2 == 0 else tuple(reversed(ARMS))
                    for arm in order:
                        runner = runners[arm]
                        run = await runner.start(TaskRunRequest(taskId=task['id'], strategy='graph_rsi'))
                        pair[arm] = run
                        self.save(item)
                        await runner.tasks[run['id']]
                        self.save(item)
                        if arm == 'no_learning' and runner.evolution.versions:
                            raise ValueError('关闭学习臂写入了跨任务经验')
                    pair['status'] = 'completed'
                    pair['experienceAfter'] = {
                        'noLearningVersions': len(runners['no_learning'].evolution.versions),
                        'onlineRsiVersions': [
                            {'id': version['id'], 'generation': version['generation'], 'matchVersion': version['matchVersion'],
                             'parentGraphId': version.get('parentGraphId'), 'sourceRunId': version.get('sourceRunId'),
                             'patches': deepcopy(version.get('patches') or []), 'matchPatches': deepcopy(version.get('matchPatches') or [])}
                            for version in runners['online_rsi'].evolution.versions
                        ],
                    }
                    self.save(item)
                    infrastructure_failure = any(
                        (pair[arm].get('metrics') or {}).get('usageComplete') is not True
                        or (pair[arm].get('evolution') or {}).get('maintenanceError')
                        for arm in ARMS
                    )
                    if mode in {'smoke', 'probe'} and any(
                        pair[arm].get('status') != 'completed' or (pair[arm].get('evaluation') or {}).get('status') != 'passed'
                        for arm in ARMS
                    ):
                        item['status'] = 'quality_stopped'
                        break
                    if infrastructure_failure:
                        item['status'] = 'infrastructure_stopped'
                        break
                else:
                    item['status'] = 'completed'
            except asyncio.CancelledError:
                item['status'] = 'cancelled'
            except Exception as error:
                item.update(status='failed', error=str(error)[:1200])
            finally:
                for runner in runners.values():
                    await runner.shutdown()
                item['finishedAt'] = now()
                item['summary'] = summarize(item)
                self.save(item)
                self.tasks.pop(key, None)

        self.tasks[key] = asyncio.create_task(work())
        return self.dashboard(key)

    async def shutdown(self):
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
