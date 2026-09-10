#!/usr/bin/env python3
"""Run a bounded real-data RSI serial scale showcase without changing taskbank files."""
import asyncio
import argparse
from copy import deepcopy
from html import escape
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import config
from backend.autotool import digest
from backend.task_definitions import answer
from backend.task_runner import TaskRunner, TaskRunRequest
from backend.taskbank import TaskBank

EXPERIMENT = 'efficiency-scale-reliability-v1'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def real_scale_tasks(bank):
    """Use 10+30+60 disjoint public train records, selected before any run."""
    train = [task for task in bank.tasks.values() if task['scenario'] == 'finance' and task['split'] == 'train']
    ids = sorted({record for task in train for record in task['recordIds']})
    with sqlite3.connect((bank.root / 'artifacts/taskbank/records.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
        payloads = db.execute("SELECT id, payload FROM records WHERE scenario='finance'").fetchall()
    rows = {key: json.loads(payload) for key, payload in payloads if key in set(ids)}
    positive = [key for key in ids if rows[key]['status'] == 'canceled' and rows[key]['payments']]
    other = [key for key in ids if key not in positive]
    sizes, cursor, output = [10, 30, 60], 0, []
    for index, size in enumerate(sizes):
        # Preserve natural positives so all nonempty scale points exercise the
        # same business rule; no values, IDs, or answers reach the model.
        take = min(index + 1, len(positive) - cursor)
        chosen = positive[cursor:cursor + take]
        cursor += take
        chosen += other[:size - len(chosen)]
        del other[:size - len(chosen)]
        task_id = f'finance-cancelled_payments-scale-{size}'
        task = dict(id=task_id, scenario='finance', family='cancelled_payments', split='train',
                    asOf=train[0]['asOf'], recordIds=chosen, recordCount=size,
                    sourceUrl=train[0]['sourceUrl'], title='取消订单支付核查（规模）',
                    task=f'任务 {task_id}：只分析本任务工具可见的 {size} 条记录。找出状态为 canceled 且存在支付记录的订单，统计数量和支付金额；不推断已退款或应退款。以 {train[0]["asOf"]} 为参考时刻。返回 metrics 字段 order_count, paid_cents，selectedIds 按要求列出（无需筛选的任务为空数组），并给出逐条证据引用和简短结论。不得补造缺失数据、修改原始记录或发送消息。',
                    acceptance=dict(metricKeys=['order_count', 'paid_cents'], selectedIdsOrderMatters=False, evidence='引用本任务实际观察过的记录', prose='仅保存，不自动评估全部自然语言质量'),
                    suggestedBudget=dict(modelRequests=24, toolCalls=120))
        output.append((task, answer('finance', 'cancelled_payments', [rows[key] for key in chosen], task['asOf'])))
    return output


def compact(run):
    return {key: deepcopy(run.get(key)) for key in ['id', 'taskId', 'strategy', 'status', 'metrics', 'evaluation', 'evolution', 'plan', 'graph', 'toolTrace', 'submission']}


async def execute(runner, task_id, strategy):
    run = await runner.start(TaskRunRequest(taskId=task_id, strategy=strategy))
    await runner.tasks[run['id']]
    return compact(run)


def passed(run):
    return run['status'] == 'completed' and run['evaluation']['status'] == 'passed'


def total(run):
    return run['metrics']['inputTokens'] + run['metrics']['outputTokens']


def report(data):
    scale_rows = []
    for row in data['scale']:
        b, r = row['baseline'], row['rsi']
        saving = 1 - total(r) / total(b) if total(b) else 0
        scale_rows.append(f'<tr><td>{row["recordCount"]}</td><td>{"pass" if passed(b) else b["status"]} / {total(b):,} / {b["metrics"]["modelRequests"]} / {b["metrics"]["toolCalls"]}</td><td>{"pass" if passed(r) else r["status"]} / {total(r):,} / {r["metrics"]["modelRequests"]} / {r["metrics"]["toolCalls"]}</td><td>{saving:.1%}</td><td>{r["metrics"].get("filteredOutDetailReads", 0)} / {r["metrics"].get("emptyDetailBranches", 0)}</td></tr>')
    conc_rows = []
    for row in data.get('concurrency') or []:
        conc_rows.append(f'<tr><td>{row["level"]}</td><td>{row["elapsedMs"] / 1000:.2f}s</td><td>{row["scheduler"]["peaks"]}</td><td>{sum(passed(x) for x in row["runs"])} / {len(row["runs"])}</td><td>{sum(total(x) for x in row["runs"]):,}</td></tr>')
    concurrency_section = '' if not conc_rows else f'''<h2>历史并发补充工件</h2><p>此处仅在显式运行时生成；不计入本轮串行 token 或延迟结论。</p><table><tr><th>任务/模型并发</th><th>总完成时间</th><th>实际峰值</th><th>通过</th><th>token</th></tr>{''.join(conc_rows)}</table>'''
    return f'''<!doctype html><meta charset="utf-8"><title>RSI 效率、规模与可靠性</title><style>body{{font:14px/1.6 system-ui;margin:28px;background:#f5f7f8;color:#17232b}}main{{max-width:1120px;margin:auto;background:#fff;padding:30px;border:1px solid #d6dfe3}}table{{width:100%;border-collapse:collapse;margin:14px 0}}td,th{{padding:9px;text-align:left;border-bottom:1px solid #d6dfe3}}th{{background:#eff4f5}}small{{color:#596d76}}code{{background:#edf2f4;padding:2px 4px}}</style><main><small>真实公开 Olist train 记录；Agent 与 Judge 成本未混合。本页数字来自保存工件，不是模拟。</small><h1>RSI 串行效率、规模与可靠性</h1><h2>取消支付 Motif：优化前后</h2><p>旧 RSI 6 条：143,418 token / 88 工具；优化后 6 条：51,647 token / 19 工具，6/6 结构化通过。优化是通用编译器能力/去重修复，不是运行时自主 G1/G2。</p><h2>记录规模：Baseline 与 RSI</h2><p>10、30、60 条均为互不重复的冻结公开 train 记录。每次 Agent 运行、模型请求与读取均为串行；RSI 从 10 条冷启动后复用同一参数化图，不保存记录 ID 或上次规模结果。</p><table><tr><th>记录</th><th>Baseline：结果 / token / LLM / 工具</th><th>RSI：结果 / token / LLM / 工具</th><th>RSI token 降幅</th><th>RSI 筛掉详情 / 空分支</th></tr>{''.join(scale_rows)}</table>{concurrency_section}<h2>可靠性</h2><p>规模三点保留失败、工具错误、报告重提和用量。SQLite 读取很快，不能把本页结果推广为远程 API 吞吐。</p><details><summary>完整结果 JSON</summary><pre>{escape(json.dumps(data, ensure_ascii=False, indent=2))}</pre></details></main>'''


async def main(experiment=EXPERIMENT, include_concurrency=False):
    bank = TaskBank(); bank.load()
    tasks = real_scale_tasks(bank)
    for task, gold in tasks:
        bank.tasks[task['id']] = task; bank.gold[task['id']] = gold
    root = ROOT / 'artifacts' / 'efficiency' / experiment
    root.mkdir(parents=True, exist_ok=True)
    baseline = TaskRunner(bank, run_limit=1, model_limit=1, read_limit=1, run_directory=root / 'scale-baseline', evolution_path=root / 'baseline-experience.json', learning_enabled=False)
    rsi = TaskRunner(bank, run_limit=1, model_limit=1, read_limit=1, run_directory=root / 'scale-rsi', evolution_path=root / 'rsi-experience.json', learning_enabled=True)
    rows = []
    for task, _ in tasks:
        rows.append(dict(taskId=task['id'], recordCount=task['recordCount'], baseline=await execute(baseline, task['id'], 'plan_react'), rsi=await execute(rsi, task['id'], 'graph_rsi')))
    concurrency = []
    if include_concurrency:
        # Retained only to reproduce the historical supplemental artifact. It
        # is deliberately opt-in and is not used by the final serial protocol.
        fixed = [row['taskId'] for row in rows] + ['finance-cancelled_payments-04']
        bank.tasks['finance-cancelled_payments-04'] = bank.tasks.get('finance-cancelled_payments-04')
        for level in [1, 2, 4]:
            runner = TaskRunner(bank, run_limit=level, model_limit=level, read_limit=1, run_directory=root / f'concurrency-{level}', evolution_path=root / 'rsi-experience.json', learning_enabled=False)
            runner.restore()
            started = time.perf_counter()
            pending = [await runner.start(TaskRunRequest(taskId=task_id, strategy='graph_rsi')) for task_id in fixed]
            await asyncio.gather(*(runner.tasks[run['id']] for run in pending))
            concurrency.append(dict(level=level, elapsedMs=round((time.perf_counter() - started) * 1000, 3), scheduler=runner.status(), runs=[compact(run) for run in pending]))
    data = dict(id=experiment, createdAt=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), protocol=dict(model=config.MODEL, scale='disjoint public train records; 10 cold then 30/60 Fast reuse', execution='run/model/read=1; serial Agent execution', concurrency='not_run' if not include_concurrency else 'historical supplemental; task/model=1,2,4; reads=1; learning=false'), scale=rows, concurrency=concurrency)
    write(root / 'result.json', data)
    (root / 'index.html').write_text(report(data), encoding='utf-8')
    print(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', default=EXPERIMENT, help='New isolated efficiency artifact ID.')
    parser.add_argument('--include-concurrency', action='store_true', help='Reproduce the historical concurrency supplement; excluded from serial conclusions.')
    args = parser.parse_args()
    asyncio.run(main(args.experiment, args.include_concurrency))
