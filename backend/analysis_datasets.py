"""Read-only analysis datasets pinned to immutable experiment artifacts.

The frontend never guesses the newest experiment. Each selectable dataset is
registered with an exact experiment, runtime digest, asset and protocol. A
mismatch fails closed so charts cannot combine results across runtime lines.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path


class AnalysisDatasets:
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
        return deepcopy(row)

    def list(self) -> dict:
        registry = self._registry()
        return {
            'defaultDatasetId': registry['defaultDatasetId'],
            'items': [self._descriptor(row) for row in registry['datasets']],
        }

    @staticmethod
    def _descriptor(row: dict) -> dict:
        return {key: deepcopy(row.get(key)) for key in [
            'datasetId', 'displayName', 'status', 'experimentId',
            'runtimeRevision', 'assetVersion', 'artifactDigest', 'protocol', 'createdAt',
            'claims', 'limitations',
        ]}

    def _experiment(self, manifest: dict) -> dict:
        path = self.root / 'artifacts' / 'workpack-experiments' / manifest['experimentId'] / 'experiment.json'
        if not path.exists():
            raise FileNotFoundError(path)
        content = path.read_bytes()
        if 'sha256:' + hashlib.sha256(content).hexdigest() != manifest['artifactDigest']:
            raise ValueError('测试组保存工件摘要不一致')
        item = json.loads(content)
        protocol = item.get('protocol') or {}
        expected_protocol = manifest.get('protocol') or {}
        fingerprint = protocol.get('runtimeFingerprint') or {}
        actual_revision = 'sha256:' + str(fingerprint.get('executionDigest') or '')
        checks = {
            'experimentId': item.get('id') == manifest['experimentId'],
            'status': item.get('status') == expected_protocol.get('experimentStatus'),
            'mode': item.get('mode') == expected_protocol.get('mode'),
            'protocol': protocol.get('id') == expected_protocol.get('id'),
            'taskCount': protocol.get('taskCountPerArm') == expected_protocol.get('taskCountPerArm'),
            'runtimeRevision': actual_revision == manifest['runtimeRevision'],
            'pairCount': len(item.get('pairs') or []) == expected_protocol.get('taskCountPerArm'),
        }
        if not all(checks.values()):
            failed = '、'.join(key for key, passed in checks.items() if not passed)
            raise ValueError('测试组与保存实验不一致：' + failed)
        return item

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

    def get(self, dataset_id: str) -> dict:
        manifest = self._manifest(dataset_id)
        item = self._experiment(manifest)
        points = []
        cumulative = {'baselineTokens': 0, 'rsiTokens': 0, 'baselineLatencyMs': 0.0, 'rsiLatencyMs': 0.0}
        cumulative_known = {'tokens': True, 'latency': True}
        for pair in item.get('pairs') or []:
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
            points.append({
                'index': pair.get('index'),
                'workpackId': pair.get('workpackId'),
                'scenario': pair.get('scenario'),
                'workflowType': pair.get('workflowType'),
                'round': pair.get('round'),
                'recordCount': pair.get('recordCount'),
                'difficulty': pair.get('difficulty'),
                'status': pair.get('status'),
                'planningPath': evolution.get('planningPath'),
                'usedVersionId': evolution.get('usedVersionId'),
                'generatedVersionIds': deepcopy(evolution.get('generatedVersionIds') or []),
                'baseline': {
                    'runId': baseline.get('id'), 'status': baseline.get('status'),
                    'passed': (baseline.get('evaluation') or {}).get('status') == 'passed',
                    'tokens': baseline_tokens, 'latencyMs': baseline_latency,
                    'modelRequests': baseline_metrics.get('modelRequests'),
                    'toolCalls': baseline_metrics.get('toolCalls'),
                    'usageComplete': baseline_metrics.get('usageComplete') is True,
                    'runUrl': f"/api/workpack-experiments/{item['id']}/runs/baseline/{baseline.get('id')}",
                    'reportUrl': f"/api/workpack-experiments/{item['id']}/runs/baseline/{baseline.get('id')}/report",
                },
                'rsi': {
                    'runId': rsi.get('id'), 'status': rsi.get('status'),
                    'passed': (rsi.get('evaluation') or {}).get('status') == 'passed',
                    'tokens': rsi_tokens, 'latencyMs': rsi_latency,
                    'modelRequests': rsi_metrics.get('modelRequests'),
                    'toolCalls': rsi_metrics.get('toolCalls'),
                    'usageComplete': rsi_metrics.get('usageComplete') is True,
                    'runUrl': f"/api/workpack-experiments/{item['id']}/runs/rsi/{rsi.get('id')}",
                    'reportUrl': f"/api/workpack-experiments/{item['id']}/runs/rsi/{rsi.get('id')}/report",
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
        summary = item.get('summary') or {}
        baseline_summary, rsi_summary = summary.get('baseline') or {}, summary.get('rsi') or {}
        quality = summary.get('qualityGate') or {}
        if quality.get('status') != expected_status(manifest):
            raise ValueError('测试组质量门槛与清单声明不一致')
        return {
            'dataset': self._descriptor(manifest),
            'experimentStatus': item.get('status'),
            'summary': {
                'taskCount': len(points),
                'pairedCompleted': summary.get('pairedCompleted'),
                'qualityGate': deepcopy(quality),
                'baseline': {
                    'passed': baseline_summary.get('passed'), 'attempts': baseline_summary.get('attempts'),
                    'tokens': baseline_summary.get('totalTokens'), 'latencyMs': baseline_summary.get('durationMs'),
                    'modelRequests': baseline_summary.get('modelRequests'), 'toolCalls': baseline_summary.get('toolCalls'),
                    'usageIncomplete': baseline_summary.get('usageIncomplete'),
                },
                'rsi': {
                    'passed': rsi_summary.get('passed'), 'attempts': rsi_summary.get('attempts'),
                    'tokens': rsi_summary.get('totalTokens'), 'latencyMs': rsi_summary.get('durationMs'),
                    'modelRequests': rsi_summary.get('modelRequests'), 'toolCalls': rsi_summary.get('toolCalls'),
                    'usageIncomplete': rsi_summary.get('usageIncomplete'),
                },
                'tokenSaving': self._saving(baseline_summary.get('totalTokens'), rsi_summary.get('totalTokens')),
                'latencySaving': self._saving(baseline_summary.get('durationMs'), rsi_summary.get('durationMs')),
                'learning': deepcopy(summary.get('learning') or {}),
                'reliability': deepcopy(summary.get('reliability') or {}),
            },
            'dimensions': {
                'scenarios': sorted({point['scenario'] for point in points}),
                'workflows': sorted({point['workflowType'] for point in points}),
                'rounds': sorted({point['round'] for point in points}),
            },
            'points': points,
        }


def expected_status(manifest: dict) -> str:
    value = (manifest.get('protocol') or {}).get('qualityGateStatus')
    if value not in {'passed', 'failed', 'incomplete'}:
        raise ValueError('数据分析清单缺少质量门槛状态')
    return value
