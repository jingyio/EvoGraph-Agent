#!/usr/bin/env python3
"""Run the fixed, isolated 36-task online RSI experiment exactly once per task."""
import asyncio
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


EXPERIMENT = 'online-e2e-train-v1'
TYPES = [
    ('finance', 'cancelled_payments'), ('finance', 'installments'),
    ('support', 'channels'), ('support', 'timeliness'),
    ('tickets', 'unassigned'), ('tickets', 'labels'),
]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def task_manifest(bank):
    selected = []
    for round_index in range(6):
        for scenario, family in TYPES:
            task_id = f'{scenario}-{family}-{round_index + 1:02d}'
            task = bank.task(task_id)
            if task['split'] != 'train':
                raise ValueError('not_train:' + task_id)
            selected.append(dict(round=round_index + 1, taskId=task_id, scenario=scenario, family=family,
                                 recordCount=task['recordCount'], recordIds=task['recordIds'], asOf=task.get('asOf'),
                                 taskDigest=digest(dict(task=task['task'], recordIds=task['recordIds'], asOf=task.get('asOf')))))
    if len({row['taskId'] for row in selected}) != 36:
        raise ValueError('task_manifest_not_unique')
    return selected


SCHEMA_VERSION = 2


def compact(run):
    return deepcopy({key: run.get(key) for key in ['id', 'taskId', 'strategy', 'status', 'phase', 'models', 'metrics', 'phaseMetrics', 'evaluation', 'evolution', 'compositionPlan', 'graphSelection', 'toolInertia', 'toolInertiaMaintenance', 'fallback', 'error', 'createdAt', 'startedAt', 'finishedAt']})


def experience_summary(runner):
    evolution = runner.evolution
    return dict(versions=len(evolution.versions), workflows=len(evolution.workflows), tinyEdges=len(evolution.tiny_edges),
                toolPaths=len(evolution.tool_inertia.get('toolPaths', [])), parameterEdges=len(evolution.tool_inertia.get('parameterEdges', [])),
                graphIds=[row['id'] for row in evolution.versions])


def aggregate(values, key):
    return sum((value or {}).get(key) or 0 for value in values)


def diagnostics(runs):
    evolution = [run.get('evolution') or {} for run in runs]
    metrics = [run.get('metrics') or {} for run in runs]
    inertia = [run.get('toolInertiaMaintenance') or {} for run in runs]
    composition = [run.get('compositionPlan') or {} for run in runs]
    paths = {}
    for item in evolution:
        paths[item.get('planningPath', 'not_applicable')] = paths.get(item.get('planningPath', 'not_applicable'), 0) + 1
    return dict(
        planningPaths=paths,
        graphReuse=sum(bool(item.get('usedVersionId')) for item in evolution),
        compositionRuns=sum(item.get('execution') == 'composition' for item in evolution),
        graphFallbacks=sum(bool(run.get('fallback')) for run in runs),
        graphLookupMs=round(aggregate(evolution, 'lookupMs'), 3),
        compositionLocalMs=round(sum(item.get('compositionLocalMs', composition[index].get('localMs', 0)) or 0 for index, item in enumerate(evolution)), 3),
        evolutionMaintenanceMs=round(aggregate(evolution, 'maintenanceMs'), 3),
        inertiaAttempts=aggregate(metrics, 'inertiaAttempts'), inertiaAccepted=aggregate(metrics, 'inertiaAccepted'),
        inertiaCalls=aggregate(metrics, 'inertiaCalls'), inertiaErrors=aggregate(metrics, 'inertiaErrors'),
        inertiaRejected=aggregate(metrics, 'inertiaRejected'), inertiaQueryMs=round(aggregate(metrics, 'inertiaQueryMs'), 3),
        inertiaUpdates=aggregate(inertia, 'updatedPaths'), parameterEdgeUpdates=aggregate(inertia, 'updatedParameterEdges'),
        inertiaUpdateMs=round(aggregate(inertia, 'updateMs'), 3), inertiaPersistMs=round(aggregate(inertia, 'persistMs'), 3))


def success(run):
    return run.get('status') == 'completed' and run.get('evaluation', {}).get('status') == 'passed'


