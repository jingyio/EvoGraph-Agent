import json
from copy import deepcopy

import pytest

from backend.tools import ToolContext
from backend.workspace import WorkspaceManager
from backend import trajectory


async def pipeline(tmp_path, payment=106):
    manager = WorkspaceManager(tmp_path)
    ws = manager.create('finance')
    manager.add_source(ws['id'], 'input.json', json.dumps({
        'orders': [{'order_id': k} for k in ['a', 'b', 'c']],
        'payments': [{'order_id': 'a', 'amount_cents': 60, 'installments': 8},
                     {'order_id': 'a', 'amount_cents': payment-60, 'installments': 1},
                     {'order_id': 'b', 'amount_cents': 105, 'installments': 2},
                     {'order_id': 'outside', 'amount_cents': 999, 'installments': 20}],
        'items': [{'order_id': 'a', 'price_cents': 70, 'freight_cents': 10},
                  {'order_id': 'a', 'price_cents': 20, 'freight_cents': 0},
                  {'order_id': 'b', 'price_cents': 100, 'freight_cents': 0}],
    }).encode())
    public, _ = manager.create_task(ws['id'], '复核差额超过 0.05 BRL 和分期达到 8 期的订单。', split='train')
    task = manager.tasks[public['id']]
    task['computeInterface'] = 'granular-compute-v1'
    tools = {t.name: t for t in manager.tools(task['id'])}
    context = ToolContext({'id': 'current'})
    traces = []
    async def call(tool_name, **args):
        sources = {}
        for key, value in args.items():
            for path, leaf in trajectory.walk(value):
                for index, trace in enumerate(traces):
                    if leaf == trace['result'].get('receiptId'):
                        sources['/'.join(map(str, [key, *path]))] = {'$output': {'traceIndex': index, 'path': ['receiptId']}}
        result = await tools[tool_name].execute(args, context)
        traces.append({'tool': tool_name, 'arguments': args, 'ok': True, 'result': result, 'argumentSources': sources})
        return result
    bindings = task['tableBindings']
    p = await call('workspace_map_fields', tableId=bindings['payments'], keyField='order_id', fields=['amount_cents', 'installments'])
    i = await call('workspace_map_fields', tableId=bindings['items'], keyField='order_id', fields=['price_cents', 'freight_cents'])
    p = await call('workspace_aggregate_keyed', receiptId=p['receiptId'], measures=[{'field': 'amount_cents', 'alias': 'paid', 'operation': 'sum'}, {'field': 'installments', 'alias': 'installments', 'operation': 'max'}])
    i = await call('workspace_aggregate_keyed', receiptId=i['receiptId'], measures=[{'field': 'price_cents', 'alias': 'price', 'operation': 'sum'}, {'field': 'freight_cents', 'alias': 'freight', 'operation': 'sum'}])
    aligned = await call('workspace_align_keyed', anchorTableId=bindings['orders'], keyField='order_id', receiptIds=[p['receiptId'], i['receiptId']])
    derived = await call('workspace_derive_values', receiptId=aligned['receiptId'], totals=[{'name': 'line', 'aliases': ['price', 'freight']}])
    diff = await call('workspace_compare_values', receiptId=derived['receiptId'], name='difference', leftAlias='paid', rightAliases=['line'], operator='abs_gt', threshold=5)
    inst = await call('workspace_compare_values', receiptId=derived['receiptId'], name='installments', leftAlias='installments', operator='gte', threshold=8)
    missing = await call('workspace_select_missing', receiptId=derived['receiptId'], name='missing_payment', aliases=['paid'])
    return manager, task, tools, context, traces, derived, diff, inst, missing


