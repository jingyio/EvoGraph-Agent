"""Read-only task-scoped tools over frozen public records; gold is never a tool output."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from .config import ROOT
from .tools import Tool, ToolContext, object_schema
from .graph_store import write_private
from .task_tool_docs import DESCRIPTIONS


SECTIONS = {
    'finance': {
        'get_order': ['status', 'purchased_at', 'delivered_at', 'estimated_at'],
        'get_order_items': ['items'], 'get_order_payments': ['payments'],
        'get_customer': ['customer_id', 'customer_unique_id', 'customer_state'], 'get_order_reviews': ['reviews'],
    },
    'support': {
        'get_complaint': ['product', 'sub_product', 'issue', 'sub_issue', 'company', 'submitted_via'],
        'get_response': ['company_response', 'company_public_response', 'timely'],
        'get_dates': ['date_received', 'date_sent_to_company'], 'get_narrative': ['narrative'],
    },
    'tickets': {
        'get_issue': ['title', 'state', 'created_at', 'updated_at'], 'get_labels': ['labels'],
        'get_assignment': ['assignee_count'], 'get_milestone': ['milestone'], 'get_activity': ['comments', 'updated_at'],
        'get_resolution': ['state', 'created_at', 'closed_at'], 'get_body': ['body', 'url'],
    },
}
PARAMS = dict(finance='orderId', support='complaintId', tickets='issueId')
LISTS = dict(finance='list_orders', support='list_complaints', tickets='list_issues')


def metric_schema(value):
    if isinstance(value, dict):
        return {'type': 'object', 'additionalProperties': {'type': 'integer'}}
    return {'type': 'integer'}


def compare(task, expected, submitted, observed):
    issues = []
    supplied = submitted.get('metrics', {})
    # Python equates True and 1; explicit type checks prevent scoring booleans as counts.
    def equal(a, b):
        if type(a) is not type(b):
            return False
        if isinstance(b, dict):
            return set(a) == set(b) and all(equal(a[k], b[k]) for k in b)
        return a == b
    for key, value in expected['metrics'].items():
        if key not in supplied or not equal(supplied[key], value):
            issues.append('metric:' + key)
    if set(supplied) != set(expected['metrics']):
        issues.append('metric_keys')
    selected = submitted.get('selectedIds', [])
    if len(selected) != len(set(selected)) or not set(selected).issubset(task['recordIds']):
        issues.append('invalid_selection')
    actual_selection = selected if expected['ordered'] else sorted(selected)
    if actual_selection != expected['selectedIds']:
        issues.append('selectedIds')
    evidence = submitted.get('evidenceIds', [])
    required = {task['scenario'] + ':' + key for key in task['recordIds']}
    if set(evidence) != required or not set(evidence).issubset(observed):
        issues.append('evidence_coverage')
    return dict(status='passed' if not issues else 'failed', issues=issues, scope='structured-facts-and-evidence', prose='not_evaluated')


class TaskBank:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.sessions = {}
        self.tasks, self.gold, self.manifest = {}, {}, None

    def load(self):
        path = self.root / 'benchmarks/tasks.jsonl'
        if path.exists():
            self.tasks = {t['id']: t for t in map(json.loads, path.read_text().splitlines())}
            self.manifest = json.loads((self.root / 'benchmarks/manifest.json').read_text())
            gold_path = self.root / 'artifacts/taskbank/gold.json'
            if gold_path.exists():
                self.gold = json.loads(gold_path.read_text())
            # These three higher-complexity tasks are an isolated recording
            # set. They are not part of the frozen 300-task corpus or V4.
            from .showcase_tasks import load as load_showcase_tasks
            showcase_tasks, showcase_gold = load_showcase_tasks(self.root)
            self.tasks.update(showcase_tasks)
            self.gold.update(showcase_gold)
            if showcase_tasks and self.manifest is not None:
                self.manifest = dict(self.manifest, showcaseTaskSets={
                    'higherComplexityV1': {
                        'taskCount': len(showcase_tasks),
                        'split': 'showcase',
                        'purpose': 'recording_demo_only_not_formal_evaluation',
                    }
                })

    def task(self, key):
        if key not in self.tasks:
            raise ValueError('Unknown task ID, or task corpus has not been built')
        return self.tasks[key]

    def record(self, task, key):
        if key not in task['recordIds']:
            raise ValueError('Record is outside this task scope')
        path = self.root / 'artifacts/taskbank/records.sqlite3'
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            row = db.execute('SELECT payload FROM records WHERE scenario=? AND id=?', (task['scenario'], key)).fetchone()
        if row is None:
            raise ValueError('Frozen source record is missing')
        return json.loads(row[0])

    def tools(self, task_id):
        task = self.task(task_id)
        if task_id not in self.gold or not (self.root / 'artifacts/taskbank/records.sqlite3').exists():
            raise ValueError('Task records are not installed; run npm run taskbank:build with the frozen source cache')
        scenario, parameter = task['scenario'], PARAMS[task['scenario']]
        tools = []
        def add(name, description, schema, handler, effect='read', outputs=None):
            tools.append(Tool(scenario + '_' + name, description, effect, schema, handler, outputs=outputs))
        def read(key, fields, ctx):
            row = self.record(task, key)
            ref = scenario + ':' + key
            ctx.evidence.add(ref)
            return dict(id=key, _evidenceRef=ref, **{f: row.get(f) for f in fields})
        def listing(args, ctx):
            start = (args['page'] - 1) * args['pageSize']
            keys = task['recordIds'][start:start + args['pageSize']]
            field = ['status'] if scenario == 'finance' else ['product'] if scenario == 'support' else ['state', 'title']
            return dict(records=[read(key, field, ctx) for key in keys], page=args['page'], mayHaveMore=start + len(keys) < len(task['recordIds']))
        label = dict(finance='订单', support='投诉', tickets='技术工单')[scenario]
        list_outputs = dict(finance=['id', 'status'], support=['id', 'product'], tickets=['id', 'state', 'title'])[scenario]
        add(LISTS[scenario], f'分页列出本任务{label}记录及 ID；返回 records 数组（id、概要字段）、page、mayHaveMore。', object_schema({'page': {'type': 'integer', 'minimum': 1}, 'pageSize': {'type': 'integer', 'minimum': 1, 'maximum': 50}}), listing, outputs=list_outputs)
        for name, fields in SECTIONS[scenario].items():
            add(name, DESCRIPTIONS[scenario + '_' + name],
                object_schema({parameter: {'type': 'string', 'minLength': 1}}), lambda args, ctx, fields=fields: read(args[parameter], fields, ctx), outputs=['id', *fields])
        add('get_task_scope', '读取当前任务范围、参考时间及输出字段名称；不返回参考答案。', object_schema(),
            lambda args, ctx: {k: task[k] for k in ['id', 'asOf', 'recordCount', 'acceptance']}, outputs=['id', 'asOf', 'recordCount', 'acceptance'])
        add('sum_values', '整数求和，不做币种换算。输入值需来自已读取记录。', object_schema({'values': {'type': 'array', 'maxItems': 2000, 'items': {'type': 'integer'}}}), lambda args, ctx: {'sum': sum(args['values'])}, 'compute', outputs=['sum'])
        def count(args, ctx):
            from collections import Counter
            return dict(counts=dict(Counter(args['values'])))
        add('count_values', '按精确字符串分组计数；缺失字段使用 (missing)。', object_schema({'values': {'type': 'array', 'maxItems': 2000, 'items': {'type': 'string'}}}), count, 'compute', outputs=['counts'])
        def rank(args, ctx):
            if any(r['id'] not in task['recordIds'] for r in args['records']):
                raise ValueError('Record is outside this task scope')
            direction = -1 if args['direction'] == 'desc' else 1
            return {'ids': [r['id'] for r in sorted(args['records'], key=lambda r: (direction * r['value'], r['id']))[:args['limit']]]}
        add('rank_values', '按整数值排序，并列按记录 ID 字符串升序。', object_schema({'records': {'type': 'array', 'maxItems': 100, 'items': object_schema({'id': {'type': 'string'}, 'value': {'type': 'integer'}})}, 'direction': {'type': 'string', 'enum': ['asc', 'desc']}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}}), rank, 'compute', outputs=['ids'])
        def rank_time(args, ctx):
            if any(r['id'] not in task['recordIds'] for r in args['records']):
                raise ValueError('Record is outside this task scope')

            def timestamp(value):
                return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()

            direction = -1 if args['direction'] == 'desc' else 1
            return {
                'ids': [
                    row['id']
                    for row in sorted(
                        args['records'],
                        key=lambda row: (direction * timestamp(row['timestamp']), row['id']),
                    )[:args['limit']]
                ]
            }
        add('rank_time_values', '按 ISO-8601 时间排序，并列按记录 ID 字符串升序。时间比较不应由模型手工判断。', object_schema({'records': {'type': 'array', 'maxItems': 100, 'items': object_schema({'id': {'type': 'string'}, 'timestamp': {'type': 'string', 'minLength': 1}})}, 'direction': {'type': 'string', 'enum': ['asc', 'desc']}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100}}), rank_time, 'compute', outputs=['ids'])
        def elapsed(args, ctx):
            start = datetime.fromisoformat(args['start'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(args['end'].replace('Z', '+00:00'))
            return {'seconds': int((end - start).total_seconds())}
        add('elapsed_seconds', '计算两个 ISO-8601 时间戳的 end - start 秒数。时间差计算不应由模型手工心算。', object_schema({'start': {'type': 'string', 'minLength': 1}, 'end': {'type': 'string', 'minLength': 1}}), elapsed, 'compute', outputs=['seconds'])
        def publish(args, ctx):
            evaluation = compare(task, self.gold[task_id], args, ctx.evidence)
            ctx.run['submission'] = deepcopy(args)
            ctx.run['evaluation'] = evaluation
            return {'saved': True, 'evaluation': evaluation}
        add('publish_report', '保存本地分析结果并检查结构化事实。不是企业系统写入，不发送消息；不返回标准答案。',
            object_schema({'metrics': object_schema({k: metric_schema(v) for k, v in self.gold[task_id]['metrics'].items()}),
                           'selectedIds': {'type': 'array', 'uniqueItems': True, 'items': {'type': 'string'}},
                           'evidenceIds': {'type': 'array', 'uniqueItems': True, 'items': {'type': 'string'}},
                           'summary': {'type': 'string', 'minLength': 1, 'maxLength': 6000}}), publish, 'artifact')
        return tools

    def start(self, key):
        self.task(key)
        session = dict(id=str(uuid4()), taskId=key, events=[], toolCalls=0, mode='manual-tool-session')
        self.sessions[session['id']] = (session, ToolContext(session))
        return session

    async def call(self, session_id, name, args):
        if session_id not in self.sessions:
            raise ValueError('Unknown tool session; create a new session after server restart')
        session, context = self.sessions[session_id]
        if session['toolCalls'] >= 80:
            raise ValueError('Task session tool budget exhausted')
        tool = next((t for t in self.tools(session['taskId']) if t.name == name), None)
        if tool is None:
            raise ValueError('Tool is not available in this scenario')
        session['toolCalls'] += 1
        try:
            output = dict(ok=True, result=await tool.execute(args, context))
        except (ValueError, KeyError, TypeError) as error:
            output = dict(ok=False, error=str(error)[:1000])
        session['events'].append(dict(tool=name, arguments=deepcopy(args), observation=deepcopy(output)))
        write_private(self.root / 'artifacts/taskbank-sessions' / (session_id + '.json'), session)
        return dict(output, toolCalls=session['toolCalls'], evaluation=session.get('evaluation'))
