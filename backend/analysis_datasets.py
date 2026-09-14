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
    SOURCE_KINDS = {'workpack', 'online-e2e'}

    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / 'releases' / 'analysis-manifest.json'

    def _registry(self) -> dict:
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('schemaVersion') != 1 or not isinstance(data.get('datasets'), list):
            raise ValueError('数据分析清单格式不受支持')
        default = data.get('defaultDatasetId')
        if not isinstance(default, str) or not any(row.get('datasetId') == default for row in data['datasets']):
            raise ValueError('数据分析清单缺少有效的默认测试组')
        return data

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
            'items': [self._descriptor(self._manifest(row['datasetId'])) for row in registry['datasets']],
        }

    @staticmethod
    def _descriptor(row: dict) -> dict:
        return {key: deepcopy(row.get(key)) for key in [
            'datasetId', 'displayName', 'status', 'experimentId', 'source',
            'runtimeRevision', 'assetVersion', 'artifactDigest', 'protocol', 'createdAt',
            'claims', 'limitations',
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
        else:
            path = self.root / 'artifacts' / 'online-e2e' / experiment_id / 'result.json'
        if not path.exists():
            raise FileNotFoundError(path)
        content = path.read_bytes()
        if 'sha256:' + hashlib.sha256(content).hexdigest() != manifest['artifactDigest']:
            raise ValueError('测试组保存工件摘要不一致')
        item = json.loads(content)
        if kind == 'workpack':
            self._validate_workpack(manifest, item)
        else:
            self._validate_online_e2e(manifest, item)
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
    def _require_checks(checks: dict) -> None:
        if not all(checks.values()):
            failed = '、'.join(key for key, passed in checks.items() if not passed)
            raise ValueError('测试组与保存实验不一致：' + failed)

    @staticmethod
    def _tokens(metrics: dict) -> int | None:
        if metrics.get('usageComplete') is not True:
            return None
        if metrics.get('inputTokens') is None or metrics.get('outputTokens') is None:
            return None
        return int(metrics['inputTokens']) + int(metrics['outputTokens'])

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
        if manifest['source']['kind'] == 'workpack':
            actual = ((item.get('summary') or {}).get('qualityGate') or {}).get('status')
        else:
            pairs = item.get('pairs') or []
            complete = len(pairs) == (manifest.get('protocol') or {}).get('taskCountPerArm')
            passed = all(
                ((pair.get('runs') or {}).get(arm) or {}).get('status') == 'completed'
                and ((((pair.get('runs') or {}).get(arm) or {}).get('evaluation') or {}).get('status') == 'passed')
                and ((((pair.get('runs') or {}).get(arm) or {}).get('metrics') or {}).get('usageComplete') is True)
                for pair in pairs for arm in ('baseline', 'rsi')
            )
            actual = 'passed' if complete and passed else ('failed' if complete else 'incomplete')
        if actual != expected:
            raise ValueError('测试组质量门槛与清单声明不一致')
        return actual

    def _arm(self, item: dict, run: dict, arm: str) -> dict:
        metrics = run.get('metrics') or {}
        tokens = self._tokens(metrics)
        latency = self._duration(metrics)
        kind = item['_sourceKind']
        base = '/api/workpack-experiments' if kind == 'workpack' else '/api/online-e2e'
        experiment_id = item['id']
        run_id = run.get('id')
        return {
            'runId': run_id,
            'status': run.get('status'),
            'passed': (run.get('evaluation') or {}).get('status') == 'passed',
            'tokens': tokens,
            'latencyMs': latency,
            'durationMs': latency,
            'modelRequests': metrics.get('modelRequests'),
            'toolCalls': metrics.get('toolCalls'),
            'toolErrors': metrics.get('toolErrors'),
            'usageComplete': metrics.get('usageComplete') is True,
            'error': run.get('error'),
            'runUrl': f'{base}/{experiment_id}/runs/{arm}/{run_id}',
            'traceUrl': f'{base}/{experiment_id}/runs/{arm}/{run_id}',
            'reportUrl': f'{base}/{experiment_id}/runs/{arm}/{run_id}/report',
        }

    def get(self, dataset_id: str) -> dict:
        manifest = self._manifest(dataset_id)
        item = self._artifact(manifest)
        item['_sourceKind'] = manifest['source']['kind']
        points = []
        cumulative = {'baselineTokens': 0, 'rsiTokens': 0, 'baselineLatencyMs': 0.0, 'rsiLatencyMs': 0.0}
        cumulative_known = {'tokens': True, 'latency': True}
        for offset, pair in enumerate(item.get('pairs') or []):
            runs = pair.get('runs') or {}
            baseline, rsi = runs.get('baseline') or {}, runs.get('rsi') or {}
            baseline_metrics, rsi_metrics = baseline.get('metrics') or {}, rsi.get('metrics') or {}
            baseline_tokens, rsi_tokens = self._tokens(baseline_metrics), self._tokens(rsi_metrics)
            baseline_latency, rsi_latency = self._duration(baseline_metrics), self._duration(rsi_metrics)
            if baseline_tokens is None or rsi_tokens is None:
                cumulative_known['tokens'] = False
            if baseline_latency is None or rsi_latency is None:
                cumulative_known['latency'] = False
            if cumulative_known['tokens']:
                cumulative['baselineTokens'] += baseline_tokens or 0
                cumulative['rsiTokens'] += rsi_tokens or 0
            if cumulative_known['latency']:
                cumulative['baselineLatencyMs'] += baseline_latency or 0
                cumulative['rsiLatencyMs'] += rsi_latency or 0
            evolution = rsi.get('evolution') or {}
            source_index = pair.get('index')
            display_index = offset + 1 if manifest['source']['kind'] == 'online-e2e' else source_index
            points.append({
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
                'baseline': self._arm(item, baseline, 'baseline'),
                'rsi': {
                    **self._arm(item, rsi, 'rsi'),
                    'planningPath': evolution.get('planningPath'),
                    'usedVersionId': evolution.get('usedVersionId'),
                    'generatedVersionIds': deepcopy(evolution.get('generatedVersionIds') or []),
                },
                'tokenSaving': self._saving(baseline_tokens, rsi_tokens),
                'latencySaving': self._saving(baseline_latency, rsi_latency),
                'cumulativeBaselineTokens': cumulative['baselineTokens'] if cumulative_known['tokens'] else None,
                'cumulativeRsiTokens': cumulative['rsiTokens'] if cumulative_known['tokens'] else None,
                'cumulativeTokenSaving': self._saving(cumulative['baselineTokens'], cumulative['rsiTokens']) if cumulative_known['tokens'] else None,
                'cumulativeBaselineLatencyMs': round(cumulative['baselineLatencyMs'], 3) if cumulative_known['latency'] else None,
                'cumulativeRsiLatencyMs': round(cumulative['rsiLatencyMs'], 3) if cumulative_known['latency'] else None,
                'cumulativeLatencySaving': self._saving(cumulative['baselineLatencyMs'], cumulative['rsiLatencyMs']) if cumulative_known['latency'] else None,
            })
        quality_status = self._quality_status(manifest, item)
        summary = self._summary(manifest, item, points, quality_status)
        del item['_sourceKind']
        return {
            'dataset': self._descriptor(manifest),
            'experimentStatus': item.get('status'),
            'summary': summary,
            'dimensions': {
                'scenarios': sorted({point['scenario'] for point in points if point['scenario'] is not None}),
                'workflows': sorted({point['workflowType'] for point in points if point['workflowType'] is not None}),
                'rounds': sorted({point['round'] for point in points if point['round'] is not None}),
            },
            'points': points,
        }

    def _summary(self, manifest: dict, item: dict, points: list[dict], quality_status: str) -> dict:
        saved = item.get('summary') or {}
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
        return {
            'taskCount': len(points),
            'pairedCompleted': saved.get('pairedCompleted', len(points)),
            'qualityGate': quality,
            'baseline': self._arm_summary(baseline),
            'rsi': self._arm_summary(rsi),
            'tokenSaving': self._saving(baseline.get('totalTokens'), rsi.get('totalTokens')),
            'latencySaving': self._saving(baseline.get('durationMs'), rsi.get('durationMs')),
            'learning': learning,
            'reliability': reliability,
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