@pytest.mark.asyncio
async def test_current_many_to_one_boundary_overlap_and_missing(tmp_path):
    manager, task, tools, ctx, traces, values, diff, inst, missing = await pipeline(tmp_path)
    assert 'workspace_reconcile_keyed_sums' not in tools
    assert values['totals']['paid'] == 211  # extra child keys excluded
    assert values['perKey']['a']['line'] == 100
    assert values['perKey']['c']['line'] is None
    assert diff['selectedIds'] == ['a']  # b difference equals 5, strict excluded
    assert diff['incompleteKeys'] == ['c']
    assert inst['selectedIds'] == ['a']
    assert missing['selectedIds'] == ['c']
    assert all(ref.startswith('workspace:') for ref in missing['evidenceByKey']['c'])
    assert 'c' not in missing['evidenceByKey']['c']
    with pytest.raises(ValueError, match='当前运行'):
        await tools['workspace_select_missing'].execute({'receiptId': values['receiptId'], 'name': 'x', 'aliases': ['paid']}, ToolContext({'id': 'other'}))
    with pytest.raises(ValueError, match='不能重叠'):
        await tools['workspace_align_keyed'].execute({'anchorTableId': task['tableBindings']['orders'], 'keyField': 'order_id', 'receiptIds': [traces[2]['result']['receiptId'], values['receiptId']]}, ctx)
    proposal = trajectory.induce({'id': 'source', 'toolTrace': traces}, manager.task(task['id']), list(tools.values()))
    names = [node['tool'] for node in proposal['nodes']]
    assert names.count('workspace_compare_values') == 1  # 5 requires conversion, 8 exact slot
    assert 'workspace_derive_values' in names and 'workspace_select_missing' in names
    assert all(node['dependencies'] for node in proposal['nodes'] if node['tool'] != 'workspace_map_fields')
    serialized = json.dumps(proposal['nodes'])
    assert 'receipt_' not in serialized and '$output' in serialized
    newmanager, newtask, newtools, _, _, new, newdiff, _, _ = await pipeline(tmp_path / 'next', payment=100)
    assert new['receiptId'] != values['receiptId'] and newdiff['selectedIds'] == []
    replay_context, outputs = ToolContext({'id': 'replay'}), {}
    bindings = {name: slot['sourceValue'] for name, slot in proposal['descriptor']['slots'].items()}
    for node in proposal['nodes']:
        arguments = trajectory.resolve_arguments(node['arguments'], newmanager.task(newtask['id']), bindings, outputs)
        outputs[node['id']] = await newtools[node['tool']].execute(arguments, replay_context)
    derived_node = next(n for n in proposal['nodes'] if n['tool'] == 'workspace_derive_values')
    assert outputs[derived_node['id']]['totals']['paid'] == 205
    assert outputs[derived_node['id']]['receiptId'] != values['receiptId']



@pytest.mark.asyncio
async def test_missing_numeric_and_nonfinite_rejected(tmp_path):
    _, _, tools, ctx, traces, values, *_ = await pipeline(tmp_path)
    receipt = traces[0]['result']['receiptId']
    ctx.computations[receipt]['rows'][0]['values']['amount_cents'] = None
    with pytest.raises(ValueError, match='完整有限数值'):
        await tools['workspace_aggregate_keyed'].execute({'receiptId': receipt, 'measures': [{'field': 'amount_cents', 'alias': 'paid', 'operation': 'sum'}]}, ctx)
    with pytest.raises(ValueError, match='有限数值'):
        await tools['workspace_compare_values'].execute({'receiptId': values['receiptId'], 'name': 'x', 'leftAlias': 'paid', 'operator': 'gt', 'threshold': float('nan')}, ctx)

