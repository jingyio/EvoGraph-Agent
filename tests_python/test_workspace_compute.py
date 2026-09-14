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