def summary(rows):
    result = {}
    for arm in ['baseline', 'rsi']:
        runs = [row['runs'][arm] for row in rows if arm in row.get('runs', {})]
        metrics = [row['metrics'] for row in runs]
        passed = sum(success(row) for row in runs)
        total_tokens = sum((row.get('inputTokens') or 0) + (row.get('outputTokens') or 0) for row in metrics)
        result[arm] = dict(attempts=len(runs), passed=passed, successRate=passed / len(runs) if runs else None,
                           inputTokens=sum(row.get('inputTokens') or 0 for row in metrics), outputTokens=sum(row.get('outputTokens') or 0 for row in metrics),
                           totalTokens=total_tokens, modelRequests=sum(row.get('modelRequests') or 0 for row in metrics),
                           toolCalls=sum(row.get('toolCalls') or 0 for row in metrics), toolErrors=sum(row.get('toolErrors') or 0 for row in metrics),
                           durationMs=sum(row.get('durationMs') or 0 for row in metrics), tokensPerSuccess=total_tokens / passed if passed else None,
                           usageComplete=all(row.get('usageComplete') for row in metrics), failures=[dict(taskId=row.get('taskId'), status=row.get('status'), error=row.get('error'), issues=row.get('evaluation', {}).get('issues', [])) for row in runs if not success(row)],
                           diagnostics=diagnostics(runs))
    a, b = result['baseline'], result['rsi']
    return dict(arms=result, allOutcomeTokenDelta=b['totalTokens'] - a['totalTokens'],
                allOutcomeLatencyDeltaMs=b['durationMs'] - a['durationMs'],
                qualityRegressions=sum(success(row['runs'].get('baseline', {})) and not success(row['runs'].get('rsi', {})) for row in rows),
                qualityImprovements=sum(not success(row['runs'].get('baseline', {})) and success(row['runs'].get('rsi', {})) for row in rows))


def round_summaries(rows):
    return [dict(round=index, summary=summary([row for row in rows if row.get('round') == index])) for index in range(1, 7)]


def evolution_chain(rows):
    chains = []
    for row in rows:
        run = row.get('runs', {}).get('rsi') or {}
        before, after = row.get('experienceBefore') or {}, row.get('experienceAfter') or {}
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