@pytest.mark.asyncio
async def test_runner_records_real_receipt_provenance(tmp_path):
    from backend.task_runner import TaskRunner, TaskRunRequest
    from backend.workspace import WorkspaceBank
    manager = WorkspaceManager(tmp_path)
    ws = manager.create('finance')
    manager.add_source(ws['id'], 'input.json', json.dumps({'orders': [{'order_id': 'a', 'installments': 8}]}).encode())
    public, _ = manager.create_task(ws['id'], '列出分期达到 8 期的订单并给出报告。', split='train')
    task = manager.tasks[public['id']]
    task['computeInterface'] = 'granular-compute-v1'
    task['deliveryContract'] = {'requiredMetricKeys': ['count'], 'requiredGroupNames': ['installments'], 'selectedIdField': 'order_id'}
    task['privateValidation'] = {'metrics': {'count': 1}, 'selectedIds': ['a'], 'groups': {'installments': ['a']}}
    binding = next(iter(task['tableBindings'].values()))
    class Model:
        model = 'injected'
        settings = {}
        async def complete(self, messages, tools):
            observations = [json.loads(m['content']).get('result', {}) for m in messages if m.get('role') == 'tool']
            valid = [r for r in observations if r.get('receiptId')]
            stage = len(valid)
            if stage == 0:
                name, args = 'workspace_map_fields', {'tableId': binding, 'keyField': 'order_id', 'fields': ['installments']}
            elif stage == 1:
                name, args = 'workspace_aggregate_keyed', {'receiptId': valid[-1]['receiptId'], 'measures': [{'field': 'installments', 'alias': 'inst', 'operation': 'max'}]}
            elif stage == 2:
                name, args = 'workspace_compare_values', {'receiptId': valid[-1]['receiptId'], 'name': 'installments', 'leftAlias': 'inst', 'operator': 'gte', 'threshold': 8}
            else:
                refs = valid[-1]['evidenceByKey']['a']
                name, args = 'workspace_publish_report', {'metrics': {'count': 1}, 'selectedIds': ['a'], 'evidenceIds': refs, 'summary': '本次订单 a 分期达到八期，建议内部复核。', 'groups': [{'name': 'installments', 'condition': '>=8', 'reason': '高分期', 'count': 1, 'selectedIds': ['a'], 'evidenceIds': refs}]}
            return {'message': {'content': None, 'tool_calls': [{'id': 'call'+str(stage), 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}, 'usage': {'input': 10, 'output': 5, 'reasoning': 0}, 'usageComplete': True, 'finishReason': 'tool_calls'}
    runner = TaskRunner(WorkspaceBank(manager), lambda _: Model(), learning_enabled=False, run_directory=tmp_path/'runs')
    run = await runner.start(TaskRunRequest(taskId=task['id'], strategy='react'))
    await runner.tasks[run['id']]
    await runner.shutdown()
    assert run['evaluation']['status'] == 'passed'
    traces = run['toolTrace']
    assert traces[1]['argumentSources']['receiptId'] == {'$output': {'traceIndex': 0, 'path': ['receiptId']}}
    assert traces[2]['argumentSources']['receiptId']['$output']['traceIndex'] == 1
    assert runner.evolution.versions == []


@pytest.mark.asyncio
async def test_graph_renumbering_is_not_a_structural_revision(tmp_path):
    manager, task, tools, _, traces, *_ = await pipeline(tmp_path)
    proposal = trajectory.induce({'id': 'source', 'toolTrace': traces}, manager.task(task['id']), list(tools.values()))
    renamed = deepcopy(proposal)
    ids = {n['id']: 'renamed_' + str(len(renamed['nodes']) - index) for index, n in enumerate(renamed['nodes'])}
    def remap(value):
        if isinstance(value, dict):
            if set(value) == {'$output'}:
                value['$output']['nodeId'] = ids[value['$output']['nodeId']]
            else:
                for item in value.values(): remap(item)
        elif isinstance(value, list):
            for item in value: remap(item)
    for node in renamed['nodes']:
        node['id'] = ids[node['id']]
        node['dependencies'] = [ids[d] for d in node['dependencies']]
        remap(node['arguments'])
    renamed['nodes'].reverse()
    assert trajectory.canonical_structure(renamed) == trajectory.canonical_structure(proposal)
    next(n for n in renamed['nodes'] if n['tool'] == 'workspace_select_missing')['arguments']['aliases'] = [{'$literal': 'line'}]
    assert trajectory.canonical_structure(renamed) != trajectory.canonical_structure(proposal)

@pytest.mark.asyncio
async def test_distinct_values_counts_current_periods_and_compiles_for_reuse(tmp_path):
    manager = WorkspaceManager(tmp_path)
    ws = manager.create('finance')
    manager.add_source(ws['id'], 'input.json', json.dumps({
        'orders': [
            {'order_id': 'a', 'purchased_month': '2018-01'},
            {'order_id': 'b', 'purchased_month': '2018-01'},
            {'order_id': 'c', 'purchased_month': '2018-02'},
            {'order_id': 'd', 'purchased_month': ''},
        ],
    }).encode())
    public, _ = manager.create_task(ws['id'], '汇总本次附件覆盖的不同订单月份数量。', split='train')
    task = manager.tasks[public['id']]
    task['computeInterface'] = 'granular-compute-v1'
    tools = {tool.name: tool for tool in manager.tools(task['id'])}
    args = {'tableId': task['tableBindings']['orders'], 'field': 'purchased_month'}
    context = ToolContext({'id': 'periods'})
    result = await tools['workspace_distinct_values'].execute(args, context)
    assert result == {
        'field': 'purchased_month', 'distinctCount': 2,
        'values': ['2018-01', '2018-02'], 'counts': {'2018-01': 2, '2018-02': 1},
        'nonemptyCount': 3, 'missingCount': 1, 'truncated': False,
    }
    assert len(context.evidence) == 4
    run = {'id': 'period-source', 'toolTrace': [
        {'tool': 'workspace_distinct_values', 'arguments': args, 'ok': True, 'result': result},
    ]}
    proposal = trajectory.induce(run, manager.task(task['id']), list(tools.values()))
    assert proposal['nodes'][0]['tool'] == 'workspace_distinct_values'
    assert proposal['nodes'][0]['arguments'] == {'tableId': {'$table': 'orders'}, 'field': 'purchased_month'}


@pytest.mark.asyncio
async def test_aggregate_rejects_count_alias_for_numeric_sum(tmp_path):
    from backend.workspace import WorkspaceManager
    from backend.workspace_compute import tools_for
    from backend.tools import ToolContext

    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance')
    manager.add_source(workspace['id'], 'rows.json', b'[{"order_id":"o1","amount_cents":100},{"order_id":"o1","amount_cents":50}]')
    table = manager.public_workspace(workspace['id'])['tables'][0]
    tools = {tool.name: tool for tool in tools_for(manager, workspace['id'], {'type': 'string'})}
    context = ToolContext({'id': 'test'})
    mapped = await tools['workspace_map_fields'].execute({
        'tableId': table['id'], 'keyField': 'order_id', 'fields': ['amount_cents'],
    }, context)
    with pytest.raises(ValueError, match='不产生记录计数'):
        await tools['workspace_aggregate_keyed'].execute({
            'receiptId': mapped['receiptId'],
            'measures': [{'field': 'amount_cents', 'alias': 'payment_count', 'operation': 'sum'}],
        }, context)


@pytest.mark.asyncio
async def test_compare_datetimes_returns_threshold_and_invalid_findings(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('support')
    manager.add_source(workspace['id'], 'responses.json', json.dumps({
        'responses': [
            {'complaint_id': 'late', 'received': '2026-01-01T00:00:00Z', 'sent': '2026-01-03T01:00:00Z'},
            {'complaint_id': 'edge', 'received': '2026-01-01T00:00:00Z', 'sent': '2026-01-03T00:00:00Z'},
            {'complaint_id': 'bad', 'received': '2026-01-02T00:00:00Z', 'sent': '2026-01-01T00:00:00Z'},
            {'complaint_id': 'missing', 'received': '', 'sent': '2026-01-01T00:00:00Z'},
        ],
    }).encode())
    public, _ = manager.create_task(workspace['id'], '复核严格超过48小时的投诉。', split='train')
    task = manager.tasks[public['id']]
    task['computeInterface'] = 'granular-compute-v1'
    tools = {tool.name: tool for tool in manager.tools(task['id'])}
    context = ToolContext({'id': 'datetime-test'})
    mapped = await tools['workspace_map_fields'].execute({
        'tableId': task['tableBindings']['responses'], 'keyField': 'complaint_id',
        'fields': ['received', 'sent'],
    }, context)
    result = await tools['workspace_compare_datetimes'].execute({
        'receiptId': mapped['receiptId'], 'fields': ['received', 'sent'],
        'name': 'delayed_transfer', 'operator': 'gt', 'thresholdHours': 48,
    }, context)
    invalid = await tools['workspace_select_invalid_datetimes'].execute({
        'receiptId': mapped['receiptId'], 'fields': ['received', 'sent'],
        'name': 'date_review',
    }, context)
    assert result['selectedIds'] == ['late']
    assert result['count'] == 1
    assert result['incompleteKeys'] == ['bad', 'missing']
    assert invalid['selectedIds'] == ['bad', 'missing']
    assert invalid['count'] == 2
    assert len(context.evidence) == 4
    source = {'$output': {'traceIndex': 0, 'path': ['receiptId']}}
    proposal = trajectory.induce({'id': 'datetime-source', 'toolTrace': [
        {'tool': 'workspace_map_fields', 'arguments': {
            'tableId': task['tableBindings']['responses'], 'keyField': 'complaint_id',
            'fields': ['received', 'sent'],
        }, 'ok': True, 'result': mapped},
        {'tool': 'workspace_compare_datetimes', 'arguments': {
            'receiptId': mapped['receiptId'], 'fields': ['received', 'sent'],
            'name': 'delayed_transfer', 'operator': 'gt', 'thresholdHours': 48,
        }, 'ok': True, 'result': result, 'argumentSources': {'receiptId': source}},
        {'tool': 'workspace_select_invalid_datetimes', 'arguments': {
            'receiptId': mapped['receiptId'], 'fields': ['received', 'sent'],
            'name': 'date_review',
        }, 'ok': True, 'result': invalid, 'argumentSources': {'receiptId': source}},
    ]}, manager.task(task['id']), list(tools.values()))
    assert [node['tool'] for node in proposal['nodes']] == [
        'workspace_map_fields', 'workspace_compare_datetimes',
        'workspace_select_invalid_datetimes',
    ]
    assert len(proposal['descriptor']['slots']) == 1


@pytest.mark.asyncio
async def test_mapped_filter_key_restriction_and_count_compile_for_reuse(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('tickets')
    manager.add_source(workspace['id'], 'tickets.json', json.dumps({
        'issues': [
            {'issue_id': 'a', 'state': 'open'},
            {'issue_id': 'b', 'state': 'closed'},
            {'issue_id': 'c', 'state': 'open'},
        ],
        'activity': [
            {'issue_id': 'a', 'comments': 5, 'assignee_count': 0, 'labels': 'bug, backend'},
            {'issue_id': 'b', 'comments': 10, 'assignee_count': 0, 'labels': 'bug'},
            {'issue_id': 'c', 'comments': 2, 'assignee_count': 1, 'labels': 'docs'},
        ],
    }).encode())
    public, _ = manager.create_task(
        workspace['id'],
        '复核 state 为 open 且评论达到 3 条的事项，标出 assignee_count 为零和 labels 包含 bug 的记录。',
        split='train',
    )
    task = manager.tasks[public['id']]
    task['computeInterface'] = 'granular-compute-v1'
    tools = {tool.name: tool for tool in manager.tools(task['id'])}
    context = ToolContext({'id': 'mapped-filter'})
    traces = []

    async def call(name, args):
        sources = {}
        for path, leaf in trajectory.walk(args):
            for index, trace in enumerate(traces):
                if leaf == trace['result'].get('receiptId'):
                    sources['/'.join(map(str, path))] = {
                        '$output': {'traceIndex': index, 'path': ['receiptId']},
                    }
        result = await tools[name].execute(args, context)
        traces.append({
            'tool': name, 'arguments': args, 'ok': True,
            'result': result, 'argumentSources': sources,
        })
        return result

    bindings = task['tableBindings']
    issues = await call('workspace_map_fields', {
        'tableId': bindings['issues'], 'keyField': 'issue_id', 'fields': ['state'],
    })
    open_rows = await call('workspace_filter_mapped_rows', {
        'receiptId': issues['receiptId'],
        'filters': [{'field': 'state', 'operator': 'equals', 'value': 'open'}],
    })
    open_keys = await call('workspace_select_keys', {
        'receiptId': open_rows['receiptId'], 'name': 'open',
    })
    activity = await call('workspace_map_fields', {
        'tableId': bindings['activity'], 'keyField': 'issue_id',
        'fields': ['comments', 'assignee_count', 'labels'],
    })
    open_activity = await call('workspace_restrict_to_keys', {
        'receiptId': activity['receiptId'], 'keysReceiptId': open_rows['receiptId'],
    })
    focus_rows = await call('workspace_filter_mapped_rows', {
        'receiptId': open_activity['receiptId'],
        'filters': [{'field': 'comments', 'operator': 'gte', 'value': 3}],
    })
    focus = await call('workspace_select_keys', {
        'receiptId': focus_rows['receiptId'], 'name': 'focus',
    })
    unassigned_rows = await call('workspace_filter_mapped_rows', {
        'receiptId': focus_rows['receiptId'],
        'filters': [{'field': 'assignee_count', 'operator': 'zero'}],
    })
    unassigned = await call('workspace_select_keys', {
        'receiptId': unassigned_rows['receiptId'], 'name': 'unassigned_focus',
    })
    counts = await call('workspace_count_keyed', {
        'receiptId': activity['receiptId'], 'alias': 'activity_rows',
    })
    open_counts = await call('workspace_restrict_to_keys', {
        'receiptId': counts['receiptId'], 'keysReceiptId': open_keys['receiptId'],
    })

    assert open_keys['selectedIds'] == ['a', 'c']
    assert focus['selectedIds'] == ['a']
    assert unassigned['selectedIds'] == ['a']
    assert counts['totals']['activity_rows'] == 3
    assert open_counts['totals']['activity_rows'] == 2
    assert set(open_counts['perKey']) == {'a', 'c'}

    proposal = trajectory.induce(
        {'id': 'mapped-filter-source', 'toolTrace': traces},
        manager.task(task['id']), list(tools.values()),
    )
    compiled_tools = [node['tool'] for node in proposal['nodes']]
    assert 'workspace_filter_mapped_rows' in compiled_tools
    assert 'workspace_restrict_to_keys' in compiled_tools
    assert 'workspace_count_keyed' in compiled_tools
    serialized = json.dumps(proposal['nodes'])
    assert 'receipt_' not in serialized
    assert serialized.count('$output') >= 6
