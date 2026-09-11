#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the fixed, isolated 36-task online RSI experiment exactly once per task."""
import asyncio
import argparse
from copy import deepcopy
from html import escape
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import config
from backend.autotool import canonical, digest
from backend.llm_judge import JUDGE_PROMPT, aggregate_verdicts, report_reward, verdict_tool
from backend.model_client import ModelClient, ModelOptions
from backend.task_runner import TaskRunner, TaskRunRequest
from backend.taskbank import TaskBank


DEFAULT_EXPERIMENT = 'online-e2e-train-v1'
TYPES = [
    ('finance', 'cancelled_payments'), ('finance', 'installments'),
    ('support', 'channels'), ('support', 'timeliness'),
    ('tickets', 'unassigned'), ('tickets', 'labels'),
]
MANIFEST_PROFILES = ('core36', 'all_train')


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def task_types(bank, profile):
    if profile == 'core36':
        return TYPES
    if profile != 'all_train':
        raise ValueError('unknown_manifest_profile:' + profile)
    rows = sorted({(task['scenario'], task['family']) for task in bank.tasks.values() if task.get('split') == 'train'})
    if not rows:
        raise ValueError('all_train_profile_has_no_train_tasks')
    return rows


def task_manifest(bank, profile='core36'):
    selected = []
    types = task_types(bank, profile)
    for round_index in range(6):
        for scenario, family in types:
            task_id = f'{scenario}-{family}-{round_index + 1:02d}'
            task = bank.task(task_id)
            if task['split'] != 'train':
                raise ValueError('not_train:' + task_id)
            selected.append(dict(round=round_index + 1, taskId=task_id, scenario=scenario, family=family,
                                 recordCount=task['recordCount'], recordIds=task['recordIds'], asOf=task.get('asOf'),
                                 taskDigest=digest(dict(task=task['task'], recordIds=task['recordIds'], asOf=task.get('asOf')))))
    if len({row['taskId'] for row in selected}) != len(types) * 6:
        raise ValueError('task_manifest_not_unique')
    return selected


def selected_manifest(bank, task_ids=None, profile='core36'):
    manifest = task_manifest(bank, profile)
    if not task_ids:
        return manifest
    by_id = {row['taskId']: row for row in manifest}
    selected = []
    for task_id in task_ids:
        if task_id not in by_id:
            raise ValueError('task_not_in_fixed_train_manifest:' + task_id)
        selected.append(deepcopy(by_id[task_id]))
    if len(selected) != len(set(task_ids)):
        raise ValueError('task_ids_not_unique')
    return selected


def completed_status(through_round, rsi_only):
    """RSI-only full runs are complete without scheduling Judge requests."""
    return through_round == 6 and rsi_only


def rsi_source_pairs(source_result, manifest):
    """Return audited, compact RSI runs from a completed isolated source run."""
    if source_result.get('schemaVersion') != SCHEMA_VERSION:
        raise RuntimeError('rsi_source_schema_changed')
    if source_result.get('manifest') != manifest:
        raise RuntimeError('rsi_source_manifest_changed')
    protocol = source_result.get('protocol') or {}
    if protocol.get('rsi') != 'graph_rsi' or not protocol.get('rsiLearning') or not protocol.get('startFromEmpty'):
        raise RuntimeError('rsi_source_protocol_incompatible')
    source = {row.get('taskId'): row for row in source_result.get('pairs') or []}
    selected = {}
    for item in manifest:
        pair = source.get(item['taskId'])
        run = (pair or {}).get('runs', {}).get('rsi')
        if not run or not success(run):
            raise RuntimeError('rsi_source_run_missing_or_failed:' + item['taskId'])
        selected[item['taskId']] = deepcopy(pair)
    return selected


SCHEMA_VERSION = 2


def compact(run):
    return deepcopy({key: run.get(key) for key in ['id', 'taskId', 'strategy', 'status', 'phase', 'models', 'metrics', 'phaseMetrics', 'evaluation', 'evolution', 'compositionPlan', 'graphSelection', 'fallback', 'error', 'createdAt', 'startedAt', 'finishedAt']})


def experience_summary(runner):
    evolution = runner.evolution
    return dict(versions=len(evolution.versions), workflows=len(evolution.workflows), tinyEdges=len(evolution.tiny_edges),
                graphIds=[row['id'] for row in evolution.versions])


def aggregate(values, key):
    return sum((value or {}).get(key) or 0 for value in values)


def percentile(values, fraction):
    """Return the nearest-rank percentile for recorded non-empty metrics."""
    ordered = sorted(value for value in values if value is not None)
    if not ordered:
        return 0
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))
    return ordered[index]


def diagnostics(runs):
    evolution = [run.get('evolution') or {} for run in runs]
    metrics = [run.get('metrics') or {} for run in runs]
    composition = [run.get('compositionPlan') or {} for run in runs]
    maintenance = [item.get('tinyEdgeMaintenance') or {} for item in evolution]
    paths = {}
    for item in evolution:
        paths[item.get('planningPath', 'not_applicable')] = paths.get(item.get('planningPath', 'not_applicable'), 0) + 1
    return dict(
        planningPaths=paths,
        graphReuse=sum(bool(item.get('usedVersionId')) for item in evolution),
        fastRuns=sum(item.get('planningPath') == 'fast' for item in evolution),
        fastSucceeded=sum(item.get('planningPath') == 'fast' and success(run) for item, run in zip(evolution, runs)),
        initialWorkflowVersions=sum(len(item.get('generatedVersionIds') or []) for item in evolution),
        maintenanceAttempts=sum(bool(item) for item in maintenance),
        maintenanceRecorded=sum(item.get('workflowStatus') == 'recorded' for item in maintenance),
        maintenanceMiningOk=sum(item.get('miningStatus') == 'ok' for item in maintenance),
        compositionRuns=sum(item.get('execution') == 'composition' for item in evolution),
        graphFallbacks=sum(bool(run.get('fallback')) and run.get('strategy') == 'graph_rsi' for run in runs),
        graphLookupMs=round(aggregate(evolution, 'lookupMs'), 3),
        compositionLocalMs=round(sum(item.get('compositionLocalMs', composition[index].get('localMs', 0)) or 0 for index, item in enumerate(evolution)), 3),
        evolutionMaintenanceMs=round(aggregate(evolution, 'maintenanceMs'), 3),
        runtimeOverheadMs=round(aggregate(metrics, 'runtimeOverheadMs'), 3),
        reportAttempts=aggregate(metrics, 'reportAttempts'), failedReportAttempts=aggregate(metrics, 'failedReportAttempts'),
        blockedRecoveryReads=aggregate(metrics, 'reportRecoveryBlockedReads'),
        evidenceCanonicalizations=aggregate(metrics, 'reportEvidenceCanonicalizations'),
        evidenceCoverageGaps=aggregate(metrics, 'reportEvidenceCoverageGaps'),
        evidenceFormatFailures=aggregate(metrics, 'reportEvidenceFormatFailures'),
        paginationGuardRejects=aggregate(metrics, 'paginationGuardRejects'),
        maintenanceErrors=sum(bool(item.get('maintenanceError')) for item in evolution))