def result_report(result):
    data = result.get('summary') or {}
    arms = data.get('arms') or {}
    def arm(name):
        row = arms.get(name, {})
        return f"<tr><th>{escape(name)}</th><td>{row.get('passed', 0)} / {row.get('attempts', 0)}</td><td>{row.get('totalTokens', 0):,}</td><td>{row.get('modelRequests', 0)}</td><td>{row.get('toolCalls', 0)}</td><td>{row.get('durationMs', 0) / 1000:.1f}s</td></tr>"
    rounds = ''.join(f"<tr><td>{row['round']}</td><td>{row['summary']['arms']['baseline']['totalTokens']:,}</td><td>{row['summary']['arms']['rsi']['totalTokens']:,}</td><td>{row['summary']['arms']['baseline']['passed']}</td><td>{row['summary']['arms']['rsi']['passed']}</td></tr>" for row in result.get('rounds', []))
    chains = ''.join(f"<li><b>{escape(item['taskId'])}</b>: used={escape(str(item['usedGraphId'] or 'none'))}, created={escape(', '.join(item['createdGraphIds']) or 'none')}</li>" for item in result.get('evolutionChain', [])) or '<li>尚未观察到经验变化。</li>'
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RSI 在线对照实验</title><style>body{{font:14px/1.65 system-ui,sans-serif;margin:0;background:#f5f7f8;color:#1d2a33}}main{{max-width:1100px;margin:28px auto;background:white;padding:32px;border:1px solid #d8e0e4}}table{{border-collapse:collapse;width:100%;margin:12px 0}}th,td{{border-bottom:1px solid #dbe3e6;text-align:left;padding:9px}}pre{{background:#f4f7f8;padding:14px;overflow:auto}}small{{color:#647781}}</style><main><small>固定 manifest、隔离经验、串行在线学习；Agent 成本不含 Judge 成本。</small><h1>RSI 端到端在线对照实验</h1><p>状态：{escape(result.get('status', 'unknown'))}；实验：{escape(result.get('id', ''))}</p><h2>累计执行</h2><table><tr><th>执行流</th><th>结构化通过</th><th>token</th><th>LLM</th><th>工具</th><th>端到端</th></tr>{arm('baseline')}{arm('rsi')}</table><p>RSI - 基线：token {data.get('allOutcomeTokenDelta', 0):,}；延迟 {data.get('allOutcomeLatencyDeltaMs', 0) / 1000:.1f}s。负值才表示 RSI 较低。</p><h2>按轮</h2><table><tr><th>轮</th><th>基线 token</th><th>RSI token</th><th>基线通过</th><th>RSI通过</th></tr>{rounds}</table><h2>经验来源到后续使用</h2><ul>{chains}</ul><h2>审计入口</h2><p>原始协议、运行索引、经验快照与双顺序 Judge 记录位于本目录的 JSON 文件。失败与中断不被筛掉。</p><details><summary>完整摘要 JSON</summary><pre>{escape(json.dumps(data, ensure_ascii=False, indent=2))}</pre></details></main>'''


def write_report(root, result):
    path = root / 'index.html'
    temporary = path.with_suffix('.html.tmp')
    temporary.write_text(result_report(result), encoding='utf-8')
    temporary.replace(path)


def checkpoint(root, result_path, result):
    result['pairs'] = sorted(result['pairs'], key=lambda row: row['index'])
    result['summary'] = summary(result['pairs'])
    result['rounds'] = round_summaries(result['pairs'])
    result['evolutionChain'] = evolution_chain(result['pairs'])
    write(result_path, result)
    write_report(root, result)


async def main():
    bank = TaskBank(); bank.load()
    if not bank.gold:
        raise RuntimeError('taskbank_records_missing')
    root = ROOT / 'artifacts' / 'online-e2e' / EXPERIMENT
    result_path, manifest_path = root / 'result.json', root / 'manifest.json'
    manifest = task_manifest(bank)
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise RuntimeError('manifest_changed')
    write(manifest_path, manifest)
    base = TaskRunner(bank, run_limit=1, model_limit=1, read_limit=1, run_directory=root / 'baseline' / 'runs', evolution_path=root / 'baseline' / 'experience.json', learning_enabled=False)
    rsi = TaskRunner(bank, run_limit=1, model_limit=1, read_limit=1, run_directory=root / 'rsi' / 'runs', evolution_path=root / 'rsi' / 'experience.json', learning_enabled=True)
    base.restore(); rsi.restore()
    result = json.loads(result_path.read_text()) if result_path.exists() else dict(
        schemaVersion=SCHEMA_VERSION, id=EXPERIMENT, status='running', createdAt=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), manifest=manifest, pairs=[],
        protocol=dict(baseline='plan_react', rsi='motif_first', baselineLearning=False, rsiLearning=True,
                      learning='RSI only, train only, sequential; baseline has no cross-task learning', executor=config.MODEL,
                      planner=config.PLANNER_MODEL, composition=config.COMPOSITION_MODEL, judgeModel=config.JUDGE_MODEL,
                      maxSteps=config.MAX_STEPS, timeout=config.RUN_TIMEOUT, taskHash=digest(manifest),
                      revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                      startFromEmpty=True, shadowRollouts=0, singleAgentConcurrency=True,
                      judge='anonymous dual order after all agent runs; judge cost is separate'))
    if result.get('schemaVersion') != SCHEMA_VERSION or result.get('manifest') != manifest:
        raise RuntimeError('experiment_checkpoint_protocol_changed')
    by_task = {row['taskId']: row for row in result['pairs']}
    for index, item in enumerate(manifest):
        pair = by_task.setdefault(item['taskId'], dict(index=index, **item, launchOrder=['baseline', 'rsi'] if index % 2 == 0 else ['rsi', 'baseline'], runs={}, experienceBefore=None, experienceAfter=None))
        if pair['experienceBefore'] is None:
            pair['experienceBefore'] = experience_summary(rsi)
            result['pairs'] = list(by_task.values())
            checkpoint(root, result_path, result)
        for arm in pair['launchOrder']:
            existing = pair['runs'].get(arm)
            if existing:
                run = (base if arm == 'baseline' else rsi).runs.get(existing['id'])
                if run:
                    pair['runs'][arm] = compact(run)
                continue
            runner, strategy = (base, 'plan_react') if arm == 'baseline' else (rsi, 'motif_first')
            run = await runner.start(TaskRunRequest(taskId=item['taskId'], strategy=strategy))
            # Persist identity before awaiting: a process interruption never silently reruns this task.
            pair['runs'][arm] = compact(run)
            pair['experienceAfter'] = experience_summary(rsi)
            result['pairs'] = list(by_task.values())
            checkpoint(root, result_path, result)
            await runner.tasks[run['id']]
            pair['runs'][arm] = compact(run)
            pair['experienceAfter'] = experience_summary(rsi)
            result['pairs'] = list(by_task.values())
            checkpoint(root, result_path, result)
        pair['experienceAfter'] = experience_summary(rsi)
        result['pairs'] = list(by_task.values())
        checkpoint(root, result_path, result)
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
        checkpoint(root, result_path, result)
    result['status'] = 'completed'; result['finishedAt'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    checkpoint(root, result_path, result)
    print(root)


if __name__ == '__main__':
    asyncio.run(main())
