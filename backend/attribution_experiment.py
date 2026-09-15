"""Small serial experiment isolating cross-task trajectory learning."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from uuid import UUID, uuid4

from . import config
from .attribution_assets import VERSION, build, install
from . import cross_domain_attribution_assets
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


def _actual_graph_use(run):
    evolution = run.get('evolution') or {}
    selected = evolution.get('usedVersionId') or evolution.get('usedVersionIds')
    return bool(selected) and (
        any(trace.get('ok') and trace.get('executor') == 'graph' for trace in run.get('toolTrace', []))
        or any(state in {'done', 'completed'} for state in (run.get('graph') or {}).get('nodeStates', {}).values())
    )


def campaign_gate_snapshot(item, task_ids):
    wanted = set(task_ids)
    pairs = [pair for pair in item.get('pairs') or [] if (pair.get('spec') or {}).get('id') in wanted]
    expected = len(task_ids)
    complete_pairs = len(pairs) == expected and all(
        pair.get('status') == 'completed' and all(pair.get(arm) for arm in ARMS)
        for pair in pairs
    )
    usage_complete = complete_pairs and all(
        (pair[arm].get('metrics') or {}).get('usageComplete') is True
        for pair in pairs for arm in ARMS
    )
    maintenance_clean = complete_pairs and all(
        not (pair[arm].get('evolution') or {}).get('maintenanceError')
        for pair in pairs for arm in ARMS
    )
    online_passed = sum(
        pair['online_rsi'].get('status') == 'completed'
        and (pair['online_rsi'].get('evaluation') or {}).get('status') == 'passed'
        for pair in pairs if pair.get('online_rsi')
    )
    graph_hits = sum(_actual_graph_use(pair['online_rsi']) for pair in pairs if pair.get('online_rsi'))
    graph_rate = graph_hits / expected if expected else None
    minimum = float((item.get('protocol') or {}).get('actualGraphUseMinimumRate') or 0)
    graph_gate = graph_rate is not None and graph_rate >= minimum
    passed = complete_pairs and usage_complete and maintenance_clean and online_passed == expected and graph_gate
    return {
        'taskIds': list(task_ids), 'expectedPairs': expected, 'completedPairs': len(pairs),
        'usageComplete': usage_complete, 'maintenanceClean': maintenance_clean,
        'onlineRsiPassed': online_passed,
        'actualGraphUse': {'hits': graph_hits, 'attempts': expected, 'rate': graph_rate, 'minimumRate': minimum, 'met': graph_gate},
        'expansionGate': passed,
    }


def summarize(item):
    arm_summary = {}
    for arm in ARMS:
        runs = [pair[arm] for pair in item.get('pairs') or [] if pair.get(arm)]
        metrics = [run.get('metrics') or {} for run in runs]
        execution_stages = {}
        for run in runs:
            for stage, values in (run.get('executionStageMetrics') or {}).items():
                target = execution_stages.setdefault(stage, {'requests': 0, 'inputTokens': 0, 'outputTokens': 0, 'usageComplete': True})
                target['requests'] += int(values.get('requests') or 0)
                target['inputTokens'] += int(values.get('inputTokens') or 0)
                target['outputTokens'] += int(values.get('outputTokens') or 0)
                target['usageComplete'] = target['usageComplete'] and values.get('usageComplete') is True
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
            'executionStages': execution_stages,
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
    online_runs = [pair.get('online_rsi') or {} for pair in item.get('pairs') or [] if pair.get('online_rsi')]
    graph_uses = [run for run in online_runs if _actual_graph_use(run)]
    minimum_use_rate = (item.get('protocol') or {}).get('actualGraphUseMinimumRate')
    actual_use_rate = len(graph_uses) / len(online_runs) if online_runs else None
    use_gate = minimum_use_rate is None or (actual_use_rate is not None and actual_use_rate >= minimum_use_rate)
    complete_usage = protocol_complete and all(
        arm_summary[arm]['attempts'] == expected and arm_summary[arm]['usageComplete']
        for arm in ARMS
    )
    quality = complete_usage and use_gate and all(
        arm_summary[arm]['passed'] == expected for arm in ARMS
    )
    # Cross-domain expansion may proceed when the learned system itself is
    # fully reliable and the baseline's ordinary business failures remain in
    # the comparison. This does not unlock same-quality cost claims.
    expansion_gate = (complete_usage and use_gate
                      and arm_summary['online_rsi']['passed'] == expected)
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
        'expansionGate': expansion_gate,
        'comparativeConclusionAllowed': complete_usage and item.get('mode') == 'cross_domain_formal',
        'costConclusionAllowed': quality and item.get('mode') in {'formal', 'cross_domain_formal'},
        'netTokenSaving': (1 - arm_summary['online_rsi']['tokens'] / arm_summary['no_learning']['tokens']) if arm_summary['no_learning']['tokens'] else None,
        'netLatencySaving': (1 - arm_summary['online_rsi']['durationMs'] / arm_summary['no_learning']['durationMs']) if arm_summary['no_learning']['durationMs'] else None,
        'actualGraphUse': {
            'hits': len(graph_uses), 'attempts': len(online_runs), 'rate': actual_use_rate,
            'minimumRate': minimum_use_rate, 'met': use_gate,
        },
        'campaign': deepcopy(item.get('campaign')) if item.get('campaign') else None,
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
                    pair[arm] = {name: deepcopy(pair[arm].get(name)) for name in ['id', 'status', 'metrics', 'phaseMetrics', 'executionStageMetrics', 'evaluation', 'evolution', 'error', 'submission']}
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
        allowed = {'smoke', 'probe', 'repair_probe', 'formal', 'cross_domain_smoke', 'cross_domain_probe', 'cross_domain_formal'}
        if mode not in allowed:
            raise ValueError('unknown attribution stage')
        if self.tasks:
            raise ValueError('已有归因实验在途')
        self._validate_model()
        cross_domain = mode.startswith('cross_domain_')
        asset_version = cross_domain_attribution_assets.VERSION if cross_domain else VERSION
        asset_builder = cross_domain_attribution_assets.build if cross_domain else build
        asset_installer = cross_domain_attribution_assets.install if cross_domain else install
        asset = asset_builder(self.root)
        runtime = fingerprint(self.root)
        predecessor = None
        campaign_stage1, campaign_stage2, campaign_stage3 = (
            cross_domain_attribution_assets.campaign_plan(asset['tasks'])
            if cross_domain else ([], [], [])
        )
        formal_mode = 'cross_domain_formal' if cross_domain else 'formal'
        probe_mode = 'cross_domain_probe' if cross_domain else 'probe'
        if mode == formal_mode and not cross_domain:
            predecessor = next((
                item for item in reversed(list(self.items.values()))
                if item.get('mode') == probe_mode and item.get('assetVersion') == asset_version
                and item.get('fingerprint') == runtime
                and summarize(item)['qualityGate']
            ), None)
            if not predecessor:
                raise ValueError('同一 runtime 与资产的双任务预检未通过，禁止启动正式归因实验')
        if mode == 'repair_probe':
            # Minimal natural chain: create the order-review parent, recover the
            # payment-period coverage extension, then test its later use.
            manifest = deepcopy([asset['tasks'][index] for index in (0, 8, 9)])
        elif mode == 'cross_domain_smoke':
            # Finance has already passed the same shared delivery chain. Spend the
            # smoke budget only on the two newly introduced scenarios.
            manifest = deepcopy([
                row for row in asset['tasks']
                if row.get('scenario') in {'support', 'tickets'} and row.get('scenarioPosition') == 1
            ])
        elif mode == 'cross_domain_probe':
            manifest = deepcopy(campaign_stage1)
        elif mode == 'cross_domain_formal':
            # Both stages are fixed before any result exists. The second stage
            # stays dormant until the first stage passes its expansion gate.
            manifest = deepcopy(campaign_stage1 + campaign_stage2)
        else:
            task_limit = {'smoke': 1, 'probe': 2}.get(mode, len(asset['tasks']))
            manifest = deepcopy(asset['tasks'][:task_limit])
        key = str(uuid4())
        directory = self.directory / key
        item = {
            'id': key,
            'mode': mode,
            'status': 'running',
            'createdAt': now(),
            'assetVersion': asset_version,
            'fingerprint': runtime,
            'manifest': manifest,
            'pairs': [],
            'predecessorId': predecessor['id'] if predecessor else None,
            'campaign': ({
                'kind': 'staged-12-plus-12-plus-24',
                'status': 'running_to_24',
                'initialTargetPairs': 24,
                'maximumTargetPairs': 48,
                'stage1': {'status': 'running', 'taskIds': [row['id'] for row in campaign_stage1]},
                'stage2': {'status': 'frozen_waiting_for_gate', 'taskIds': [row['id'] for row in campaign_stage2]},
                'stage3': {'status': 'frozen_waiting_for_explicit_expansion', 'taskIds': [row['id'] for row in campaign_stage3]},
                'allTaskIds': [row['id'] for row in campaign_stage1 + campaign_stage2 + campaign_stage3],
                'gatePolicy': 'stage1 online_rsi passes 12/12, usage and maintenance complete, actual graph use meets the frozen minimum',
                'selectionPolicy': 'all three stages frozen before execution; later stages never selected from earlier outcomes',
            } if mode == 'cross_domain_formal' else None),
            'protocol': {
                'id': ('finance-graph-rsi-error-recovery-probe-v1' if mode == 'repair_probe'
                       else 'cross-domain-graph-rsi-learning-attribution-v2-staged-24' if mode == 'cross_domain_formal'
                       else 'cross-domain-graph-rsi-learning-attribution-v1' if cross_domain
                       else 'finance-graph-rsi-learning-attribution-v5-12'),
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
                'actualGraphUseMinimumRate': (None if mode in {'smoke', 'cross_domain_smoke'} else 0.50),
                'actualGraphUsePolicy': 'count only a saved version that is selected and has graph-executor nodes completed; partial reuse qualifies, version load alone does not',
                'smokePolicy': ('one cold-start pair only; excluded from formal metrics' if mode == 'smoke'
                                else 'two new-domain capability pairs (support C01 and tickets T01); excluded from learning and formal conclusions' if mode == 'cross_domain_smoke'
                                else 'cold-start plus first reuse/rebind pair; excluded from formal metrics' if mode == 'probe'
                                else 'twelve frozen pairs across finance, support and tickets; excluded from formal metrics' if mode == 'cross_domain_probe'
                                else 'FX01 creates the parent; FX09 exercises the coverage extension and bounded report recovery; FX10 tests later use; excluded from formal metrics' if mode == 'repair_probe'
                                else 'one campaign: frozen 12-pair gate followed by 12 frozen demo pairs; optional explicit continuation uses the remaining 24 frozen pairs without rerunning earlier work' if cross_domain
                                else 'formal frozen twelve-task finance chain'),
                'failurePolicy': ('retain all attempts; cross-domain probe/formal continue ordinary business failures and stop only on runtime mutation, usage loss or maintenance failure' if cross_domain else 'retain all attempts; formal continues business failures and stops only on runtime mutation, usage loss or maintenance failure'),
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
                    workspace, task = asset_installer(manager, self.root, spec)
                    pair = {'index': index + 1, 'stage': spec.get('campaignStage'), 'spec': spec,
                            'workspaceId': workspace['id'], 'taskId': task['id'], 'status': 'running'}
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
                    if mode in {'smoke', 'probe', 'repair_probe', 'cross_domain_smoke'} and any(
                        pair[arm].get('status') != 'completed' or (pair[arm].get('evaluation') or {}).get('status') != 'passed'
                        for arm in ARMS
                    ):
                        item['status'] = 'quality_stopped'
                        break
                    if infrastructure_failure:
                        item['status'] = 'infrastructure_stopped'
                        if item.get('campaign') and spec.get('campaignStage') in {1, 2}:
                            item['campaign'][f'stage{spec["campaignStage"]}']['status'] = 'infrastructure_stopped'
                            item['campaign']['status'] = f'stopped_in_stage{spec["campaignStage"]}'
                        break
                    if (mode == 'cross_domain_formal' and spec.get('campaignStage') == 1
                            and index + 1 == len(campaign_stage1)):
                        gate = campaign_gate_snapshot(item, item['campaign']['stage1']['taskIds'])
                        item['campaign']['stage1'].update(status='completed', gate=gate)
                        if not gate['expansionGate']:
                            item['campaign']['stage2']['status'] = 'blocked_by_stage1_gate'
                            item['campaign']['status'] = 'stopped_at_12'
                            item['status'] = 'gate_stopped'
                            self.save(item)
                            break
                        item['campaign']['stage2']['status'] = 'running'
                        self.save(item)
                else:
                    item['status'] = 'completed'
                    if item.get('campaign'):
                        item['campaign']['stage2']['status'] = 'completed'
                        item['campaign']['status'] = 'completed_24'
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

    async def continue_campaign(self, key, target_pairs=48):
        if target_pairs != 48:
            raise ValueError('跨场景 campaign 续跑目标只支持48对')
        if self.tasks:
            raise ValueError('已有归因实验在途')
        self._validate_model()
        if key not in self.items:
            raise KeyError(key)
        item = self.items[key]
        campaign = item.get('campaign') or {}
        if item.get('mode') != 'cross_domain_formal' or item.get('status') != 'completed':
            raise ValueError('只有已完成24对的跨场景正式 campaign 可以续跑')
        if campaign.get('status') == 'expanded_to_48':
            raise ValueError('跨场景 campaign 已完成48对')
        if campaign.get('stage1', {}).get('status') != 'completed' or campaign.get('stage2', {}).get('status') != 'completed':
            raise ValueError('跨场景 campaign 前24对尚未完成')
        existing_ids = [(pair.get('spec') or {}).get('id') for pair in item.get('pairs') or []]
        first_24 = campaign.get('stage1', {}).get('taskIds', []) + campaign.get('stage2', {}).get('taskIds', [])
        if (len(existing_ids) != 24 or len(set(existing_ids)) != 24 or existing_ids != first_24
                or any(pair.get('status') != 'completed' or any(not pair.get(arm) for arm in ARMS)
                       for pair in item.get('pairs') or [])):
            raise ValueError('跨场景 campaign 前24对记录不完整或顺序已变化')
        if [row.get('id') for row in item.get('manifest') or []] != first_24:
            raise ValueError('跨场景 campaign 活动清单不再是冻结的前24对')
        runtime = item.get('fingerprint')
        if fingerprint(self.root) != runtime:
            raise ValueError('runtime changed after freeze')
        directory = self.directory / key
        frozen_path = directory / 'frozen-assets-manifest.json'
        if not frozen_path.is_file():
            raise ValueError('缺少实验创建时冻结的跨场景资产清单')
        frozen_asset = json.loads(frozen_path.read_text())
        if frozen_asset.get('version') != item.get('assetVersion'):
            raise ValueError('冻结资产版本与 campaign 不一致')
        stage1, stage2, stage3 = cross_domain_attribution_assets.campaign_plan(frozen_asset.get('tasks') or [])
        frozen_order = [row['id'] for row in stage1 + stage2 + stage3]
        if frozen_order != campaign.get('allTaskIds'):
            raise ValueError('冻结 campaign 顺序与初始实验不一致')
        stage3_ids = campaign.get('stage3', {}).get('taskIds') or []
        if [row['id'] for row in stage3] != stage3_ids:
            raise ValueError('冻结 stage3 与初始实验不一致')
        if set(stage3_ids) & set(existing_ids):
            raise ValueError('stage3 与已执行任务重叠')
        for spec in stage3:
            cross_domain_attribution_assets.verify_task_files(self.root, spec)

        item['manifest'].extend(deepcopy(stage3))
        item['protocol']['taskCountPerArm'] = 48
        item['protocol']['taskOrder'] = list(frozen_order)
        item['status'] = 'running'
        campaign['status'] = 'expanding_to_48'
        campaign['stage3']['status'] = 'running'
        item.pop('finishedAt', None)
        item.pop('error', None)
        item.pop('summary', None)
        self.save(item)

        async def work():
            manager = WorkspaceManager(directory)
            manager.restore()
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
                for runner in runners.values():
                    runner.restore()
                if runners['no_learning'].evolution.versions:
                    raise ValueError('关闭学习臂读取了跨任务经验')
                for offset, spec in enumerate(stage3, start=24):
                    if fingerprint(self.root) != runtime:
                        raise ValueError('runtime changed after freeze')
                    cross_domain_attribution_assets.verify_task_files(self.root, spec)
                    workspace, task = cross_domain_attribution_assets.install(manager, self.root, spec)
                    pair = {'index': offset + 1, 'stage': 3, 'spec': spec,
                            'workspaceId': workspace['id'], 'taskId': task['id'], 'status': 'running'}
                    item['pairs'].append(pair)
                    self.save(item)
                    order = ARMS if offset % 2 == 0 else tuple(reversed(ARMS))
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
                    if infrastructure_failure:
                        item['status'] = 'infrastructure_stopped'
                        campaign['stage3']['status'] = 'infrastructure_stopped'
                        break
                else:
                    final_ids = [(pair.get('spec') or {}).get('id') for pair in item['pairs']]
                    if final_ids != frozen_order or len(set(final_ids)) != 48:
                        raise ValueError('48对 campaign 结果顺序或唯一性校验失败')
                    item['status'] = 'completed'
                    campaign['stage3']['status'] = 'completed'
                    campaign['status'] = 'expanded_to_48'
            except asyncio.CancelledError:
                item['status'] = 'cancelled'
                campaign['stage3']['status'] = 'cancelled'
            except Exception as error:
                item.update(status='failed', error=str(error)[:1200])
                campaign['stage3']['status'] = 'failed'
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