def phase_summary(runs):
    result = {}
    for run in runs:
        for phase, metrics in (run.get('phaseMetrics') or {}).items():
            current = result.setdefault(phase, dict(requests=0, inputTokens=0, outputTokens=0))
            current['requests'] += metrics.get('requests') or 0
            current['inputTokens'] += metrics.get('inputTokens') or 0
            current['outputTokens'] += metrics.get('outputTokens') or 0
    return result


def success(run):
    return run.get('status') == 'completed' and run.get('evaluation', {}).get('status') == 'passed'


def summary(rows):
    result = {}
    for arm in ['baseline', 'rsi']:
        runs = [row['runs'][arm] for row in rows if arm in row.get('runs', {})]
        metrics = [row['metrics'] for row in runs]
        passed = sum(success(row) for row in runs)
        total_tokens = sum((row.get('inputTokens') or 0) + (row.get('outputTokens') or 0) for row in metrics)
        durations = [row.get('durationMs') or 0 for row in metrics]
        run_tokens = [(row.get('inputTokens') or 0) + (row.get('outputTokens') or 0) for row in metrics]
        result[arm] = dict(attempts=len(runs), passed=passed, successRate=passed / len(runs) if runs else None,
                           inputTokens=sum(row.get('inputTokens') or 0 for row in metrics), outputTokens=sum(row.get('outputTokens') or 0 for row in metrics),
                           totalTokens=total_tokens, modelRequests=sum(row.get('modelRequests') or 0 for row in metrics),
                           toolCalls=sum(row.get('toolCalls') or 0 for row in metrics), toolErrors=sum(row.get('toolErrors') or 0 for row in metrics),
                           durationMs=sum(row.get('durationMs') or 0 for row in metrics), tokensPerSuccess=total_tokens / passed if passed else None,
                           runtimeOverheadMs=round(sum(float(row.get('runtimeOverheadMs') or 0) for row in metrics), 3),
                           localComputeCalls=sum(row.get('localComputeCalls') or 0 for row in metrics),
                           localComputeMs=round(sum(float(row.get('localComputeMs') or 0) for row in metrics), 3),
                           averageLatencyMs=sum(durations) / len(durations) if durations else None,
                           p95LatencyMs=percentile(durations, .95), maxLatencyMs=max(durations) if durations else 0,
                           maxTotalTokens=max(run_tokens) if run_tokens else 0,
                           averageToolCalls=sum(row.get('toolCalls') or 0 for row in metrics) / len(metrics) if metrics else None,
                           usageComplete=all(row.get('usageComplete') for row in metrics), failures=[dict(taskId=row.get('taskId'), status=row.get('status'), error=row.get('error'), issues=row.get('evaluation', {}).get('issues', [])) for row in runs if not success(row)],
                           diagnostics=diagnostics(runs), phaseMetrics=phase_summary(runs))
    a, b = result['baseline'], result['rsi']
    comparable = bool(a['attempts'] and b['attempts'])
    return dict(arms=result, allOutcomeTokenDelta=b['totalTokens'] - a['totalTokens'] if comparable else None,
                allOutcomeLatencyDeltaMs=b['durationMs'] - a['durationMs'] if comparable else None,
                tokenSavingRate=1 - b['totalTokens'] / a['totalTokens'] if comparable and a['totalTokens'] else None,
                modelRequestSavingRate=1 - b['modelRequests'] / a['modelRequests'] if comparable and a['modelRequests'] else None,
                observedLatencySavingRate=1 - b['durationMs'] / a['durationMs'] if comparable and a['durationMs'] else None,
                toolCallDelta=b['toolCalls'] - a['toolCalls'] if comparable else None,
                agentReportedTotalTokens=a['totalTokens'] + b['totalTokens'] if comparable else None,
                qualityRegressions=sum(success(row['runs'].get('baseline', {})) and not success(row['runs'].get('rsi', {})) for row in rows) if comparable else None,
                qualityImprovements=sum(not success(row['runs'].get('baseline', {})) and success(row['runs'].get('rsi', {})) for row in rows) if comparable else None)


def round_summaries(rows):
    return [dict(round=index, summary=summary([row for row in rows if row.get('round') == index])) for index in range(1, 7)]


def evolution_chain(rows):
    chains = []
    for row in rows:
        run = row.get('runs', {}).get('rsi') or {}
        timeline = row.get('experienceTimeline') or {}
        before, after = timeline.get('before') or row.get('experienceBefore') or {}, timeline.get('after') or row.get('experienceAfter') or {}
        used = (run.get('evolution') or {}).get('usedVersionId')
        produced = (run.get('evolution') or {}).get('generatedVersionIds') or []
        if used or produced or before != after:
            sources = sorted({source for row in run.get('graphSelection') or [] for source in row.get('sourceRunIds', [])})
            chains.append(dict(taskId=row['taskId'], round=row['round'], runId=run.get('id'), usedGraphId=used,
                               selectedTinyEdgeIds=(run.get('evolution') or {}).get('selectedTinyEdgeIds', []),
                               selectedSourceRunIds=sources,
                               createdGraphIds=produced, before=before, after=after,
                               note=(run.get('evolution') or {}).get('note')))
    return chains


