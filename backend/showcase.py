"""Read-only DTOs for the recorded RSI delivery showcase.

This module deliberately derives display data from completed experiment artifacts.
It never feeds gold data back into an Agent run and does not mutate an experiment.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import json
import re
from pathlib import Path
from typing import Any


SHOWCASE_EXPERIMENT = 'online-rsi-serial-final-v4'
REPORT_KEYS = {'metrics', 'selectedIds', 'evidenceIds', 'summary'}


def total_tokens(metrics: dict[str, Any] | None) -> int:
    metrics = metrics or {}
    return int(metrics.get('inputTokens') or 0) + int(metrics.get('outputTokens') or 0)


def _equal(actual: Any, expected: Any) -> bool:
    """Exact comparison that does not accept bool where an integer is expected."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(_equal(actual[key], expected[key]) for key in expected)
    return actual == expected


def _numbers(value: Any) -> set[str]:
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float)):
        return {str(value)}
    if isinstance(value, dict):
        return set().union(*(_numbers(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_numbers(item) for item in value)) if value else set()
    return set()


def _observed_evidence_and_numbers(run: dict[str, Any]) -> tuple[set[str], set[str]]:
    evidence, numbers = set(), set()
    for event in run.get('events') or []:
        if event.get('type') != 'observation':
            continue
        result = ((event.get('detail') or {}).get('result'))
        if result is None:
            continue
        numbers |= _numbers(result)

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                reference = value.get('_evidenceRef')
                if isinstance(reference, str):
                    evidence.add(reference)
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(result)
    return evidence, numbers


def audit_submission(task: dict[str, Any], expected: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    """Return a stricter, read-only report audit without exposing expected values.

    The official task result remains the existing structured evaluation.  The extra
    checks make the presentation honest about report schema, evidence provenance,
    identifier references, numeric claims and ambiguous currency notation.
    """
    submitted = run.get('submission') or {}
    observed, observed_numbers = _observed_evidence_and_numbers(run)
    expected_metrics = expected.get('metrics') or {}
    required_evidence = {f"{task['scenario']}:{record_id}" for record_id in task.get('recordIds') or []}
    metrics = submitted.get('metrics')
    selected = submitted.get('selectedIds')
    evidence = submitted.get('evidenceIds')
    summary = submitted.get('summary')
    expected_selected = expected.get('selectedIds') or []
    ordered = bool(expected.get('ordered'))

    schema = (
        set(submitted) == REPORT_KEYS
        and isinstance(metrics, dict)
        and isinstance(selected, list) and all(isinstance(value, str) for value in selected)
        and isinstance(evidence, list) and all(isinstance(value, str) for value in evidence)
        and isinstance(summary, str) and bool(summary.strip())
    )
    metric_exact = isinstance(metrics, dict) and _equal(metrics, expected_metrics)
    selection_exact = (
        isinstance(selected, list)
        and len(selected) == len(set(selected))
        and set(selected).issubset(set(task.get('recordIds') or []))
        and (selected == expected_selected if ordered else sorted(selected) == sorted(expected_selected))
    )
    evidence_exact = (
        isinstance(evidence, list)
        and len(evidence) == len(set(evidence))
        and set(evidence) == required_evidence
    )
    evidence_observed = isinstance(evidence, list) and set(evidence).issubset(observed)

    report_text = summary or ''
    for record_id in task.get('recordIds') or []:
        report_text = report_text.replace(record_id, ' ')
    for reference in required_evidence:
        report_text = report_text.replace(reference, ' ')
    identifier_pattern = r'\b[0-9a-f]{32}\b' if task.get('scenario') == 'finance' else r'(?<!\d)\d{7,}(?!\d)'
    unknown_ids = sorted(set(re.findall(identifier_pattern, report_text, flags=re.IGNORECASE)) - set(task.get('recordIds') or []))
    allowed_numbers = _numbers(expected_metrics) | observed_numbers | {str(task.get('recordCount') or 0)}
    numeric_claims = set(re.findall(r'(?<![\w.:-])\d+(?:\.\d+)?(?![\w.:-])', report_text))
    unknown_numbers = sorted(number for number in numeric_claims if number not in allowed_numbers)
    amount_contract = any('cents' in key for key in expected_metrics)
    currency_clear = not amount_contract or not bool(re.search(r'\bBRL\s*(?:分|cents?)', summary or '', flags=re.IGNORECASE))
    summary_references_valid = not unknown_ids
    summary_numbers_grounded = not unknown_numbers

    structured_pass = schema and metric_exact and selection_exact and evidence_exact and evidence_observed
    report_audit_pass = structured_pass and summary_references_valid and summary_numbers_grounded and currency_clear
    return {
        'schemaExact': schema,
        'metricExact': metric_exact,
        'selectionExact': selection_exact,
        'evidenceExact': evidence_exact,
        'evidenceObserved': evidence_observed,
        'summaryReferencesValid': summary_references_valid,
        'summaryNumbersGrounded': summary_numbers_grounded,
        'currencyNotationClear': currency_clear,
        'strictStructuredPass': structured_pass,
        'strictReportAuditPass': report_audit_pass,
        'issues': [
            *([] if schema else ['schema']),
            *([] if metric_exact else ['metrics']),
            *([] if selection_exact else ['selection']),
            *([] if evidence_exact else ['evidence']),
            *([] if evidence_observed else ['evidence_not_observed']),
            *([] if summary_references_valid else ['unknown_identifier']),
            *([] if summary_numbers_grounded else ['ungrounded_numeric_claim']),
            *([] if currency_clear else ['ambiguous_currency_notation']),
        ],
        'unknownIdentifierCount': len(unknown_ids),
        'unknownNumericClaimCount': len(unknown_numbers),
    }


def _run_path(root: Path, arm: str, run_id: str) -> Path:
    return root / arm / 'runs' / f'{run_id}.json'


def _read_run(root: Path, arm: str, run_id: str) -> dict[str, Any]:
    path = _run_path(root, arm, run_id)
    if not path.exists():
        raise FileNotFoundError(path)
    run = json.loads(path.read_text(encoding='utf-8'))
    if run.get('id') != run_id:
        raise ValueError('run_id_mismatch')
    return run


def _compact_run(run: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    metrics = run.get('metrics') or {}
    evolution = run.get('evolution') or {}
    return {
        'id': run.get('id'),
        'strategy': run.get('strategy'),
        'status': run.get('status'),
        'evaluation': run.get('evaluation'),
        'metrics': {
            key: metrics.get(key, 0) for key in [
                'modelRequests', 'toolCalls', 'inputTokens', 'outputTokens', 'durationMs', 'peakReads',
                'reportAttempts', 'failedReportAttempts', 'filteredOutDetailReads', 'deterministicBindings',
                'bindingMs', 'toolErrors', 'usageComplete',
            ]
        },
        'phaseMetrics': run.get('phaseMetrics') or {},
        'evolution': {
            key: evolution.get(key) for key in [
                'usedVersionId', 'generation', 'planningPath', 'generatedVersionIds', 'note', 'lookupMs',
                'compileMs', 'bindingMs', 'maintenanceMs', 'persistMs', 'localCompileMs',
            ]
        } if evolution else None,
        'audit': audit,
    }


def _family_label(scenario: str, family: str) -> str:
    scenario_name = {'finance': '财务', 'support': '客服', 'tickets': '技术工单'}.get(scenario, scenario)
    family_name = {
        'cancelled_payments': '取消订单支付', 'installments': '分期订单', 'channels': '投诉渠道',
        'timeliness': '投诉时效', 'labels': '工单标签', 'unassigned': '未分配工单',
    }.get(family, family)
    return f'{scenario_name} / {family_name}'


def _overview(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get('summary') or {}
    arms = summary.get('arms') or {}
    baseline, rsi = arms.get('baseline') or {}, arms.get('rsi') or {}
    return {
        'baseline': baseline,
        'rsi': rsi,
        'tokenSavingRate': summary.get('tokenSavingRate'),
        'modelRequestSavingRate': summary.get('modelRequestSavingRate'),
        'observedLatencySavingRate': summary.get('observedLatencySavingRate'),
        'toolCallDelta': summary.get('toolCallDelta'),
        'qualityRegressions': summary.get('qualityRegressions'),
        'judge': result.get('judgeSummary') or {},
    }


def _audit_rollup(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [
        'strictStructuredPass', 'strictReportAuditPass', 'schemaExact', 'metricExact', 'selectionExact',
        'evidenceExact', 'evidenceObserved', 'summaryReferencesValid', 'summaryNumbersGrounded',
        'currencyNotationClear',
    ]
    arms: dict[str, dict[str, Any]] = {}
    for arm in ['baseline', 'rsi']:
        audits = [pair['runs'][arm]['audit'] for pair in pairs]
        arms[arm] = {'runs': len(audits), **{field: sum(bool(audit[field]) for audit in audits) for field in fields}}
        issue_counts: Counter[str] = Counter(issue for audit in audits for issue in audit['issues'])
        arms[arm]['issueCounts'] = dict(issue_counts)
    return {'arms': arms, 'scope': 'deterministic_schema_metrics_selection_evidence_and_limited_summary_claim_checks'}


def build_showcase(root: Path, taskbank: Any, experiment: str = SHOWCASE_EXPERIMENT) -> dict[str, Any]:
    result_path = root / 'artifacts' / 'online-e2e' / experiment / 'result.json'
    if not result_path.exists():
        raise FileNotFoundError(result_path)
    result = json.loads(result_path.read_text(encoding='utf-8'))
    experiment_root = result_path.parent
    pairs = []
    for source in sorted(result.get('pairs') or [], key=lambda item: item.get('index', 0)):
        task_id = source['taskId']
        task = taskbank.task(task_id)
        row = {
            key: deepcopy(source.get(key)) for key in ['index', 'round', 'taskId', 'scenario', 'family', 'recordCount', 'launchOrder']
        }
        row['familyLabel'] = _family_label(row['scenario'], row['family'])
        row['runs'] = {}
        for arm in ['baseline', 'rsi']:
            compact = source.get('runs', {}).get(arm) or {}
            run = _read_run(experiment_root, arm, compact['id'])
            row['runs'][arm] = _compact_run(run, audit_submission(task, taskbank.gold[task_id], run))
        row['links'] = {
            arm: {
                'trace': f'/api/online-e2e/{experiment}/runs/{arm}/{row["runs"][arm]["id"]}',
                'report': f'/api/online-e2e/{experiment}/runs/{arm}/{row["runs"][arm]["id"]}/report',
            } for arm in ['baseline', 'rsi']
        }
        pairs.append(row)
    family_map: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        family_map[(pair['scenario'], pair['family'])].append(pair)
    families = []
    for (scenario, family), rows in family_map.items():
        base_total = rsi_total = 0
        points = []
        for pair in rows:
            base_total += total_tokens(pair['runs']['baseline']['metrics'])
            rsi_total += total_tokens(pair['runs']['rsi']['metrics'])
            points.append({
                'taskId': pair['taskId'], 'position': len(points) + 1,
                'baselineCumulativeTokens': base_total, 'rsiCumulativeTokens': rsi_total,
                'savingRate': 1 - rsi_total / base_total if base_total else None,
            })
        families.append({
            'id': f'{scenario}-{family}', 'scenario': scenario, 'family': family, 'label': _family_label(scenario, family),
            'pairs': [pair['taskId'] for pair in rows], 'points': points,
            'finalSavingRate': points[-1]['savingRate'] if points else None,
        })
    protocol = result.get('protocol') or {}
    return {
        'id': result.get('id'), 'status': result.get('status'), 'createdAt': result.get('createdAt'),
        'protocol': {key: protocol.get(key) for key in ['executor', 'planner', 'composition', 'maxSteps', 'timeout', 'comparisonMode', 'startFromEmpty', 'singleAgentConcurrency', 'shadowRollouts']},
        'overview': _overview(result), 'audit': _audit_rollup(pairs), 'families': families, 'pairs': pairs,
        'limitations': {
            'latency': '同一 session 交替串行观测；供应商负载和缓存仍会影响时长，不能表述为稳定 provider 性能优势。',
            'judge': 'Judge 与执行模型相同，26/36 对完成且有顺序分歧；不构成独立文字质量优势。',
            'evolution': '已观察到 G0 Workflow 形成和 Fast 复用；没有真实 G1/G2 结构修订，也没有 Composition 实际执行。',
            'data': '任务来自公开历史数据任务库；不是生产企业数据。',
        },
    }


def _parse_arguments(value: Any) -> dict[str, Any] | str:
    if not isinstance(value, str):
        return value if isinstance(value, dict) else ''
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else value
    except json.JSONDecodeError:
        return value[:200]


def _observation_summary(result: Any) -> str:
    if not isinstance(result, dict):
        return '工具返回观察'
    records = result.get('records')
    if isinstance(records, list):
        fields = sorted({key for record in records if isinstance(record, dict) for key in record if not key.startswith('_') and key != 'id'})
        return f'返回 {len(records)} 条记录' + (f'：{", ".join(fields[:4])}' if fields else '')
    fields = [key for key in result if not key.startswith('_')]
    return '返回字段：' + '、'.join(fields[:5]) if fields else '工具返回空结果'


def _action_summary(tool: str, arguments: Any) -> str | dict[str, Any]:
    parsed = _parse_arguments(arguments)
    if tool.endswith('publish_report') and isinstance(parsed, dict):
        metrics = parsed.get('metrics') if isinstance(parsed.get('metrics'), dict) else {}
        selected = parsed.get('selectedIds') if isinstance(parsed.get('selectedIds'), list) else []
        evidence = parsed.get('evidenceIds') if isinstance(parsed.get('evidenceIds'), list) else []
        return f'提交指标 {metrics} · 入选 {len(selected)} · 证据 {len(evidence)}'
    return parsed


def _graph_nodes(run: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = ((run.get('graph') or {}).get('nodes') or [])
    if not nodes:
        nodes = next((event.get('detail', {}).get('nodes') for event in run.get('events') or [] if event.get('type') == 'graph_created'), []) or []
    actions: dict[str, list[dict[str, Any] | str]] = defaultdict(list)
    for event in run.get('events') or []:
        if event.get('type') == 'action' and (event.get('detail') or {}).get('nodeId'):
            actions[event['detail']['nodeId']].append(_parse_arguments(event['detail'].get('arguments')))
    return [{
        'id': node.get('id'), 'tool': node.get('tool'), 'dependencies': node.get('dependencies') or [],
        'filter': ((node.get('foreach') or {}).get('filter')), 'reuse': ((node.get('reuse') or {}).get('fields')),
        'defer': bool(node.get('defer')), 'boundArguments': actions.get(node.get('id'), []),
    } for node in nodes]


def _trace_steps(run: dict[str, Any]) -> list[dict[str, Any]]:
    steps = []
    for event in run.get('events') or []:
        detail = event.get('detail') or {}
        event_type = event.get('type')
        if event_type == 'plan':
            steps.append({'kind': 'plan', 'title': '生成读取计划', 'detail': [step.get('intent') for step in detail.get('steps') or []]})
        elif event_type == 'graph_created':
            steps.append({'kind': 'graph', 'title': '读取图已绑定当前任务', 'detail': f"{len(detail.get('nodes') or [])} 个节点"})
        elif event_type == 'motif':
            condition = detail.get('condition') or {}
            steps.append({'kind': 'motif', 'title': '先筛选，再补查', 'detail': f"{detail.get('selectedRecords', 0)} 入选 / {detail.get('filteredOutRecords', 0)} 跳过；{condition.get('field', '')} {condition.get('operator', '')} {condition.get('value', '')}"})
        elif event_type == 'binding':
            steps.append({'kind': 'binding', 'title': '结构化参数绑定', 'detail': f"{detail.get('argumentSets', 0)} 组参数 · {detail.get('bindingMs', 0)} ms"})
        elif event_type == 'action':
            steps.append({'kind': 'tool', 'title': event.get('title') or '调用工具', 'detail': _action_summary(event.get('title') or '', detail.get('arguments')), 'executor': detail.get('executor'), 'nodeId': detail.get('nodeId')})
        elif event_type == 'observation':
            steps.append({'kind': 'observation', 'title': event.get('title') or '工具返回', 'detail': _observation_summary(detail.get('result')), 'executor': detail.get('executor'), 'nodeId': detail.get('nodeId')})
        elif event_type == 'model' and event.get('title') == 'execute' and not detail.get('toolCalls'):
            text = detail.get('content')
            if text:
                steps.append({'kind': 'model', 'title': '模型输出', 'detail': text[:360]})
        elif event_type == 'evaluation':
            steps.append({'kind': 'check', 'title': '结果校验', 'detail': detail.get('status')})
    return steps


def build_pair_detail(root: Path, taskbank: Any, experiment: str, task_id: str) -> dict[str, Any]:
    showcase = build_showcase(root, taskbank, experiment)
    pair = next((item for item in showcase['pairs'] if item['taskId'] == task_id), None)
    if not pair:
        raise KeyError(task_id)
    task = taskbank.task(task_id)
    experiment_root = root / 'artifacts' / 'online-e2e' / experiment
    detail = deepcopy(pair)
    detail['task'] = {key: task.get(key) for key in ['id', 'title', 'task', 'scenario', 'family', 'split', 'recordCount', 'recordIds', 'asOf', 'sourceUrl']}
    detail['runs'] = {}
    for arm in ['baseline', 'rsi']:
        run = _read_run(experiment_root, arm, pair['runs'][arm]['id'])
        detail['runs'][arm] = {
            **pair['runs'][arm],
            'graphNodes': _graph_nodes(run),
            'steps': _trace_steps(run),
            'report': {key: (run.get('submission') or {}).get(key) for key in REPORT_KEYS},
        }
    return detail
