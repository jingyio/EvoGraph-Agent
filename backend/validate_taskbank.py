"""Corpus/tool verification, not model accuracy evaluation."""
import asyncio
from collections import Counter, defaultdict
from copy import deepcopy
import json
from .config import ROOT
from .taskbank import TaskBank, PARAMS, LISTS, SECTIONS, compare
from .task_definitions import FAMILIES, answer
from .tools import ToolContext
from .graph_store import write_private


async def validate():
    bank = TaskBank()
    bank.load()
    corpus = {
        task_id: task
        for task_id, task in bank.tasks.items()
        if task.get('split') in {'train', 'validation', 'test'}
    }
    assert len(corpus) == 300
    splits = defaultdict(lambda: defaultdict(set))
    customers = defaultdict(set)
    tool_calls, summaries = 0, {}
    for task in corpus.values():
        scenario = task['scenario']
        context = ToolContext({'taskId': task['id']})
        tools = {t.name: t for t in bank.tools(task['id'])}
        async def call(name, args):
            nonlocal tool_calls
            tool_calls += 1
            return await tools[scenario + '_' + name].execute(args, context)
        ids, page = [], 1
        while True:
            result = await call(LISTS[scenario], dict(page=page, pageSize=2))
            ids.extend(r['id'] for r in result['records'])
            if not result['mayHaveMore']:
                break
            page += 1
        assert ids == task['recordIds']
        for key in ids:
            for name in SECTIONS[scenario]:
                row = await call(name, {PARAMS[scenario]: key})
                assert row['id'] == key and row['_evidenceRef'] == scenario + ':' + key
        expected = bank.gold[task['id']]
        records = [bank.record(task, key) for key in ids]
        assert answer(scenario, task['family'], records, task['asOf']) == expected
        correct = dict(metrics=expected['metrics'], selectedIds=expected['selectedIds'], evidenceIds=sorted(context.evidence), summary='离线工具契约验证，不是模型生成结果。')
        assert (await call('publish_report', correct))['evaluation']['status'] == 'passed'
        wrong = deepcopy(correct)
        field = next(iter(wrong['metrics']))
        wrong['metrics'][field] = {} if isinstance(wrong['metrics'][field], dict) and wrong['metrics'][field] else {'unexpected': 1} if isinstance(wrong['metrics'][field], dict) else wrong['metrics'][field] + 1
        assert compare(task, expected, wrong, context.evidence)['status'] == 'failed'
        splits[scenario][task['split']].update(ids)
        if scenario == 'finance':
            customers[task['split']].update(r['customer_unique_id'] for r in records)
    for scenario in FAMILIES:
        tasks = [t for t in corpus.values() if t['scenario'] == scenario]
        assert len(tasks) == 100 and set(Counter(t['family'] for t in tasks).values()) == {10}
        assert Counter(t['split'] for t in tasks) == dict(train=60, validation=20, test=20)
        for a, b in [('train', 'validation'), ('train', 'test'), ('validation', 'test')]:
            assert not splits[scenario][a] & splits[scenario][b]
            if scenario == 'finance':
                assert not customers[a] & customers[b]
        assert sum(len(t['recordIds']) for t in tasks) == len(set(i for t in tasks for i in t['recordIds']))
        summaries[scenario] = dict(tasks=100, families=10, tools=len(bank.tools(tasks[0]['id'])), splits=dict(Counter(t['split'] for t in tasks)))
    report = dict(status='passed', tasks=300, scenarios=summaries, toolCalls=tool_calls, modelRequests=0,
                  note='分页、全部字段接口、评分器拒绝错误答案与分组隔离验证；不是 300 次 LLM 任务成功率。')
    write_private(ROOT / 'artifacts/taskbank/validation.json', report)
    catalog = ['# 工具简明目录', '', '仅列用途和主要返回内容；精确参数见 specs/taskbank 或任务 API。', '']
    for scenario in FAMILIES:
        task = next(t for t in corpus.values() if t['scenario'] == scenario)
        catalog.extend(['## ' + scenario, '', '| 工具 | 用途与返回内容 |', '|---|---|'])
        catalog.extend('| `' + t.name + '` | ' + t.description + ' |' for t in bank.tools(task['id']))
        catalog.append('')
    write_private(ROOT / 'docs/reference/tool-catalog.md', '\n'.join(catalog))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(validate())