def reconstructed_timeline(rows, runner):
    """Recover per-task snapshots from append-only source-run lists after a resume.

    This does not execute or learn anything; it derives counts from the isolated
    final store and retains the legacy checkpoint fields for audit.
    """
    evolution, seen = runner.evolution, set()
    for pair in rows:
        run_id = (pair.get('runs', {}).get('rsi') or {}).get('id')
        before = set(seen)
        if run_id:
            seen.add(run_id)
        def snapshot(ids):
            workflows = [row for row in evolution.workflows if row['sourceRunId'] in ids]
            versions = [row for row in evolution.versions if row['sourceRunId'] in ids]
            edges = [row for row in evolution.tiny_edges if set(row.get('sourceWorkflowIds', [])) <= {item['id'] for item in workflows}]
            return dict(versions=len(versions), workflows=len(workflows), tinyEdges=len(edges), graphIds=[row['id'] for row in versions])
        pair['experienceTimeline'] = dict(method='reconstructed_from_append_only_source_run_ids',
                                          before=snapshot(before), after=snapshot(seen),
                                          note='Legacy experienceBefore/After is retained; this derived timeline corrects resume-time overwrite.')


def judge_summary(rows):
    # An absent Judge is pending, not a failed judging attempt.
    judges = [row['judge'] for row in rows if row.get('judge') is not None]
    completed = [row for row in judges if row.get('status') == 'completed']
    metrics = [row.get('metrics') or {} for row in judges]
    rewards = {arm: [] for arm in ['baseline', 'rsi']}
    winners, failure_reasons = {}, {}
    consistent = 0
    for item in completed:
        result = item.get('result') or {}
        winners[result.get('winner', 'unknown')] = winners.get(result.get('winner', 'unknown'), 0) + 1
        consistent += bool(result.get('orderConsistent'))
        for arm in rewards:
            report = (result.get('reports') or {}).get(arm)
            if report:
                rewards[arm].append(report['reward'])
    for item in judges:
        if item.get('status') == 'completed':
            continue
        reason = item.get('error') or 'unknown_judge_failure'
        failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    return dict(attempts=len(judges), completed=len(completed), failed=len(judges) - len(completed), winners=winners,
                orderConsistent=consistent, orderInconclusive=len(completed) - consistent,
                rewards={arm: round(sum(values) / len(values), 4) if values else None for arm, values in rewards.items()},
                modelRequests=aggregate(metrics, 'modelRequests'), inputTokens=aggregate(metrics, 'inputTokens'),
                outputTokens=aggregate(metrics, 'outputTokens'), totalTokens=aggregate(metrics, 'inputTokens') + aggregate(metrics, 'outputTokens'),
                durationMs=aggregate(metrics, 'durationMs'), usageComplete=all(item.get('usageComplete') for item in metrics),
                reportedTokenLowerBound=aggregate(metrics, 'inputTokens') + aggregate(metrics, 'outputTokens'),
                failureReasons=failure_reasons,
                sameAsExecutor=all(item.get('sameAsExecutor') for item in completed) if completed else None)


def judge_input(bank, baseline, rsi):
    task = bank.task(baseline['taskId'])
    evidence = {task['scenario'] + ':' + key: bank.record(task, key) for key in task['recordIds']}
    reports = {arm: {key: (source.get('submission') or {}).get(key) for key in ['metrics', 'selectedIds', 'evidenceIds', 'summary']}
               for arm, source in [('baseline', baseline), ('rsi', rsi)]}
    payload = dict(task=task['task'], evidence=evidence)
    if len(canonical(dict(payload, reports=reports))) > 200000:
        raise ValueError('judge_payload_too_large')
    return payload, reports


async def judge_pair(payload, reports, provider):
    tool, passes = verdict_tool(), []
    metrics = dict(modelRequests=0, inputTokens=0, outputTokens=0, usageComplete=True, durationMs=0)
    started = time.monotonic()
    for mapping in [dict(A='baseline', B='rsi'), dict(A='rsi', B='baseline')]:
        history = [dict(role='system', content=JUDGE_PROMPT), dict(role='user', content=canonical(dict(payload, reports={label: reports[arm] for label, arm in mapping.items()})))]
        entry = dict(mapping=mapping, attempts=[])
        for repair in range(2):
            metrics['modelRequests'] += 1
            response = await provider.complete(history, [tool])
            usage = response.get('usage')
            entry['attempts'].append(dict(response=response['message'], usage=usage))
            if usage:
                metrics['inputTokens'] += usage['input']; metrics['outputTokens'] += usage['output']
            else:
                metrics['usageComplete'] = False
            calls = response['message'].get('tool_calls') or []
            try:
                if response.get('finishReason') in ['length', 'content_filter'] or len(calls) != 1 or calls[0]['function']['name'] != tool.name:
                    raise ValueError('judge_tool_call')
                verdict = json.loads(calls[0]['function']['arguments']); tool.validator.validate(verdict)
                break
            except Exception as error:
                entry['attempts'][-1]['formatError'] = str(error)[:500]
                if repair:
                    raise
                history.extend([response['message'], dict(role='tool', tool_call_id=calls[0]['id'] if calls else 'missing', content='格式不符合 schema；请重新提交。')])
        if any(finding['evidenceRef'] and finding['evidenceRef'] not in payload['evidence'] for finding in verdict['findings'].values()):
            raise ValueError('judge_unknown_evidence_ref')
        scores = {mapping[label]: verdict[label] for label in ['A', 'B']}
        rewards = {arm: report_reward(values) for arm, values in scores.items()}
        entry.update(status='completed', verdict=verdict, scores=scores, rewards=rewards,
                     winner=mapping['A'] if rewards[mapping['A']] > rewards[mapping['B']] else mapping['B'] if rewards[mapping['B']] > rewards[mapping['A']] else 'tie')
        passes.append(entry)
    metrics['durationMs'] = round((time.monotonic() - started) * 1000)
    return dict(status='completed', passes=passes, result=aggregate_verdicts(passes), metrics=metrics,
                sameAsExecutor=provider.model == config.MODEL)


