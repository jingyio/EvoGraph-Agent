"""Read-only analysis datasets pinned to immutable experiment artifacts.

The frontend never guesses the newest experiment. Each selectable dataset is
registered with an exact source kind, experiment, runtime, asset and protocol.
A mismatch fails closed so charts cannot combine results across runtime lines.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path


class AnalysisDatasets:
    SOURCE_KINDS = {'workpack', 'online-e2e', 'attribution'}

    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / 'releases' / 'analysis-manifest.json'

    def _registry(self) -> dict:
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('schemaVersion') != 1 or not isinstance(data.get('datasets'), list):
            raise ValueError('数据分析清单格式不受支持')
        self._validate_pricing(data.get('modelPricing'))
        default = data.get('defaultDatasetId')
        if not isinstance(default, str) or not any(row.get('datasetId') == default for row in data['datasets']):
            raise ValueError('数据分析清单缺少有效的默认测试组')
        return data

    @staticmethod
    def _validate_pricing(pricing: object) -> None:
        if not isinstance(pricing, dict):
            raise ValueError('数据分析清单缺少模型价格快照')
        source = pricing.get('source')
        models = pricing.get('models')
        if pricing.get('currency') != 'USD' or not isinstance(source, dict) or not isinstance(models, dict):
            raise ValueError('模型价格快照格式不受支持')
        if not all(isinstance(source.get(key), str) and source[key] for key in ('name', 'url', 'retrievedAt')):
            raise ValueError('模型价格快照缺少来源信息')
        for model, price in models.items():
            if not isinstance(model, str) or not model or not isinstance(price, dict):
                raise ValueError('模型价格快照条目不合法')
            for key in ('inputPerMillionUsd', 'outputPerMillionUsd'):
                value = price.get(key)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                    raise ValueError('模型价格快照条目不合法')

    def _pricing(self) -> dict:
        pricing = self._registry().get('modelPricing')
        self._validate_pricing(pricing)
        return deepcopy(pricing)

    def _manifest(self, dataset_id: str) -> dict:
        row = next((item for item in self._registry()['datasets'] if item.get('datasetId') == dataset_id), None)
        if not row:
            raise KeyError(dataset_id)
        required = {
            'datasetId', 'displayName', 'status', 'experimentId', 'runtimeRevision',
            'assetVersion', 'artifactDigest', 'protocol', 'createdAt', 'claims', 'limitations',
        }
        if not required.issubset(row):
            raise ValueError('数据分析清单字段不完整')
        source = row.get('source') or {'kind': 'workpack'}
        if source.get('kind') not in self.SOURCE_KINDS or set(source) != {'kind'}:
            raise ValueError('数据分析清单来源不受支持')
        row = deepcopy(row)
        row['source'] = deepcopy(source)
        return row

    def list(self) -> dict:
        registry = self._registry()
        return {
            'defaultDatasetId': registry['defaultDatasetId'],
            'modelPricing': self._pricing(),
            'items': [self._descriptor(self._manifest(row['datasetId'])) for row in registry['datasets']],
        }

    @staticmethod
    def _descriptor(row: dict) -> dict:
        return {key: deepcopy(row.get(key)) for key in [
            'datasetId', 'displayName', 'status', 'experimentId', 'source',
            'runtimeRevision', 'assetVersion', 'artifactDigest', 'protocol', 'createdAt',
            'claims', 'limitations', 'taskCount', 'taskPlan', 'attribution', 'releaseId',
            'maintenanceDiagnostics',
        ]}

    def _artifact(self, manifest: dict) -> dict:
        kind = manifest['source']['kind']
        experiment_id = manifest['experimentId']
        if not isinstance(experiment_id, str) or not experiment_id or any(
            char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for char in experiment_id
        ):
            raise ValueError('数据分析实验 ID 不合法')
        if kind == 'workpack':
            path = self.root / 'artifacts' / 'workpack-experiments' / experiment_id / 'experiment.json'
        elif kind == 'online-e2e':
            path = self.root / 'artifacts' / 'online-e2e' / experiment_id / 'result.json'
        else:
            path = self.root / 'artifacts' / 'attribution-experiments' / experiment_id / 'experiment.json'
        if not path.exists():
            raise FileNotFoundError(path)
        content = path.read_bytes()
        if 'sha256:' + hashlib.sha256(content).hexdigest() != manifest['artifactDigest']:
            raise ValueError('测试组保存工件摘要不一致')
        item = json.loads(content)
        if kind == 'workpack':
            self._validate_workpack(manifest, item)
        elif kind == 'online-e2e':
            self._validate_online_e2e(manifest, item)
        else:
            self._validate_attribution(manifest, item)
        return item

    @staticmethod
    def _validate_workpack(manifest: dict, item: dict) -> None:
        protocol = item.get('protocol') or {}
        expected = manifest.get('protocol') or {}
        fingerprint = protocol.get('runtimeFingerprint') or {}
        actual_revision = 'sha256:' + str(fingerprint.get('executionDigest') or '')
        checks = {
            'experimentId': item.get('id') == manifest['experimentId'],
            'status': item.get('status') == expected.get('experimentStatus'),
            'mode': item.get('mode') == expected.get('mode'),
            'protocol': protocol.get('id') == expected.get('id'),
            'taskCount': protocol.get('taskCountPerArm') == expected.get('taskCountPerArm'),
            'runtimeRevision': actual_revision == manifest['runtimeRevision'],
            'pairCount': len(item.get('pairs') or []) == expected.get('taskCountPerArm'),
        }
        AnalysisDatasets._require_checks(checks)

    @staticmethod
    def _validate_online_e2e(manifest: dict, item: dict) -> None:
        protocol = item.get('protocol') or {}
        expected = manifest.get('protocol') or {}
        pairs = item.get('pairs') or []
        checks = {
            'experimentId': item.get('id') == manifest['experimentId'],
            'status': item.get('status') == expected.get('experimentStatus'),
            'baseline': protocol.get('baseline') == expected.get('baseline'),
            'rsi': protocol.get('rsi') == expected.get('rsi'),
            'comparisonMode': protocol.get('comparisonMode') == expected.get('comparisonMode'),
            'singleAgentConcurrency': protocol.get('singleAgentConcurrency') is expected.get('singleAgentConcurrency'),
            'startFromEmpty': protocol.get('startFromEmpty') is expected.get('startFromEmpty'),
            'taskHash': protocol.get('taskHash') == expected.get('taskHash'),
            'runtimeRevision': protocol.get('revision') == manifest['runtimeRevision'],
            'pairCount': len(pairs) == expected.get('taskCountPerArm'),
        }
        AnalysisDatasets._require_checks(checks)

    @staticmethod
    def _validate_attribution(manifest: dict, item: dict) -> None:
        protocol = item.get('protocol') or {}
        expected = manifest.get('protocol') or {}
        fingerprint = item.get('fingerprint') or {}
        task_order = [row.get('id') for row in item.get('manifest') or []]
        checks = {
            'experimentId': item.get('id') == manifest['experimentId'],
            'status': item.get('status') == expected.get('experimentStatus'),
            'mode': item.get('mode') == expected.get('mode'),
            'assetVersion': item.get('assetVersion') == manifest['assetVersion'],
            'protocol': protocol.get('id') == expected.get('id'),
            'model': protocol.get('model') == expected.get('model'),
            'planner': protocol.get('planner') == expected.get('planner'),
            'composition': protocol.get('composition') == expected.get('composition'),
            'thinking': protocol.get('thinking') is expected.get('thinking'),
            'limits': protocol.get('limits') == expected.get('limits'),
            'taskCount': protocol.get('taskCountPerArm') == expected.get('taskCountPerArm'),
            'manifestCount': len(item.get('manifest') or []) == expected.get('taskCountPerArm'),
            'taskOrder': task_order == expected.get('taskOrder') == protocol.get('taskOrder'),
            'pairCount': len(item.get('pairs') or []) == expected.get('completedPairCount'),
            'runtimeRevision': 'sha256:' + str(fingerprint.get('digest') or '') == manifest['runtimeRevision'],
        }
        AnalysisDatasets._require_checks(checks)

    @staticmethod
    def _require_checks(checks: dict) -> None:
        if not all(checks.values()):
            failed = '、'.join(key for key, passed in checks.items() if not passed)
            raise ValueError('测试组与保存实验不一致：' + failed)

    @staticmethod
    def _token_usage(metrics: dict) -> tuple[int, int] | None:
        if metrics.get('usageComplete') is not True:
            return None
        input_tokens, output_tokens = metrics.get('inputTokens'), metrics.get('outputTokens')
        if not isinstance(input_tokens, int) or isinstance(input_tokens, bool) or input_tokens < 0:
            return None
        if not isinstance(output_tokens, int) or isinstance(output_tokens, bool) or output_tokens < 0:
            return None
        return input_tokens, output_tokens

    @classmethod
    def _tokens(cls, metrics: dict) -> int | None:
        usage = cls._token_usage(metrics)
        return None if usage is None else sum(usage)

    @staticmethod
    def _models(run: dict) -> dict[str, str]:
        models = run.get('models')
        if not isinstance(models, dict):
            return {}
        return {
            role: value for role, value in models.items()
            if role in {'planner', 'composition', 'executor'} and isinstance(value, str) and value
        }

    @classmethod
    def _cost_usd(cls, run: dict, pricing: dict) -> float | None:
        metrics = run.get('metrics') or {}
        usage = cls._token_usage(metrics)
        models = cls._models(run)
        if usage is None or set(models) != {'planner', 'composition', 'executor'}:
            return None
        prices = pricing['models']

        def priced(model: str, input_tokens: int, output_tokens: int) -> float | None:
            rate = prices.get(model)
            if not isinstance(rate, dict):
                return None
            return (input_tokens * float(rate['inputPerMillionUsd']) + output_tokens * float(rate['outputPerMillionUsd'])) / 1_000_000

        if len(set(models.values())) == 1:
            value = priced(models['planner'], *usage)
            return round(value, 12) if value is not None else None

        phases = run.get('phaseMetrics')
        phase_roles = {
            'plan': 'planner', 'match': 'planner',
            'composition': 'composition', 'compile': 'composition',
            'execute': 'executor', 'graph': 'executor',
        }
        if not isinstance(phases, dict) or not phases:
            return None
        phase_usage: list[tuple[str, tuple[int, int]]] = []
        for phase, values in phases.items():
            if phase not in phase_roles or not isinstance(values, dict):
                return None
            counted = cls._token_usage(values)
            if counted is None:
                return None
            phase_usage.append((phase_roles[phase], counted))
        if tuple(map(sum, zip(*(counts for _, counts in phase_usage)))) != usage:
            return None
        total = 0.0
        for role, (input_tokens, output_tokens) in phase_usage:
            value = priced(models[role], input_tokens, output_tokens)
            if value is None:
                return None
            total += value
        return round(total, 12)

    @staticmethod
    def _duration(metrics: dict) -> float | None:
        value = metrics.get('durationMs')
        return round(float(value), 3) if value is not None else None

    @staticmethod
    def _saving(baseline: float | int | None, rsi: float | int | None) -> float | None:
        if baseline in (None, 0) or rsi is None:
            return None
        return round(1 - float(rsi) / float(baseline), 6)

    @staticmethod
    def _quality_status(manifest: dict, item: dict) -> str:
        expected = expected_status(manifest)
        kind = manifest['source']['kind']
        if kind == 'workpack':
            actual = ((item.get('summary') or {}).get('qualityGate') or {}).get('status')
        elif kind == 'online-e2e':
            pairs = item.get('pairs') or []
            complete = len(pairs) == (manifest.get('protocol') or {}).get('taskCountPerArm')
            passed = all(
                ((pair.get('runs') or {}).get(arm) or {}).get('status') == 'completed'
                and ((((pair.get('runs') or {}).get(arm) or {}).get('evaluation') or {}).get('status') == 'passed')
                and ((((pair.get('runs') or {}).get(arm) or {}).get('metrics') or {}).get('usageComplete') is True)
                for pair in pairs for arm in ('baseline', 'rsi')
            )
            actual = 'passed' if complete and passed else ('failed' if complete else 'incomplete')
        else:
            saved = item.get('summary') or {}
            complete = saved.get('protocolComplete') is True
            passed = saved.get('qualityGate') is True
            actual = 'passed' if complete and passed else ('failed' if complete else 'incomplete')
        if actual != expected:
            raise ValueError('测试组质量门槛与清单声明不一致')
        return actual

    def _arm(self, item: dict, run: dict, arm: str, pricing: dict) -> dict:
        metrics = run.get('metrics') or {}
        usage = self._token_usage(metrics)
        tokens = self._tokens(metrics)
        latency = self._duration(metrics)
        kind = item['_sourceKind']
        base = {
            'workpack': '/api/workpack-experiments',
            'online-e2e': '/api/online-e2e',
            'attribution': '/api/attribution-experiments',
        }[kind]
        experiment_id = item['id']
        run_id = run.get('id')
        route_arm = {
            ('attribution', 'baseline'): 'no_learning',
            ('attribution', 'rsi'): 'online_rsi',
        }.get((kind, arm), arm)
        run_url = f'{base}/{experiment_id}/runs/{route_arm}/{run_id}' if run_id else None
        return {
            'runId': run_id,
            'status': run.get('status'),
            'passed': (run.get('evaluation') or {}).get('status') == 'passed',
            'tokens': tokens,
            'inputTokens': usage[0] if usage else None,
            'outputTokens': usage[1] if usage else None,
            'models': self._models(run),
            'costUsd': self._cost_usd(run, pricing),
            'latencyMs': latency,
            'durationMs': latency,
            'modelRequests': metrics.get('modelRequests'),
            'toolCalls': metrics.get('toolCalls'),
            'toolErrors': metrics.get('toolErrors'),
            'usageComplete': metrics.get('usageComplete') is True,
            'error': run.get('error'),
            'runUrl': run_url,
            'traceUrl': run_url,
            'reportUrl': f'{run_url}/report' if run_url else None,
        }

    def get(self, dataset_id: str) -> dict:
        manifest = self._manifest(dataset_id)
        pricing = self._pricing()
        item = self._artifact(manifest)
        item['_sourceKind'] = manifest['source']['kind']
        if manifest['source']['kind'] == 'attribution':
            try:
                return self._get_attribution(manifest, item, pricing)
            finally:
                item.pop('_sourceKind', None)
        points = []
        cumulative = {
            'baselineTokens': 0, 'rsiTokens': 0,
            'baselineLatencyMs': 0.0, 'rsiLatencyMs': 0.0,
            'baselineCostUsd': 0.0, 'rsiCostUsd': 0.0,
        }
        cumulative_known = {
            'baselineTokens': True, 'rsiTokens': True,
            'baselineLatency': True, 'rsiLatency': True,
            'baselineCost': True, 'rsiCost': True,
        }
        for offset, pair in enumerate(item.get('pairs') or []):
            runs = pair.get('runs') or {}
            baseline, rsi = runs.get('baseline') or {}, runs.get('rsi') or {}
            baseline_metrics, rsi_metrics = baseline.get('metrics') or {}, rsi.get('metrics') or {}
            baseline_tokens, rsi_tokens = self._tokens(baseline_metrics), self._tokens(rsi_metrics)
            baseline_latency, rsi_latency = self._duration(baseline_metrics), self._duration(rsi_metrics)
            baseline_cost, rsi_cost = self._cost_usd(baseline, pricing), self._cost_usd(rsi, pricing)
            for key, value in (
                ('baselineTokens', baseline_tokens), ('rsiTokens', rsi_tokens),
                ('baselineLatency', baseline_latency), ('rsiLatency', rsi_latency),
                ('baselineCost', baseline_cost), ('rsiCost', rsi_cost),
            ):
                if value is None:
                    cumulative_known[key] = False
            if cumulative_known['baselineTokens']:
                cumulative['baselineTokens'] += baseline_tokens or 0
            if cumulative_known['rsiTokens']:
                cumulative['rsiTokens'] += rsi_tokens or 0
            if cumulative_known['baselineLatency']:
                cumulative['baselineLatencyMs'] += baseline_latency or 0
            if cumulative_known['rsiLatency']:
                cumulative['rsiLatencyMs'] += rsi_latency or 0
            if cumulative_known['baselineCost']:
                cumulative['baselineCostUsd'] += baseline_cost or 0
            if cumulative_known['rsiCost']:
                cumulative['rsiCostUsd'] += rsi_cost or 0
            evolution = rsi.get('evolution') or {}
            source_index = pair.get('index')
            display_index = offset + 1 if manifest['source']['kind'] == 'online-e2e' else source_index
            points.append(self._point(
                item, pair, display_index, source_index, baseline, rsi, evolution,
                baseline_tokens, rsi_tokens, baseline_latency, rsi_latency,
                baseline_cost, rsi_cost, pricing, cumulative, cumulative_known,
            ))
        quality_status = self._quality_status(manifest, item)
        summary = self._summary(manifest, item, points, quality_status)
        del item['_sourceKind']
        return {
            'dataset': self._descriptor(manifest),
            'pricing': pricing,
            'experimentStatus': item.get('status'),
            'summary': summary,
            'dimensions': self._dimensions(points),
            'points': points,
        }

    def _point(self, item, pair, display_index, source_index, baseline, rsi, evolution,
               baseline_tokens, rsi_tokens, baseline_latency, rsi_latency,
               baseline_cost, rsi_cost, pricing, cumulative, cumulative_known, **extra):
        tokens_comparable = cumulative_known['baselineTokens'] and cumulative_known['rsiTokens']
        latency_comparable = cumulative_known['baselineLatency'] and cumulative_known['rsiLatency']
        costs_comparable = cumulative_known['baselineCost'] and cumulative_known['rsiCost']
        return {
            'index': display_index,
            'sourceIndex': source_index,
            'workpackId': pair.get('workpackId') or pair.get('taskId'),
            'scenario': pair.get('scenario'),
            'workflowType': pair.get('workflowType') or pair.get('family'),
            'round': pair.get('round'),
            'recordCount': pair.get('recordCount'),
            'difficulty': pair.get('difficulty'),
            'status': pair.get('status') or ('completed' if baseline and rsi else 'incomplete'),
            'planningPath': evolution.get('planningPath'),
            'usedVersionId': evolution.get('usedVersionId'),
            'generatedVersionIds': deepcopy(evolution.get('generatedVersionIds') or []),
            'baseline': self._arm(item, baseline, 'baseline', pricing),
            'rsi': {
                **self._arm(item, rsi, 'rsi', pricing),
                'planningPath': evolution.get('planningPath'),
                'usedVersionId': evolution.get('usedVersionId'),
                'generatedVersionIds': deepcopy(evolution.get('generatedVersionIds') or []),
            },
            'tokenSaving': self._saving(baseline_tokens, rsi_tokens),
            'latencySaving': self._saving(baseline_latency, rsi_latency),
            'costSaving': self._saving(baseline_cost, rsi_cost),
            'cumulativeBaselineCostUsd': round(cumulative['baselineCostUsd'], 12) if cumulative_known['baselineCost'] else None,
            'cumulativeRsiCostUsd': round(cumulative['rsiCostUsd'], 12) if cumulative_known['rsiCost'] else None,
            'cumulativeCostSaving': self._saving(cumulative['baselineCostUsd'], cumulative['rsiCostUsd']) if costs_comparable else None,
            'cumulativeBaselineTokens': cumulative['baselineTokens'] if cumulative_known['baselineTokens'] else None,
            'cumulativeRsiTokens': cumulative['rsiTokens'] if cumulative_known['rsiTokens'] else None,
            'cumulativeTokenSaving': self._saving(cumulative['baselineTokens'], cumulative['rsiTokens']) if tokens_comparable else None,
            'cumulativeBaselineLatencyMs': round(cumulative['baselineLatencyMs'], 3) if cumulative_known['baselineLatency'] else None,
            'cumulativeRsiLatencyMs': round(cumulative['rsiLatencyMs'], 3) if cumulative_known['rsiLatency'] else None,
            'cumulativeLatencySaving': self._saving(cumulative['baselineLatencyMs'], cumulative['rsiLatencyMs']) if latency_comparable else None,
            **extra,
        }

    @staticmethod
    def _dimensions(points: list[dict]) -> dict:
        return {
            'scenarios': sorted({point['scenario'] for point in points if point['scenario'] is not None}),
            'workflows': sorted({point['workflowType'] for point in points if point['workflowType'] is not None}),
            'rounds': sorted({point['round'] for point in points if point.get('round') is not None}),
        }

    def _get_attribution(self, manifest: dict, item: dict, pricing: dict) -> dict:
        points = []
        cumulative = {
            'baselineTokens': 0, 'rsiTokens': 0,
            'baselineLatencyMs': 0.0, 'rsiLatencyMs': 0.0,
            'baselineCostUsd': 0.0, 'rsiCostUsd': 0.0,
        }
        cumulative_known = {
            'baselineTokens': True, 'rsiTokens': True,
            'baselineLatency': True, 'rsiLatency': True,
            'baselineCost': True, 'rsiCost': True,
        }
        for offset, pair in enumerate(item.get('pairs') or []):
            spec = pair.get('spec') or {}
            baseline, rsi = pair.get('no_learning') or {}, pair.get('online_rsi') or {}
            baseline_metrics, rsi_metrics = baseline.get('metrics') or {}, rsi.get('metrics') or {}
            baseline_tokens, rsi_tokens = self._tokens(baseline_metrics), self._tokens(rsi_metrics)
            baseline_latency, rsi_latency = self._duration(baseline_metrics), self._duration(rsi_metrics)
            baseline_cost, rsi_cost = self._cost_usd(baseline, pricing), self._cost_usd(rsi, pricing)
            for key, value in (
                ('baselineTokens', baseline_tokens), ('rsiTokens', rsi_tokens),
                ('baselineLatency', baseline_latency), ('rsiLatency', rsi_latency),
                ('baselineCost', baseline_cost), ('rsiCost', rsi_cost),
            ):
                if value is None:
                    cumulative_known[key] = False
            if cumulative_known['baselineTokens']:
                cumulative['baselineTokens'] += baseline_tokens or 0
            if cumulative_known['rsiTokens']:
                cumulative['rsiTokens'] += rsi_tokens or 0
            if cumulative_known['baselineLatency']:
                cumulative['baselineLatencyMs'] += baseline_latency or 0
            if cumulative_known['rsiLatency']:
                cumulative['rsiLatencyMs'] += rsi_latency or 0
            if cumulative_known['baselineCost']:
                cumulative['baselineCostUsd'] += baseline_cost or 0
            if cumulative_known['rsiCost']:
                cumulative['rsiCostUsd'] += rsi_cost or 0
            evolution = rsi.get('evolution') or {}
            generated_matches = evolution.get('generatedMatchVersions') or []
            match_versions = [
                row.get('version') if isinstance(row, dict) else row
                for row in generated_matches
                if (isinstance(row, dict) and row.get('version') is not None) or isinstance(row, (str, int, float))
            ]
            used_graph = evolution.get('usedVersionId')
            point = self._point(
                item, pair, spec.get('position', offset + 1), pair.get('index', offset + 1),
                baseline, rsi, evolution, baseline_tokens, rsi_tokens,
                baseline_latency, rsi_latency, baseline_cost, rsi_cost, pricing, cumulative, cumulative_known,
                pairId=spec.get('id'), workpackId=spec.get('id'), title=spec.get('title'),
                detailUrl=(f'/api/releases/{manifest["releaseId"]}/pairs/{spec["id"]}' if manifest.get('releaseId') else None),
                opportunity=spec.get('opportunity'), scenario=spec.get('scenario') or 'finance',
                workflowType='财务复核', round=None,
                generatedMatchVersions=deepcopy(match_versions),
                usedMatchVersion=evolution.get('matchVersion') if used_graph else None,
            )
            point['rsi'].update({
                'generatedMatchVersions': deepcopy(match_versions),
                'usedMatchVersion': evolution.get('matchVersion') if used_graph else None,
            })
            points.append(point)
        quality_status = self._quality_status(manifest, item)
        revisions = self._attribution_revisions(item)
        task_plan = self._attribution_task_plan(item)
        summary = self._summary(manifest, item, points, quality_status, revisions=revisions)
        descriptor = self._descriptor(manifest)
        descriptor['taskCount'] = len(task_plan)
        descriptor['taskPlan'] = deepcopy(task_plan)
        return {
            'dataset': descriptor,
            'pricing': deepcopy(pricing),
            'experimentStatus': item.get('status'),
            'summary': summary,
            'dimensions': self._dimensions(points),
            'points': points,
            'taskPlan': task_plan,
            'revisions': revisions,
            'attribution': deepcopy(manifest.get('attribution') or {}),
            'maintenanceDiagnostics': self._maintenance_diagnostics(manifest, item),
        }

    @staticmethod
    def _safe_id(value: object, label: str) -> str:
        if not isinstance(value, str) or not value or any(
            char not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for char in value
        ):
            raise ValueError(f'{label}不合法')
        return value

    def _maintenance_entries(self, manifest: dict) -> list[dict]:
        entries = manifest.get('maintenanceDiagnostics') or []
        if not isinstance(entries, list):
            raise ValueError('维护诊断清单格式不受支持')
        allowed_roles = {'validated', 'failed_setup'}
        required = {
            'role', 'diagnosticId', 'kind', 'artifactKind', 'sourceTaskId',
            'createdFromExperiment', 'artifactDigest', 'runtimeRevision', 'model',
            'learningEnabled', 'status', 'claims', 'limitations',
        }
        rows = []
        for entry in entries:
            if not isinstance(entry, dict) or not required.issubset(entry):
                raise ValueError('维护诊断清单字段不完整')
            if entry.get('role') not in allowed_roles or entry.get('kind') != 'post_release_cross_runtime':
                raise ValueError('维护诊断清单角色或类型不受支持')
            self._safe_id(entry.get('diagnosticId'), '维护诊断 ID ')
            if entry.get('createdFromExperiment') != manifest.get('experimentId'):
                raise ValueError('维护诊断来源实验与发布不一致')
            if entry.get('sourceTaskId') not in (manifest.get('protocol') or {}).get('taskOrder', []):
                raise ValueError('维护诊断来源任务不在正式发布中')
            if not isinstance(entry.get('learningEnabled'), bool):
                raise ValueError('维护诊断学习配置不合法')
            if not all(isinstance(entry.get(key), str) and entry[key] for key in (
                'artifactKind', 'artifactDigest', 'runtimeRevision', 'model', 'status'
            )):
                raise ValueError('维护诊断身份字段不完整')
            if not all(isinstance(entry.get(key), list) and all(isinstance(v, str) for v in entry[key])
                       for key in ('claims', 'limitations')):
                raise ValueError('维护诊断结论字段不合法')
            rows.append(deepcopy(entry))
        if entries and {row['role'] for row in rows} != allowed_roles:
            raise ValueError('维护诊断清单必须同时保留验证结果和配置失败记录')
        return rows

    def _maintenance_artifact(self, manifest: dict, entry: dict) -> dict:
        diagnostic_id = self._safe_id(entry.get('diagnosticId'), '维护诊断 ID ')
        path = self.root / 'artifacts' / 'attribution-diagnostics' / diagnostic_id / 'diagnostic.json'
        if not path.exists():
            raise FileNotFoundError(path)
        content = path.read_bytes()
        if 'sha256:' + hashlib.sha256(content).hexdigest() != entry['artifactDigest']:
            raise ValueError('维护诊断保存工件摘要不一致')
        item = json.loads(content)
        runtime = item.get('runtime') or {}
        evaluation = item.get('evaluation') or {}
        expected_evaluation = 'passed' if entry['role'] == 'validated' else 'passed'
        checks = {
            'diagnosticId': item.get('id') == diagnostic_id,
            'artifactKind': item.get('kind') == entry['artifactKind'],
            'createdFromExperiment': item.get('createdFromExperiment') == manifest['experimentId'] == entry['createdFromExperiment'],
            'sourceTaskId': item.get('sourceTaskId') == entry['sourceTaskId'],
            'runtimeRevision': 'sha256:' + str(runtime.get('digest') or '') == entry['runtimeRevision'],
            'differentRuntime': entry['runtimeRevision'] != manifest['runtimeRevision'],
            'model': item.get('model') == entry['model'],
            'learningEnabled': item.get('learningEnabled') is entry['learningEnabled'],
            'status': item.get('status') == 'completed',
            'evaluation': evaluation.get('status') == expected_evaluation,
        }
        try:
            self._require_checks(checks)
        except ValueError as error:
            raise ValueError(str(error).replace('测试组与保存实验', '维护诊断与清单')) from error
        return item

    @classmethod
    def _maintenance_run(cls, run: dict, *, runtime_revision: str, artifact_url: str | None = None) -> dict:
        metrics = run.get('metrics') or {}
        evolution = run.get('evolution') or {}
        match = run.get('trajectoryMatch') or {}
        selections = match.get('selections') or []
        selected_nodes = {
            node_id for selection in selections if isinstance(selection, dict)
            for node_id in selection.get('nodeIds') or [] if isinstance(node_id, str)
        }
        bindings = [
            deepcopy(binding) for selection in selections if isinstance(selection, dict)
            for binding in selection.get('bindings') or [] if isinstance(binding, dict)
        ]
        return {
            'runId': run.get('runId') or run.get('id'),
            'status': run.get('status'),
            'evaluationStatus': (run.get('evaluation') or {}).get('status'),
            'runtimeRevision': runtime_revision,
            'model': run.get('model') or (run.get('models') or {}).get('executor'),
            'learningEnabled': run.get('learningEnabled'),
            'modelRequests': metrics.get('modelRequests'),
            'tokens': cls._tokens(metrics),
            'inputTokens': metrics.get('inputTokens'),
            'outputTokens': metrics.get('outputTokens'),
            'latencyMs': cls._duration(metrics),
            'toolCalls': metrics.get('toolCalls'),
            'toolErrors': metrics.get('toolErrors'),
            'usageComplete': metrics.get('usageComplete') is True,
            'planningPath': evolution.get('planningPath'),
            'usedVersionId': evolution.get('usedVersionId'),
            'usedMatchVersion': evolution.get('matchVersion'),
            'selectedGraphNodeCount': len(selected_nodes),
            'currentBindings': bindings,
            'uncovered': deepcopy(match.get('uncovered') or []),
            'note': evolution.get('note'),
            'artifactUrl': artifact_url,
        }

    def _maintenance_diagnostics(self, manifest: dict, item: dict) -> dict | None:
        entries = self._maintenance_entries(manifest)
        if not entries:
            return None
        formal_pair = next((
            pair for pair in item.get('pairs') or []
            if (pair.get('spec') or {}).get('id') == entries[0]['sourceTaskId']
        ), None)
        if not formal_pair:
            raise ValueError('维护诊断来源任务缺少正式运行')
        request = (formal_pair.get('spec') or {}).get('request')
        if not isinstance(request, str) or not request:
            raise ValueError('维护诊断来源任务缺少正式业务请求')
        formal_run = formal_pair.get('online_rsi') or {}
        formal = self._maintenance_run(formal_run, runtime_revision=manifest['runtimeRevision'])
        formal.update({
            'experimentId': manifest['experimentId'],
            'runUrl': f'/api/attribution-experiments/{manifest["experimentId"]}/runs/online_rsi/{formal_run.get("id")}',
            'reportUrl': f'/api/attribution-experiments/{manifest["experimentId"]}/runs/online_rsi/{formal_run.get("id")}/report',
        })
        projected = {}
        claims, limitations = [], []
        for entry in entries:
            artifact = self._maintenance_artifact(manifest, entry)
            url = f'/api/analysis/datasets/{manifest["datasetId"]}/maintenance-diagnostics/{entry["diagnosticId"]}'
            row = self._maintenance_run(artifact, runtime_revision=entry['runtimeRevision'], artifact_url=url)
            row.update({
                'diagnosticId': entry['diagnosticId'], 'role': entry['role'],
                'diagnosticStatus': entry['status'], 'claims': deepcopy(entry['claims']),
                'limitations': deepcopy(entry['limitations']),
            })
            projected[entry['role']] = row
            claims.extend(entry['claims'])
            limitations.extend(entry['limitations'])
        return {
            'kind': 'post_release_cross_runtime',
            'sourceTaskId': entries[0]['sourceTaskId'],
            'request': request,
            'excludedFromFormalMetrics': True,
            'formal': formal,
            'validated': projected['validated'],
            'failedSetup': projected['failed_setup'],
            'claims': claims,
            'limitations': limitations,
        }

    def get_maintenance_diagnostic(self, dataset_id: str, diagnostic_id: str) -> dict:
        manifest = self._manifest(dataset_id)
        entry = next((row for row in self._maintenance_entries(manifest)
                      if row['diagnosticId'] == diagnostic_id), None)
        if not entry:
            raise KeyError(diagnostic_id)
        artifact = self._maintenance_artifact(manifest, entry)
        return {
            'datasetId': dataset_id,
            'experimentId': manifest['experimentId'],
            'excludedFromFormalMetrics': True,
            'diagnostic': self._maintenance_run(
                artifact,
                runtime_revision=entry['runtimeRevision'],
                artifact_url=f'/api/analysis/datasets/{dataset_id}/maintenance-diagnostics/{diagnostic_id}',
            ),
            'claims': deepcopy(entry['claims']),
            'limitations': deepcopy(entry['limitations']),
        }

    @staticmethod
    def _attribution_task_plan(item: dict) -> list[dict]:
        recorded = {((pair.get('spec') or {}).get('id')): pair for pair in item.get('pairs') or []}
        return [{
            'index': spec.get('position', offset + 1),
            'taskId': spec.get('id'),
            'sourceTaskId': spec.get('sourceTaskId'),
            'title': spec.get('title'),
            'opportunity': spec.get('opportunity'),
            'status': 'recorded' if spec.get('id') in recorded else 'pending',
            'requestHash': spec.get('requestHash'),
            'inputHash': spec.get('inputHash'),
            'scoreHash': spec.get('scoreHash'),
        } for offset, spec in enumerate(item.get('manifest') or [])]

    @staticmethod
    def _attribution_revisions(item: dict) -> list[dict]:
        pairs = item.get('pairs') or []
        source_by_run = {
            (pair.get('online_rsi') or {}).get('id'): (index, pair)
            for index, pair in enumerate(pairs)
            if (pair.get('online_rsi') or {}).get('id')
        }
        versions = {}
        for pair in pairs:
            for version in ((pair.get('experienceAfter') or {}).get('onlineRsiVersions') or []):
                versions[version.get('id')] = version
        # Old artifacts may number an unchanged DAG differently after replay.
        # Re-audit the witnessed graphs without rewriting those artifacts.
        from .trajectory import canonical_structure
        compiled = {}
        for pair in pairs:
            evolution = (pair.get('online_rsi') or {}).get('evolution') or {}
            proposal = evolution.get('trajectoryCompilation') or {}
            if proposal.get('nodes') and proposal.get('descriptor'):
                for version_id in evolution.get('generatedVersionIds') or []:
                    compiled[version_id] = proposal
        revisions = []
        for version in versions.values():
            generation = version.get('generation')
            match_version = version.get('matchVersion')
            patches = deepcopy(version.get('patches') or [])
            match_patches = deepcopy(version.get('matchPatches') or [])
            graph_revision = bool(version.get('parentGraphId')) or (
                isinstance(generation, (int, float)) and generation > 0
            )
            matching_revision = isinstance(match_version, (int, float)) and match_version > 0
            graph_changed = graph_revision and any(
                patch.get('before') != patch.get('after') for patch in patches
            )
            changed_match_patches = [
                patch for patch in match_patches
                if patch.get('before') is not None and patch.get('before') != patch.get('after')
            ]
            matching_changed = matching_revision and bool(changed_match_patches)
            child = compiled.get(version.get('id'))
            parent = compiled.get(version.get('parentGraphId'))
            if child and parent:
                substantive = canonical_structure(child) != canonical_structure(parent)
                graph_changed = graph_changed and substantive
                matching_changed = matching_changed and (substantive or
                    child['descriptor'].get('acceptedSchemas', [child['descriptor'].get('schema')]) !=
                    parent['descriptor'].get('acceptedSchemas', [parent['descriptor'].get('schema')]))
            if not graph_changed and not matching_changed:
                continue
            source_run_id = (
                changed_match_patches[-1].get('sourceRunId')
                if matching_changed and not graph_changed
                else version.get('sourceRunId')
            )
            source_index, source_pair = source_by_run.get(source_run_id, (-1, {}))
            uses = []
            for later in pairs[source_index + 1:] if source_index >= 0 else []:
                run = later.get('online_rsi') or {}
                evolution = run.get('evolution') or {}
                used = set(evolution.get('usedVersionIds') or [])
                if evolution.get('usedVersionId'):
                    used.add(evolution['usedVersionId'])
                graph_executed = any(
                    row.get('executor') == 'graph' and row.get('ok') is True
                    for row in run.get('toolTrace') or []
                )
                if version.get('id') in used and graph_executed:
                    later_spec = later.get('spec') or {}
                    uses.append({
                        'pairId': later_spec.get('id'), 'taskId': later_spec.get('id'),
                        'runId': run.get('id'), 'matchVersion': evolution.get('matchVersion'),
                    })
            source_spec = source_pair.get('spec') or {}
            revisions.append({
                'versionId': version.get('id'), 'graphId': version.get('id'),
                'parentVersionId': version.get('parentGraphId'),
                'sourceRunId': source_run_id,
                'sourcePairId': source_spec.get('id'), 'sourceTaskId': source_spec.get('id'),
                'graphChanged': graph_changed, 'matchingChanged': matching_changed,
                'graphDiff': patches, 'matchingDiff': match_patches, 'subsequentUses': uses,
            })
        return revisions

    @staticmethod
    def _projected_cost(points: list[dict], arm: str) -> float | None:
        values = [point.get(arm, {}).get('costUsd') for point in points]
        if not values or any(value is None for value in values):
            return None
        return round(sum(float(value) for value in values), 12)

    def _summary(self, manifest: dict, item: dict, points: list[dict], quality_status: str,
                 revisions: list[dict] | None = None) -> dict:
        saved = item.get('summary') or {}
        if manifest['source']['kind'] == 'attribution':
            arms = saved.get('arms') or {}
            baseline = arms.get('no_learning') or {}
            rsi = arms.get('online_rsi') or {}
            created_graphs = sum(len(point['rsi'].get('generatedVersionIds') or []) for point in points)
            created_matches = sum(len(point['rsi'].get('generatedMatchVersions') or []) for point in points)
            revisions = revisions or []
            graph_revisions = sum(row.get('graphChanged') is True for row in revisions)
            matching_revisions = sum(row.get('matchingChanged') is True for row in revisions)
            subsequent_uses = sum(len(row.get('subsequentUses') or []) for row in revisions)
            target = len(item.get('manifest') or [])
            completed = len(points)
            all_usage_complete = all(
                point[arm].get('usageComplete') is True
                for point in points for arm in ('baseline', 'rsi')
            )
            cost_allowed = quality_status == 'passed' and completed == target and all_usage_complete
            if quality_status == 'passed':
                reason = f'两臂{completed}/{target}任务均通过，usage完整。'
            elif item.get('status') == 'infrastructure_stopped':
                reason = f'正式协议在完成{completed}/{target}个配对任务后因基础设施停止；失败与usage缺口已保留。'
            else:
                reason = f'当前仅完成{completed}/{target}个配对任务，或质量与usage尚未满足可比条件。'
            quality = {
                'status': quality_status,
                'reason': reason,
                'sameQualityCostClaim': cost_allowed,
            }
            reliability = {
                'allUsageComplete': all_usage_complete,
                'usageIncompleteRuns': sum(
                    point[arm].get('usageComplete') is not True
                    for point in points for arm in ('baseline', 'rsi')
                ),
                'note': f'保留{completed}个已运行配对、全部失败、工具错误和串行耗时；未知token不按0补齐。',
            }
            baseline_summary = self._attribution_arm_summary(
                baseline, sum(point['baseline'].get('usageComplete') is not True for point in points)
            )
            rsi_summary = self._attribution_arm_summary(
                rsi, sum(point['rsi'].get('usageComplete') is not True for point in points)
            )
            baseline_summary['costUsd'] = self._projected_cost(points, 'baseline')
            rsi_summary['costUsd'] = self._projected_cost(points, 'rsi')
            later_use = [use for revision in revisions for use in revision.get('subsequentUses') or []]
            return {
                'taskCount': target,
                'pairedCompleted': completed,
                'qualityGate': quality,
                'baseline': baseline_summary,
                'rsi': rsi_summary,
                'tokenSaving': self._saving(baseline_summary['tokens'], rsi_summary['tokens']) if cost_allowed else None,
                'latencySaving': self._saving(baseline_summary['durationMs'], rsi_summary['durationMs']) if cost_allowed else None,
                'costSaving': self._saving(baseline_summary['costUsd'], rsi_summary['costUsd']) if cost_allowed else None,
                'costConclusionAllowed': cost_allowed,
                'learning': {
                    'workflowCreated': created_graphs,
                    'matchingCreated': created_matches,
                    'fastReuse': sum(point['rsi'].get('planningPath') == 'fast' for point in points),
                    'graphRevisions': graph_revisions,
                    'matchingRevisions': matching_revisions,
                    'subsequentUses': subsequent_uses,
                    'created': [
                        {'taskId': point.get('pairId'),
                         'graphVersionIds': deepcopy(point['rsi'].get('generatedVersionIds') or []),
                         'matchVersions': deepcopy(point['rsi'].get('generatedMatchVersions') or [])}
                        for point in points
                        if point['rsi'].get('generatedVersionIds') or point['rsi'].get('generatedMatchVersions')
                    ],
                    'revisions': deepcopy(revisions),
                    'laterUse': deepcopy(later_use),
                    'revisionWithLaterUse': subsequent_uses > 0,
                },
                'reliability': reliability,
            }
        if manifest['source']['kind'] == 'workpack':
            baseline, rsi = saved.get('baseline') or {}, saved.get('rsi') or {}
            learning = deepcopy(saved.get('learning') or {})
            quality = deepcopy(saved.get('qualityGate') or {})
            reliability = deepcopy(saved.get('reliability') or {})
        else:
            arms = saved.get('arms') or {}
            baseline, rsi = arms.get('baseline') or {}, arms.get('rsi') or {}
            diagnostics = rsi.get('diagnostics') or {}
            planning_paths = diagnostics.get('planningPaths') or {}
            learning = {
                'workflowCreated': diagnostics.get('initialWorkflowVersions'),
                'fastReuse': diagnostics.get('fastRuns'),
                'composition': diagnostics.get('compositionRuns'),
                'fallback': planning_paths.get('fallback'),
            }
            quality = {
                'status': quality_status,
                'reason': '两臂36/36结构化事实与证据通过，usage完整。',
                'sameQualityCostClaim': quality_status == 'passed',
            }
            reliability = {
                'allUsageComplete': baseline.get('usageComplete') is True and rsi.get('usageComplete') is True,
                'note': '失败、报告恢复、工具错误与端到端等待均保留在保存运行；本组两臂最终均通过。',
            }
        baseline_summary = self._arm_summary(baseline)
        rsi_summary = self._arm_summary(rsi)
        baseline_summary['costUsd'] = self._projected_cost(points, 'baseline')
        rsi_summary['costUsd'] = self._projected_cost(points, 'rsi')
        cost_allowed = quality_status == 'passed'
        return {
            'taskCount': len(points),
            'pairedCompleted': saved.get('pairedCompleted', len(points)),
            'qualityGate': quality,
            'baseline': baseline_summary,
            'rsi': rsi_summary,
            'tokenSaving': self._saving(baseline.get('totalTokens'), rsi.get('totalTokens')),
            'latencySaving': self._saving(baseline.get('durationMs'), rsi.get('durationMs')),
            'costSaving': self._saving(baseline_summary['costUsd'], rsi_summary['costUsd']) if cost_allowed else None,
            'costConclusionAllowed': cost_allowed,
            'learning': learning,
            'reliability': reliability,
        }

    @staticmethod
    def _attribution_arm_summary(row: dict, usage_incomplete: int) -> dict:
        usage_complete = row.get('usageComplete') is True
        attempts = int(row.get('attempts') or 0)
        return {
            'passed': row.get('passed'),
            'attempts': attempts,
            'tokens': row.get('tokens') if usage_complete else None,
            'latencyMs': row.get('durationMs'),
            'durationMs': row.get('durationMs'),
            'modelRequests': row.get('modelRequests'),
            'toolCalls': row.get('toolCalls'),
            'toolErrors': row.get('toolErrors'),
            'usageIncomplete': usage_incomplete,
        }

    @staticmethod
    def _arm_summary(row: dict) -> dict:
        return {
            'passed': row.get('passed'),
            'attempts': row.get('attempts'),
            'tokens': row.get('totalTokens'),
            'latencyMs': row.get('durationMs'),
            'durationMs': row.get('durationMs'),
            'modelRequests': row.get('modelRequests'),
            'toolCalls': row.get('toolCalls'),
            'toolErrors': row.get('toolErrors'),
            'usageIncomplete': row.get('usageIncomplete', 0 if row.get('usageComplete') is True else None),
        }


def expected_status(manifest: dict) -> str:
    value = (manifest.get('protocol') or {}).get('qualityGateStatus')
    if value not in {'passed', 'failed', 'incomplete'}:
        raise ValueError('数据分析清单缺少质量门槛状态')
    return value
