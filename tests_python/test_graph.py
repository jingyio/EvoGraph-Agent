import json
import pytest
from backend.tools import Tool, ToolContext, object_schema
from backend.graph import compile_read_graph, run_read_graph, contract_hash, task_key
from backend.runtime import create_run

async def trace(tools, operations):
    run = create_run({'scenario': 'finance', 'mode': 'live', 'source': 'erpnext', 'task': 'protocol-only'}, 'protocol-test')
    for name, args in operations:
        run['events'].append({'seq': len(run['events']) + 1, 'at': '', 'type': 'action', 'title': name, 'detail': {'arguments': json.dumps(args)}})
        result = await next(t for t in tools if t.name == name).execute(args, ToolContext(run))
        run['events'].append({'seq': len(run['events']) + 1, 'at': '', 'type': 'observation', 'title': name, 'detail': {'ok': True, 'result': result}})
    run['status'] = 'completed'
    run['metrics'].update(modelRequests=3, inputTokens=150, outputTokens=40)
    return run

async def test_dynamic_pagination_expands_beyond_original_sample():
    rows = [{'id': 1}, {'id': 2}]
    def listing(args, context):
        page, size = args['page'], args['pageSize']
        return {'records': rows[(page-1)*size:page*size], 'mayHaveMore': page*size < len(rows)}
    tools = [Tool('list_records', 'read', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), listing),
             Tool('get_record', 'read', 'read', object_schema({'recordId': {'type': 'integer'}}), lambda args, c: {'id': args['recordId']})]
    source = await trace(tools, [('list_records', {'page': 1, 'pageSize': 2}), ('get_record', {'recordId': 1})])
    nodes = compile_read_graph(source, tools)
    rows[:] = [{'id': i} for i in range(11, 16)]
    pages, ids = [], []
    async def invoke(name, args, node):
        (pages if name == 'list_records' else ids).append(args.get('page', args.get('recordId')))
        return await next(t for t in tools if t.name == name).execute(args, ToolContext(source))
    await run_read_graph(nodes, tools, invoke)
    assert pages == [1, 2, 3] and ids == [11, 12, 13, 14, 15]

async def test_legacy_graph_executor_reuses_upstream_output_without_calling_detail_tool():
    tools = [Tool('list_issues', 'read', 'read', object_schema({'page': {'type': 'integer'}, 'pageSize': {'type': 'integer'}}), lambda a, c: None),
             Tool('get_issue', 'read', 'read', object_schema({'issueId': {'type': 'string'}}), lambda a, c: None)]
    nodes = [
        {'id': 'list', 'tool': 'list_issues', 'arguments': {'page': {'kind': 'literal', 'value': 1}, 'pageSize': {'kind': 'literal', 'value': 50}}, 'dependencies': [], 'paginate': {'maxPages': 2}, 'sourceEventSeqs': []},
        {'id': 'state', 'tool': 'get_issue', 'arguments': {}, 'dependencies': ['list'], 'reuse': {'nodeId': 'list', 'collectionPath': ['records'], 'fields': ['state']}, 'sourceEventSeqs': []},
    ]
    calls, states = [], []
    async def invoke(name, args, node):
        calls.append((name, args))
        return {'records': [{'id': '1', 'state': 'open'}], 'mayHaveMore': False}
    outputs = await run_read_graph(nodes, tools, invoke, lambda key, state: states.append((key, state)))
    assert calls == [('list_issues', {'page': 1, 'pageSize': 50})]
    assert outputs['state'] == outputs['list']
    assert ('state', 'reused') in states

def test_contract_hash_changes_when_declared_outputs_change():
    schema = object_schema()
    first = Tool('read', 'read', 'read', schema, lambda a, c: None, outputs=['id'])
    second = Tool('read', 'read', 'read', schema, lambda a, c: None, outputs=['id', 'state'])
    assert contract_hash([first]) != contract_hash([second])

def test_task_clock_abstraction_does_not_remove_deadline_constraints():
    assert task_key('以 2026-09-09T01:00:00Z 为本次巡检时刻，读取') == task_key('以 2026-09-10T01:00:00Z 为本次巡检时刻，读取')
    assert task_key('截止 2026-09-09T01:00:00Z') != task_key('截止 2026-09-10T01:00:00Z')