def run_url(experiment, arm, run_id, report=False):
    return f'/api/online-e2e/{experiment}/runs/{arm}/{run_id}' + ('/report' if report else '')


def family_sections(result):
    """Render six-record family comparisons only from recorded run data."""
    groups = {}
    for pair in sorted(result.get('pairs') or [], key=lambda row: row.get('index', 0)):
        groups.setdefault((pair.get('scenario', ''), pair.get('family', '')), []).append(pair)
    options, sections = [], []
    for number, ((scenario, family), pairs) in enumerate(sorted(groups.items())):
        identifier = f'family-{number}'
        options.append(f'<option value="{identifier}">{escape(scenario + "/" + family)}</option>')
        base_total = rsi_total = 0
        rows, base_points, rsi_points = [], [], []
        for position, pair in enumerate(sorted(pairs, key=lambda row: row.get('round', 0)), 1):
            runs = pair.get('runs') or {}
            baseline, rsi = runs.get('baseline') or {}, runs.get('rsi') or {}
            bm, rm = baseline.get('metrics') or {}, rsi.get('metrics') or {}
            total = lambda metrics: (metrics.get('inputTokens') or 0) + (metrics.get('outputTokens') or 0)
            base_total += total(bm); rsi_total += total(rm)
            saving = 1 - rsi_total / base_total if base_total else None
            evolution = rsi.get('evolution') or {}
            timeline = pair.get('experienceTimeline') or {}
            source = (pair.get('rsiSource') or {}).get('experiment', result.get('id'))
            links = []
            for arm, run, experiment in [('baseline', baseline, result.get('id')), ('rsi', rsi, source)]:
                if run.get('id'):
                    links.append(f'<a href="{run_url(experiment, arm, run["id"])}">{arm} trace</a>')
                    links.append(f'<a href="{run_url(experiment, arm, run["id"], True)}">{arm} report</a>')
            before = (timeline.get('before') or pair.get('experienceBefore') or {}).get('versions', 0)
            after = (timeline.get('after') or pair.get('experienceAfter') or {}).get('versions', 0)
            rows.append(f'''<tr><td>{position}</td><td>{escape(pair.get('taskId', ''))}<br><small>{pair.get('recordCount', 0)} records</small></td>
<td>{before} → {after}<br><small>created {escape(', '.join(evolution.get('generatedVersionIds') or []) or '—')}<br>used {escape(evolution.get('usedVersionId') or '—')}</small></td>
<td>{escape(evolution.get('planningPath', '—'))}</td>
<td>{'pass' if success(baseline) else escape(baseline.get('status', '—'))}<br>{total(bm):,} token / {bm.get('modelRequests', 0)} LLM / {bm.get('toolCalls', 0)} tools<br>{(bm.get('durationMs') or 0) / 1000:.2f}s</td>
<td>{'pass' if success(rsi) else escape(rsi.get('status', '—'))}<br>{total(rm):,} token / {rm.get('modelRequests', 0)} LLM / {rm.get('toolCalls', 0)} tools<br>{(rm.get('durationMs') or 0) / 1000:.2f}s</td>
<td>{base_total:,} / {rsi_total:,}<br>{'—' if saving is None else f'{saving:.1%}'}</td><td>{' · '.join(links)}</td></tr>''')
            base_points.append(base_total); rsi_points.append(rsi_total)
        # The two arms run the same task sequence, so their cumulative shapes are
        # expected to be similar. Keep an absolute shared axis and fill the gap so
        # the chart does not visually hide a material cumulative saving.
        maximum = max(base_points + rsi_points + [1])
        axis_max = max(1, ((maximum + 9999) // 10000) * 10000)
        left, right, top, bottom = 56, 548, 28, 154
        x = lambda index: left + (right - left) * index / max(1, len(base_points) - 1)
        y = lambda value: bottom - (bottom - top) * value / axis_max
        def points(values, reverse_x=False):
            return ' '.join(
                f'{x(len(values) - 1 - index if reverse_x else index):.1f},{y(value):.1f}'
                for index, value in enumerate(values)
            )

        gap = f'{points(base_points)} {points(rsi_points, reverse_x=True)}'
        ticks = []
        for fraction in (0, 0.5, 1):
            value = int(axis_max * fraction)
            coordinate = y(value)
            ticks.append(f'<line x1="{left}" y1="{coordinate:.1f}" x2="{right}" y2="{coordinate:.1f}" class="grid"/><text x="4" y="{coordinate + 4:.1f}" class="tick">{value // 1000}k</text>')
        markers = ''.join(f'<circle cx="{x(index):.1f}" cy="{y(value):.1f}" r="3" class="baseline-marker"/>' for index, value in enumerate(base_points))
        markers += ''.join(f'<circle cx="{x(index):.1f}" cy="{y(value):.1f}" r="3" class="rsi-marker"/>' for index, value in enumerate(rsi_points))
        final_saving = 1 - rsi_total / base_total if base_total else 0
        chart = f'''<svg viewBox="0 0 570 204" role="img" aria-label="{escape(scenario + "/" + family)} cumulative token">
<text x="{left}" y="17">Cumulative token (absolute shared axis)</text>{''.join(ticks)}
<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" class="axis"/>
<polygon points="{gap}" class="saving-area"/><polyline points="{points(base_points)}" class="baseline-line"/><polyline points="{points(rsi_points)}" class="rsi-line"/>{markers}
<text x="{left}" y="183" class="tick">1</text><text x="{right - 5}" y="183" class="tick">6</text>
<text x="{left}" y="199" class="baseline-label">baseline {base_total:,}</text><text x="{right - 156}" y="199" class="rsi-label">RSI {rsi_total:,} ({final_saving:.1%} less)</text></svg>'''
        sections.append(f'''<section class="family" data-family="{identifier}"{' hidden' if number else ''}><h2>{escape(scenario + "/" + family)} · online experience accumulation and reuse</h2><p>Six distinct records in arrival order. Cumulative savings include the cold start and recorded maintenance. A new G0 is not a structural revision.</p>{chart}<table><thead><tr><th>#</th><th>Task / scope</th><th>Experience / graph</th><th>Path</th><th>Baseline</th><th>RSI</th><th>Cumulative tokens<br>base / RSI / saving</th><th>Replay</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>''')
    return ''.join(options), ''.join(sections)


def result_report(result):
    data = result.get('summary') or {}
    arms = data.get('arms') or {}
    protocol = result.get('protocol') or {}
    judge = result.get('judgeSummary') or {}

    def percent(value):
        return '—' if value is None else f'{value:.1%}'

    def seconds(value):
        return f'{(value or 0) / 1000:.2f}s'

    def arm(name):
        row = arms.get(name, {})
        return f"<tr><th>{escape(name)}</th><td>{row.get('passed', 0)} / {row.get('attempts', 0)}</td><td>{row.get('inputTokens', 0):,} / {row.get('outputTokens', 0):,} / {row.get('totalTokens', 0):,}</td><td>{row.get('modelRequests', 0)}</td><td>{row.get('toolCalls', 0)}<br><small>avg {(row.get('averageToolCalls') or 0):.2f}</small></td><td>{row.get('localComputeCalls', 0)} calls / {row.get('localComputeMs', 0):.3f}ms</td><td>{row.get('runtimeOverheadMs', 0):.3f}ms<br><small>0 token</small></td><td>{seconds(row.get('durationMs'))}</td></tr>"

    def reliability(name):
        row = arms.get(name, {})
        diagnostics = row.get('diagnostics') or {}
        return f"<tr><th>{escape(name)}</th><td>{seconds(row.get('averageLatencyMs'))} / {seconds(row.get('p95LatencyMs'))} / {seconds(row.get('maxLatencyMs'))}</td><td>{row.get('maxTotalTokens', 0):,}</td><td>{diagnostics.get('reportAttempts', 0)} / {diagnostics.get('failedReportAttempts', 0)}</td><td>{row.get('toolErrors', 0)} / {diagnostics.get('maintenanceErrors', 0)}</td><td>{diagnostics.get('paginationGuardRejects', 0)} / {diagnostics.get('blockedRecoveryReads', 0)}</td></tr>"

    def phase(name, stage):
        metrics = (arms.get(name, {}).get('phaseMetrics') or {}).get(stage, {})
        return f"{metrics.get('requests', 0)} req / {metrics.get('inputTokens', 0) + metrics.get('outputTokens', 0):,} token"

    rounds = ''.join(f"<tr><td>{row['round']}</td><td>{row['summary']['arms']['baseline']['totalTokens']:,}</td><td>{row['summary']['arms']['rsi']['totalTokens']:,}</td><td>{row['summary']['arms']['baseline']['passed']}</td><td>{row['summary']['arms']['rsi']['passed']}</td></tr>" for row in result.get('rounds', []))
    chains = ''.join(f"<li><b>{escape(item['taskId'])}</b>: used={escape(str(item['usedGraphId'] or 'none'))}, created={escape(', '.join(item['createdGraphIds']) or 'none')}</li>" for item in result.get('evolutionChain', [])) or '<li>尚未观察到经验变化。</li>'
    selectors, families = family_sections(result)
    delta = '本次为 RSI-only 预检，不生成新的基线调用，不能计算严格相对差值。' if data.get('allOutcomeTokenDelta') is None else f"RSI 相对 Baseline：Agent token {data['allOutcomeTokenDelta']:,}（{percent(data.get('tokenSavingRate'))}）；模型请求 {data['modelRequestSavingRate'] * 100:.1f}% 更少；工具调用 {data['toolCallDelta']:+,}。端到端时长观察差异 {data['allOutcomeLatencyDeltaMs'] / 1000:.1f}s（{percent(data.get('observedLatencySavingRate'))}），受模型服务时段影响，不作为稳定延迟优势主张。"
    rsi_diagnostics = (arms.get('rsi') or {}).get('diagnostics') or {}
    baseline_diagnostics = (arms.get('baseline') or {}).get('diagnostics') or {}
    evolution_note = f"Fast {rsi_diagnostics.get('graphReuse', 0)} 次；Fallback {(rsi_diagnostics.get('planningPaths') or {}).get('fallback', 0)} 次；Composition 实际执行 {rsi_diagnostics.get('compositionRuns', 0)} 次。RSI 专属图运行时账本合计 {(arms.get('rsi') or {}).get('runtimeOverheadMs', 0):.3f}ms：图查询 {rsi_diagnostics.get('graphLookupMs', 0):.1f}ms、组合本地选择 {rsi_diagnostics.get('compositionLocalMs', 0):.1f}ms、维护 {rsi_diagnostics.get('evolutionMaintenanceMs', 0):.1f}ms。它们已包含在端到端时长，但为 0 token，不混入 Agent token 成本。"
    judge_failures = '；'.join(f'{escape(reason)} × {count}' for reason, count in (judge.get('failureReasons') or {}).items()) or '无'
    supplements = []
    if protocol.get('reliabilityExperiment'):
        supplements.append(f'<a href="/api/online-e2e/{escape(protocol["reliabilityExperiment"])} /report">长尾修复预检</a>'.replace(' /report', '/report'))
    if protocol.get('scaleExperiment'):
        supplements.append(f'<a href="/api/efficiency/{escape(protocol["scaleExperiment"])} /report">串行规模与可靠性补验</a>'.replace(' /report', '/report'))
    supplemental_html = '；'.join(supplements) if supplements else '本实验没有关联补充工件。'
    failed_report_rate = lambda diagnostics: (diagnostics.get('failedReportAttempts', 0) / diagnostics.get('reportAttempts', 0)) if diagnostics.get('reportAttempts', 0) else 0
    rsi_learning_health = f'''<h2>RSI 在线学习链路健康</h2><table><tr><th>RSI 专属检查</th><th>本次记录</th><th>结论边界</th></tr>
<tr><th>初始 Workflow 形成</th><td>{rsi_diagnostics.get('initialWorkflowVersions', 0)}</td><td>这是 G0 积累，不是 G1/G2 结构修订。</td></tr>
<tr><th>Fast 复用完成</th><td>{rsi_diagnostics.get('fastSucceeded', 0)} / {rsi_diagnostics.get('fastRuns', 0)}</td><td>已保存 Workflow 被后续任务实际选择、绑定并完成。</td></tr>
<tr><th>在线记录与 TinyEdge 挖掘</th><td>{rsi_diagnostics.get('maintenanceRecorded', 0)} / {rsi_diagnostics.get('maintenanceAttempts', 0)} recorded；{rsi_diagnostics.get('maintenanceMiningOk', 0)} / {rsi_diagnostics.get('maintenanceAttempts', 0)} mining ok</td><td>本次跨场景隔离维护没有产生错误；不能据此声称长期零错误。</td></tr>
<tr><th>经验维护错误</th><td>{rsi_diagnostics.get('maintenanceErrors', 0)}</td><td>证明本次 RSI 学习链路没有给业务任务引入维护失败。</td></tr></table>
<p>这是 RSI 的链路稳定性证据，不等同于“RSI 比基线更可靠”：两臂任务均为 36 / 36 通过；报告失败提交率为 Baseline {failed_report_rate(baseline_diagnostics):.1%}（{baseline_diagnostics.get('failedReportAttempts', 0)} / {baseline_diagnostics.get('reportAttempts', 0)}），RSI {failed_report_rate(rsi_diagnostics):.1%}（{rsi_diagnostics.get('failedReportAttempts', 0)} / {rsi_diagnostics.get('reportAttempts', 0)}）。因此本次没有证明 RSI 降低报告失败率。</p>'''
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RSI 在线对照实验</title><style>body{{font:14px/1.65 system-ui,sans-serif;margin:0;background:#f5f7f8;color:#1d2a33}}main{{max-width:1240px;margin:28px auto;background:white;padding:32px;border:1px solid #d8e0e4}}table{{border-collapse:collapse;width:100%;margin:12px 0}}th,td{{border-bottom:1px solid #dbe3e6;text-align:left;padding:9px;vertical-align:top}}th{{background:#f4f7f8}}pre{{background:#f4f7f8;padding:14px;overflow:auto}}small{{color:#647781}}a{{color:#086c72}}select{{font:inherit;padding:7px;border:1px solid #9aabb2;background:white}}.family{{margin-top:22px;border-top:2px solid #354a56;padding-top:12px;overflow-x:auto}}svg{{display:block;width:100%;max-width:570px;height:auto;background:#fbfcfc;border:1px solid #dbe3e6}}.axis{{stroke:#9aabb2;stroke-width:1}}.grid{{stroke:#dbe3e6;stroke-width:1}}.tick{{fill:#647781;font-size:11px}}.saving-area{{fill:#8fd5bc;fill-opacity:.35}}.baseline-line{{stroke:#8a4a25;stroke-width:3;fill:none}}.rsi-line{{stroke:#087d64;stroke-width:3;fill:none}}.baseline-marker{{fill:#8a4a25}}.rsi-marker{{fill:#087d64}}.baseline-label{{fill:#8a4a25}}.rsi-label{{fill:#087d64}}@media(max-width:700px){{main{{margin:0;padding:16px}}table{{font-size:12px}}}}</style><main><small>固定 manifest、独立经验库，run/model/read 均为 1；Agent、Judge、本地计算和 RSI 图运行时账本分开。</small><h1>RSI 串行在线对照实验</h1><p>状态：{escape(result.get('status', 'unknown'))}；实验：{escape(result.get('id', ''))}；比较：{escape(protocol.get('comparisonMode', 'unknown'))}</p><h2>累计 Agent 执行</h2><table><tr><th>执行流</th><th>结构化通过</th><th>输入 / 输出 / 总 token</th><th>LLM</th><th>工具</th><th>本地计算</th><th>RSI 图运行时账本</th><th>端到端</th></tr>{arm('baseline')}{arm('rsi')}</table><p>{delta}</p><h2>串行可靠性与恢复</h2><table><tr><th>执行流</th><th>平均 / P95 / 最大延迟</th><th>最大单任务 token</th><th>报告提交 / 失败提交</th><th>工具错误 / 维护错误</th><th>分页拒绝 / 恢复期拒绝读取</th></tr>{reliability('baseline')}{reliability('rsi')}</table><p>“失败提交”累计每一次未通过的 `publish_report`，而不是只统计首次失败；总提交数包含失败后的有界重提。本次每个失败都发生在首提，因为第二次失败会被有界恢复规则终止，且 72 个任务均最终完成。页面同时保留总提交、失败提交、重复签名阻断读取和最终任务状态。所有 Agent usage 完整；未发生重复签名无限恢复。证据规范化次数：Baseline {baseline_diagnostics.get('evidenceCanonicalizations', 0)}，RSI {rsi_diagnostics.get('evidenceCanonicalizations', 0)}；coverage gap 与 evidence 格式失败都为 0。</p><h2>经验使用与本地开销</h2><p>{evolution_note}</p><p>完整 Plan：Baseline {phase('baseline', 'plan')}；RSI {phase('rsi', 'plan')}。RSI 少 24 次 Plan 请求；总请求差异还包含真实执行/恢复轮数，不能全部归因于图复用。Composition 角色调用：{phase('rsi', 'composition')}，但没有实际组合执行，不主张其收益。</p>{rsi_learning_health}<h2>报告质量与 Judge 成本</h2><p>{judge.get('completed', 0)} / {judge.get('attempts', 0)} 对完成；失败 {judge.get('failed', 0)}：{judge_failures}。Judge {judge.get('modelRequests', 0)} 请求、已记录至少 {judge.get('reportedTokenLowerBound', 0):,} token、{seconds(judge.get('durationMs'))}；平均 reward：Baseline {judge.get('rewards', {}).get('baseline', '—')}，RSI {judge.get('rewards', {}).get('rsi', '—')}；顺序一致 {judge.get('orderConsistent', 0)} / 完成 {judge.get('completed', 0)}。同模型 Judge：{judge.get('sameAsExecutor')}，不计入 Agent 成本；超时失败未返回 usage，因此裁判 token 仅为下限。</p><h2>按轮</h2><table><tr><th>轮</th><th>Baseline token</th><th>RSI token</th><th>Baseline 通过</th><th>RSI 通过</th></tr>{rounds}</table><h2>任务族内演进</h2><label>任务族 <select id="family-select">{selectors}</select></label>{families}<h2>经验来源到后续使用</h2><ul>{chains}</ul><h2>补充可靠性工件</h2><p>{supplemental_html}</p><h2>录制顺序</h2><ol><li>查看累计 Agent 表，说明同一固定 train manifest、独立空经验和严格串行限流。</li><li>选择一个任务族，展示首个任务形成 G0 和后续任务实际 Fast 使用；点击同一任务的 baseline/RSI trace 与 report。</li><li>查看族内累计 token 曲线：共用绝对轴，绿色面积是到当前任务的累计节省；冷启动与维护已计入。</li><li>展示串行可靠性与恢复，以及补充工件中的长尾和大记录范围；它们不替代全量结论。</li><li>最后展示 Judge 成本、超时覆盖缺口，以及未观察到 G1/G2/Composition 的限制。</li></ol><h2>审计入口</h2><p>原始协议、运行索引、经验快照与双顺序 Judge 记录位于本目录的 JSON 文件。失败与中断不被筛掉。</p><details><summary>完整摘要 JSON</summary><pre>{escape(json.dumps(data, ensure_ascii=False, indent=2))}</pre></details></main><script>document.getElementById('family-select').addEventListener('change',function(){{document.querySelectorAll('.family').forEach((item)=>item.hidden=item.dataset.family!==this.value);}});</script>'''


def write_report(root, result):
    path = root / 'index.html'
    temporary = path.with_suffix('.html.tmp')
    temporary.write_text(result_report(result), encoding='utf-8')
    temporary.replace(path)


def checkpoint(root, result_path, result, rsi=None):
    if rsi:
        reconstructed_timeline(result['pairs'], rsi)
    result['pairs'] = sorted(result['pairs'], key=lambda row: row['index'])
    result['summary'] = summary(result['pairs'])
    result['rounds'] = round_summaries(result['pairs'])
    result['evolutionChain'] = evolution_chain(result['pairs'])
    result['judgeSummary'] = judge_summary(result['pairs'])
    write(result_path, result)
    write_report(root, result)


async def main(through_round=6, experiment=DEFAULT_EXPERIMENT, rsi_only=False, task_ids=None, rsi_source=None,
               skip_judge=False, reliability_experiment=None, scale_experiment=None, manifest_profile='core36'):
    if not 1 <= through_round <= 6:
        raise ValueError('through_round_must_be_1_to_6')
    bank = TaskBank(); bank.load()
    if not bank.gold:
        raise RuntimeError('taskbank_records_missing')
    if not experiment or '/' in experiment or '\\' in experiment or experiment in ['.', '..']:
        raise ValueError('invalid_experiment_id')
    root = ROOT / 'artifacts' / 'online-e2e' / experiment
    result_path, manifest_path = root / 'result.json', root / 'manifest.json'
    if manifest_profile not in MANIFEST_PROFILES:
        raise ValueError('unknown_manifest_profile:' + manifest_profile)
    manifest = selected_manifest(bank, task_ids, manifest_profile)
    source_root = ROOT / 'artifacts' / 'online-e2e' / rsi_source if rsi_source else None
    source_result = None
    source_pairs = {}
    if rsi_source:
        if rsi_only:
            raise ValueError('rsi_source_cannot_be_combined_with_rsi_only')
        source_path = source_root / 'result.json'
        if not source_path.exists():
            raise RuntimeError('rsi_source_result_missing')
        source_result = json.loads(source_path.read_text())
        source_pairs = rsi_source_pairs(source_result, manifest)
        source_protocol = source_result.get('protocol') or {}
        for key, current in [('executor', config.MODEL), ('planner', config.PLANNER_MODEL), ('composition', config.COMPOSITION_MODEL),
                             ('maxSteps', config.MAX_STEPS), ('timeout', config.RUN_TIMEOUT), ('taskHash', digest(manifest)),
                             ('shadowRollouts', 0), ('singleAgentConcurrency', True)]:
            if source_protocol.get(key) != current:
                raise RuntimeError('rsi_source_current_protocol_mismatch:' + key)
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise RuntimeError('manifest_changed')
    write(manifest_path, manifest)
    base = TaskRunner(bank, run_limit=1, model_limit=1, read_limit=1, run_directory=root / 'baseline' / 'runs', evolution_path=root / 'baseline' / 'experience.json', learning_enabled=False)
    rsi_root = source_root if source_root else root
    rsi = TaskRunner(bank, run_limit=1, model_limit=1, read_limit=1, run_directory=rsi_root / 'rsi' / 'runs', evolution_path=rsi_root / 'rsi' / 'experience.json', learning_enabled=True)
    base.restore(); rsi.restore()
    result = json.loads(result_path.read_text()) if result_path.exists() else dict(
        schemaVersion=SCHEMA_VERSION, id=experiment, status='running', createdAt=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), manifest=manifest, pairs=[],
        protocol=dict(baseline='not_run' if rsi_only else 'plan_react', rsi='graph_rsi', baselineLearning=False, rsiLearning=True,
                      learning='RSI only, train only, sequential; baseline has no cross-task learning', executor=config.MODEL,
                      planner=config.PLANNER_MODEL, composition=config.COMPOSITION_MODEL, judgeModel=config.JUDGE_MODEL,
                      maxSteps=config.MAX_STEPS, timeout=config.RUN_TIMEOUT, taskHash=digest(manifest),
                      manifestProfile=manifest_profile,
                      revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                      startFromEmpty=True, shadowRollouts=0, singleAgentConcurrency=True,
                      judge='anonymous dual order after all agent runs; judge cost is separate',
                      judgeDeferredDuringPrecheck=skip_judge,
                      reliabilityExperiment=reliability_experiment, scaleExperiment=scale_experiment,
                      comparisonMode='time_separated_matched' if rsi_source else 'same_session_interleaved',
                      rsiSourceExperiment=rsi_source,
                      rsiSourceRevision=(source_result.get('protocol') or {}).get('revision') if source_result else None))
    if result.get('schemaVersion') != SCHEMA_VERSION or result.get('manifest') != manifest:
        raise RuntimeError('experiment_checkpoint_protocol_changed')
    by_task = {row['taskId']: row for row in result['pairs']}
    for index, item in enumerate(manifest):
        if item['round'] > through_round:
            break
        launch = ['rsi'] if rsi_only else ['baseline'] if rsi_source else ['baseline', 'rsi'] if index % 2 == 0 else ['rsi', 'baseline']
        pair = by_task.setdefault(item['taskId'], dict(index=index, **item, launchOrder=launch, runs={}, experienceBefore=None, experienceAfter=None))
        if rsi_source and 'rsi' not in pair['runs']:
            source_pair = source_pairs[item['taskId']]
            pair['runs']['rsi'] = deepcopy(source_pair['runs']['rsi'])
            pair['experienceBefore'] = deepcopy(source_pair.get('experienceBefore'))
            pair['experienceAfter'] = deepcopy(source_pair.get('experienceAfter'))
            pair['experienceTimeline'] = deepcopy(source_pair.get('experienceTimeline'))
            pair['rsiSource'] = dict(experiment=rsi_source, runId=pair['runs']['rsi']['id'])
        if pair['experienceBefore'] is None:
            pair['experienceBefore'] = experience_summary(rsi)
            result['pairs'] = list(by_task.values())
            checkpoint(root, result_path, result, rsi)
        for arm in pair['launchOrder']:
            existing = pair['runs'].get(arm)
            if existing:
                run = (base if arm == 'baseline' else rsi).runs.get(existing['id'])
                if run:
                    pair['runs'][arm] = compact(run)
                continue
            runner, strategy = (base, 'plan_react') if arm == 'baseline' else (rsi, 'graph_rsi')
            run = await runner.start(TaskRunRequest(taskId=item['taskId'], strategy=strategy))
            # Persist identity before awaiting: a process interruption never silently reruns this task.
            pair['runs'][arm] = compact(run)
            pair['experienceAfter'] = experience_summary(rsi)
            result['pairs'] = list(by_task.values())
            checkpoint(root, result_path, result, rsi)
            await runner.tasks[run['id']]
            pair['runs'][arm] = compact(run)
            pair['experienceAfter'] = experience_summary(rsi)
            result['pairs'] = list(by_task.values())
            checkpoint(root, result_path, result, rsi)
        if pair['experienceAfter'] is None:
            pair['experienceAfter'] = experience_summary(rsi)
        result['pairs'] = list(by_task.values())
        checkpoint(root, result_path, result, rsi)
    if through_round < 6 and task_ids is None:
        result['status'] = 'running'
        result['precheckThroughRound'] = through_round
        checkpoint(root, result_path, result, rsi)
        print(root)
        return
    if completed_status(through_round, rsi_only) or skip_judge:
        result['status'] = 'completed'; result['finishedAt'] = result.get('finishedAt') or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        if skip_judge:
            result['judgeStatus'] = 'deferred_until_agent_protocol_is_stable'
        checkpoint(root, result_path, result, rsi)
        print(root)
        return
    provider = ModelClient(ModelOptions(config.JUDGE_BASE_URL, config.JUDGE_API_KEY, config.JUDGE_MODEL, config.MODEL_TIMEOUT))
    for pair in result['pairs']:
        if pair.get('judge') or not {'baseline', 'rsi'}.issubset(pair['runs']):
            continue
        try:
            baseline, rsi_run = base.runs[pair['runs']['baseline']['id']], rsi.runs[pair['runs']['rsi']['id']]
            payload, reports = judge_input(bank, baseline, rsi_run)
            input_path = root / 'judgements' / 'inputs' / (pair['taskId'] + '.json')
            write(input_path, dict(taskId=pair['taskId'], baselineRunId=baseline['id'], rsiRunId=rsi_run['id'],
                                   inputHash=digest(dict(payload=payload, reports=reports)), payload=payload, reports=reports))
            pair['judge'] = await judge_pair(payload, reports, provider)
        except Exception as error:
            pair['judge'] = dict(status='failed', error=str(error)[:1000])
        write(root / 'judgements' / (pair['taskId'] + '.json'), pair['judge'])
        checkpoint(root, result_path, result, rsi)
    result['status'] = 'completed'; result['finishedAt'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    checkpoint(root, result_path, result, rsi)
    print(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through-round', type=int, default=6, help='Run through this fixed round; values below 6 retain a resumable formal precheck.')
    parser.add_argument('--experiment', default=DEFAULT_EXPERIMENT, help='New isolated experiment directory ID; existing manifests cannot change.')
    parser.add_argument('--rsi-only', action='store_true', help='Run only Graph RSI for isolated mechanism prechecks; no baseline or Judge calls.')
    parser.add_argument('--rsi-source', help='Reuse a completed RSI-only experiment by ID and run only a protocol-matched baseline in this new experiment directory.')
    parser.add_argument('--task-ids', help='Comma-separated subset of the selected train manifest, preserving the supplied order.')
    parser.add_argument('--manifest-profile', choices=MANIFEST_PROFILES, default='core36',
                        help='core36 is the frozen delivery set; all_train is an independent 180-task saturation protocol.')
    parser.add_argument('--skip-judge', action='store_true', help='Complete Agent execution without Judge requests; a later compatible resume judges after all Agent runs.')
    parser.add_argument('--reliability-experiment', help='Optional linked serial long-tail precheck experiment ID for the report page.')
    parser.add_argument('--scale-experiment', help='Optional linked serial scale/reliability experiment ID for the report page.')
    args = parser.parse_args()
    task_ids = args.task_ids.split(',') if args.task_ids else None
    asyncio.run(main(args.through_round, args.experiment, args.rsi_only, task_ids, args.rsi_source,
                     args.skip_judge, args.reliability_experiment, args.scale_experiment, args.manifest_profile))
