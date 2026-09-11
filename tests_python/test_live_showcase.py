import asyncio
import json

from backend.live_showcase import LiveShowcase
from backend.tools import Tool, object_schema


def response(name=None, args=None):
    message = {'role': 'assistant', 'content': 'done'}
    if name:
        message['tool_calls'] = [{'id': name, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args or {})}}]
    return {'message': message, 'usage': {'input': 4, 'output': 1}, 'finishReason': 'stop'}


class Model:
    def __init__(self, role):
        self.model = role
        self.role = role
    async def complete(self, messages, tools):
        if self.role == 'planner':
            return response('submit_plan', {'steps': [{'id': 'list', 'intent': 'list records', 'dependencies': []}]})
        if tools and tools[0].name == 'submit_graph':
            return response('submit_graph', {'nodes': [{'id': 'list', 'tool': 'finance_list_orders'}]})
        if not any(call.get('function', {}).get('name') == 'finance_list_orders' for message in messages for call in message.get('tool_calls') or []):
            return response('finance_list_orders', {'page': 1, 'pageSize': 50})
        if not any(message.get('tool_call_id') == 'finance_publish_report' for message in messages):
            return response('finance_publish_report', dict(metrics={'count': 1}, selectedIds=[], evidenceIds=['finance:one'], summary='done'))
        return response()


class Bank:
    def __init__(self, root):
        self.root = root
        self.manifest = {'version': 'test'}
        self.tasks = {f'finance-sample-{index:02d}': dict(id=f'finance-sample-{index:02d}', scenario='finance', family='sample', split='train',
                      recordIds=['one'], task='list records and publish report', suggestedBudget={'toolCalls': 10}) for index in [1, 2]}
    def task(self, key):
        return self.tasks[key]
    def tools(self, key):
        def listing(args, ctx):
            ctx.evidence.add('finance:one')
            return {'records': [{'id': 'one', '_evidenceRef': 'finance:one'}], 'page': 1, 'mayHaveMore': False}
        def publish(args, ctx):
            ctx.run['submission'] = args
            ctx.run['evaluation'] = {'status': 'passed', 'issues': []}
            return {'saved': True, 'evaluation': ctx.run['evaluation']}
        return [Tool('finance_list_orders', 'list records', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), listing, outputs=['id']),
                Tool('finance_publish_report', 'publish report', 'artifact', object_schema({
                    'metrics': object_schema({'count': {'type': 'integer'}}),
                    'selectedIds': {'type': 'array', 'items': {'type': 'string'}},
                    'evidenceIds': {'type': 'array', 'items': {'type': 'string'}},
                    'summary': {'type': 'string'},
                }), publish)]


async def test_live_showcase_uses_isolated_two_task_train_sequence(tmp_path):
    bank = Bank(tmp_path)
    live = LiveShowcase(bank, tmp_path, lambda role: Model(role))
    item = await live.start('finance-sample-01', steps=2)
    await live.tasks[item['id']]
    saved = live.get(item['id'])
    assert saved['status'] == 'completed'
    assert saved['taskIds'] == ['finance-sample-01', 'finance-sample-02']
    assert saved['protocol']['runLimit'] == saved['protocol']['modelLimit'] == saved['protocol']['readLimit'] == 1
    assert saved['summary']['baseline']['attempts'] == saved['summary']['rsi']['attempts'] == 2
    assert saved['pairs'][1]['runs']['rsi']['evolution']['usedVersionId']
    assert (tmp_path / 'artifacts/live-showcase' / item['id'] / 'rsi/experience.json').exists()
    await live.shutdown()
