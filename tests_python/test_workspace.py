import asyncio
from io import BytesIO
import json
from zipfile import ZipFile

import httpx
import pytest

from backend.app import create_app
from backend.service import RunService
from backend.task_runner import TaskRunRequest, TaskRunner
from backend.intent_graph import compile_intent_graph, execute_graph
from backend.workspace import WorkspaceBank, WorkspaceManager
from backend.taskbank import TaskBank
from backend.workpacks import install_workpack, list_workpacks


def response(name=None, args=None):
    message = {'role': 'assistant', 'content': 'done'}
    if name:
        message['tool_calls'] = [{'id': name, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args or {})}}]
    return {'message': message, 'usage': {'input': 4, 'output': 1}, 'finishReason': 'stop'}


class Model:
    def __init__(self, role, evidence):
        self.model = role
        self.role = role
        self.evidence = evidence

    async def complete(self, messages, tools):
        calls = [call for message in messages for call in message.get('tool_calls') or []]
        names = {call['function']['name'] for call in calls}
        if 'workspace_preview_rows' not in names:
            return response('workspace_preview_rows', {'tableId': 'placeholder', 'page': 1, 'pageSize': 20})
        if 'workspace_publish_report' not in names:
            return response('workspace_publish_report', {'metrics': {'reviewed_rows': 2}, 'selectedIds': [],
                                                         'evidenceIds': self.evidence, 'summary': '资料已读取，等待用户复核。'})
        return response()


def mini_xlsx() -> bytes:
    output = BytesIO()
    with ZipFile(output, 'w') as archive:
        archive.writestr('xl/workbook.xml', '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet A" sheetId="1" r:id="rId1"/></sheets></workbook>''')
        archive.writestr('xl/_rels/workbook.xml.rels', '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''')
        archive.writestr('xl/worksheets/sheet1.xml', '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>order_id</t></is></c><c r="B1" t="inlineStr"><is><t>amount</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>a-1</t></is></c><c r="B2"><v>17</v></c></row></sheetData></worksheet>''')
    return output.getvalue()


async def test_workspace_parses_supported_files_scopes_evidence_and_never_learns_user_data(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance')
    manager.add_source(workspace['id'], 'orders.csv', b'order_id,status,amount\na-1,canceled,17\na-2,paid,9\n')
    manager.add_source(workspace['id'], 'policy.txt', b'Cancellation needs a finance review.\n')
    manager.add_source(workspace['id'], 'extra.json', b'[{"order_id":"a-3","amount":2}]')
    manager.add_source(workspace['id'], 'book.xlsx', mini_xlsx())
    current = manager.public_workspace(workspace['id'])
    assert len(current['sources']) == len(current['tables']) == 4
    order_table = next(table for table in current['tables'] if table['sheet'] == 'orders')
    preview = manager.preview(workspace['id'], order_table['id'])
    assert preview['records'][0]['_evidenceRef'].startswith('workspace:' + workspace['id'])
    assert preview['records'][0]['order_id'] == 'a-1'
    assert preview['records'][0]['amount'] == 17

    task, questions = manager.create_task(workspace['id'], '核对取消订单并提供有证据的内部草稿。')
    assert task and not questions
    tools = {tool.name: tool for tool in manager.tools(task['id'])}
    context = type('Context', (), {'run': {'id': 'manual'}, 'evidence': set()})()
    result = await tools['workspace_filter_rows'].execute({'tableId': order_table['id'], 'filters': [{'field': 'status', 'operator': 'equals', 'value': 'canceled'}], 'page': 1, 'pageSize': 20}, context)
    assert result['matchedCount'] == 1 and len(context.evidence) == 1
    report = await tools['workspace_publish_report'].execute({'metrics': {'reviewed_rows': 1}, 'selectedIds': ['a-1'],
                                                              'evidenceIds': sorted(context.evidence), 'summary': '仅建议人工复核，不执行退款。'}, context)
    assert report['evaluation']['status'] == 'user_review_required'

    grouped = await tools['workspace_aggregate_rows'].execute({'tableId': order_table['id'], 'operation': 'sum',
                                                                'field': 'amount', 'groupBy': 'status'}, context)
    assert grouped == {'groups': {'canceled': 17, 'paid': 9}, 'rowCount': 2}

    evidence = [record['_evidenceRef'] for record in manager.preview(workspace['id'], order_table['id'])['records']]
    class StableModel(Model):
        async def complete(self, messages, tools):
            calls = [call for message in messages for call in message.get('tool_calls') or []]
            names = {call['function']['name'] for call in calls}
            if 'workspace_preview_rows' not in names:
                return response('workspace_preview_rows', {'tableId': order_table['id'], 'page': 1, 'pageSize': 20})
            if 'workspace_publish_report' not in names:
                return response('workspace_publish_report', {'metrics': {'reviewed_rows': 2}, 'selectedIds': [], 'evidenceIds': evidence,
                                                             'summary': '读取当前订单，等待用户复核。'})
            return response()
    runner = TaskRunner(WorkspaceBank(manager), lambda role: StableModel(role, evidence), learning_enabled=False,
                        run_directory=tmp_path / 'runs', evolution_path=tmp_path / 'experience.json')
    run = await runner.start(TaskRunRequest(taskId=task['id'], strategy='react'))
    await runner.tasks[run['id']]
    assert run['status'] == 'completed'
    assert run['evaluation']['status'] == 'user_review_required'
    assert runner.evolution.versions == []

    source = current['sources'][0]
    manager.remove_source(workspace['id'], source['id'])
    assert source['id'] not in {item['id'] for item in manager.public_workspace(workspace['id'])['sources']}
    await runner.shutdown()


async def test_workspace_reconcile_keyed_sums_uses_only_current_tables_and_records_source_evidence(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance')
    manager.add_source(workspace['id'], 'orders.csv', b'order_id,status\no-1,paid\no-2,paid\no-3,paid\n')
    manager.add_source(workspace['id'], 'payments.csv', b'order_id,amount_cents\no-1,100\no-2,50\n')
    manager.add_source(workspace['id'], 'items.csv', b'order_id,price_cents,freight_cents\no-1,90,5\no-2,50,0\n')
    task, questions = manager.create_task(workspace['id'], '按订单键核对当前多张资料中的金额。')
    assert task and not questions
    tables = {table['sheet']: table['id'] for table in manager.public_workspace(workspace['id'])['tables']}
    tools = {tool.name: tool for tool in manager.tools(task['id'])}
    context = type('Context', (), {'run': {'id': 'manual'}, 'evidence': set()})()

    result = await tools['workspace_reconcile_keyed_sums'].execute({
        'anchorTableId': tables['orders'], 'keyField': 'order_id',
        'aggregates': [
            {'tableId': tables['payments'], 'keyField': 'order_id', 'field': 'amount_cents', 'alias': 'paid'},
            {'tableId': tables['items'], 'keyField': 'order_id', 'field': 'price_cents', 'alias': 'price'},
            {'tableId': tables['items'], 'keyField': 'order_id', 'field': 'freight_cents', 'alias': 'freight'},
        ],
        'derivedTotals': [{'name': 'line', 'aliases': ['price', 'freight']}],
        'comparisons': [{'name': 'mismatch', 'leftAlias': 'paid', 'rightAliases': ['line'],
                         'operator': 'abs_gt', 'threshold': 1}],
    }, context)

    assert result['totals'] == {'paid': 150, 'price': 140, 'freight': 5, 'line': 145}
    assert result['perKey']['o-1'] == {'paid': 100, 'price': 90, 'freight': 5, 'line': 95}
    assert result['missingByAlias'] == {'paid': ['o-3'], 'price': ['o-3'], 'freight': ['o-3']}
    assert result['missingAnyCount'] == 1 and result['missingAnyKeys'] == ['o-3']
    assert result['comparisons'] == [{'name': 'mismatch', 'operator': 'abs_gt', 'threshold': 1,
                                      'count': 1, 'keys': ['o-1'], 'truncated': False,
                                      'matchingTotals': {'paid': 100, 'price': 90, 'freight': 5, 'line': 95}}]
    # Evidence comes from the current anchor and source rows used by the
    # calculation, never from any external expected-answer source.
    assert len(context.evidence) == 7


async def test_workspace_reconcile_keyed_sums_supports_explicit_weighted_ratio_comparisons(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance')
    manager.add_source(workspace['id'], 'orders.csv', b'order_id,status\no-1,paid\no-2,paid\no-3,paid\n')
    manager.add_source(workspace['id'], 'items.csv', b'order_id,price_cents,freight_cents\no-1,100,20\no-2,80,15\no-3,0,7\n')
    task, questions = manager.create_task(workspace['id'], '找出运费达到商品金额 20% 的订单。')
    assert task and not questions
    tables = {table['sheet']: table['id'] for table in manager.public_workspace(workspace['id'])['tables']}
    tools = {tool.name: tool for tool in manager.tools(task['id'])}
    context = type('Context', (), {'run': {'id': 'manual'}, 'evidence': set()})()

    result = await tools['workspace_reconcile_keyed_sums'].execute({
        'anchorTableId': tables['orders'], 'keyField': 'order_id',
        'aggregates': [
            {'tableId': tables['items'], 'keyField': 'order_id', 'field': 'price_cents', 'alias': 'price'},
            {'tableId': tables['items'], 'keyField': 'order_id', 'field': 'freight_cents', 'alias': 'freight'},
        ],
        'comparisons': [{
            'name': 'freight_at_least_twenty_percent', 'leftAlias': 'freight',
            'rightTerms': [{'alias': 'price', 'multiplier': 0.2}],
            'operator': 'gte', 'threshold': 0,
        }],
    }, context)

    assert result['comparisons'] == [{
        'name': 'freight_at_least_twenty_percent', 'operator': 'gte', 'threshold': 0,
        'count': 2, 'keys': ['o-1', 'o-3'], 'truncated': False,
        'matchingTotals': {'price': 100, 'freight': 27},
        'rightTerms': [{'alias': 'price', 'multiplier': 0.2}],
    }]
    assert len(context.evidence) == 6


async def test_workspace_reconcile_keyed_sums_accepts_one_to_many_anchor_keys_and_keeps_all_anchor_evidence(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance')
    manager.add_source(workspace['id'], 'items.csv', b'order_id,price_cents,freight_cents\no-1,100,20\no-1,50,10\no-2,40,3\n')
    task, questions = manager.create_task(workspace['id'], '按订单汇总订单行中的运费和商品金额。')
    assert task and not questions
    tables = {table['sheet']: table['id'] for table in manager.public_workspace(workspace['id'])['tables']}
    tool = {tool.name: tool for tool in manager.tools(task['id'])}['workspace_reconcile_keyed_sums']
    context = type('Context', (), {'run': {'id': 'manual'}, 'evidence': set()})()

    result = await tool.execute({
        'anchorTableId': tables['items'], 'keyField': 'order_id',
        'aggregates': [
            {'tableId': tables['items'], 'keyField': 'order_id', 'field': 'price_cents', 'alias': 'price'},
            {'tableId': tables['items'], 'keyField': 'order_id', 'field': 'freight_cents', 'alias': 'freight'},
        ],
        'comparisons': [{'name': 'freight_twenty_percent', 'leftAlias': 'freight',
                         'rightTerms': [{'alias': 'price', 'multiplier': .2}], 'operator': 'gte', 'threshold': 0}],
    }, context)

    assert result['anchorCount'] == 2 and result['anchorRowCount'] == 3
    assert result['perKey']['o-1'] == {'price': 150, 'freight': 30}
    assert result['comparisons'][0]['keys'] == ['o-1']
    assert len(context.evidence) == 3


async def test_workspace_reconcile_keyed_sums_allows_redundant_matching_aliases_but_rejects_conflicts(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance')
    manager.add_source(workspace['id'], 'orders.csv', b'order_id\no-1\n')
    manager.add_source(workspace['id'], 'items.csv', b'order_id,value\no-1,1\n')
    task, _ = manager.create_task(workspace['id'], '比较当前金额。')
    tables = {table['sheet']: table['id'] for table in manager.public_workspace(workspace['id'])['tables']}
    tool = {tool.name: tool for tool in manager.tools(task['id'])}['workspace_reconcile_keyed_sums']
    context = type('Context', (), {'run': {'id': 'manual'}, 'evidence': set()})()

    accepted = await tool.execute({
        'anchorTableId': tables['orders'], 'keyField': 'order_id',
        'aggregates': [{'tableId': tables['items'], 'keyField': 'order_id', 'field': 'value', 'alias': 'value'}],
        'comparisons': [{'name': 'redundant', 'leftAlias': 'value', 'rightAliases': ['value'],
                         'rightTerms': [{'alias': 'value', 'multiplier': 1}], 'operator': 'equals', 'threshold': 0}],
    }, context)
    assert accepted['comparisons'][0]['count'] == 1

    with pytest.raises(ValueError, match='别名顺序必须一致'):
        await tool.execute({
            'anchorTableId': tables['orders'], 'keyField': 'order_id',
            'aggregates': [{'tableId': tables['items'], 'keyField': 'order_id', 'field': 'value', 'alias': 'value'}],
            'comparisons': [{'name': 'conflict', 'leftAlias': 'value', 'rightAliases': ['other'],
                             'rightTerms': [{'alias': 'value', 'multiplier': 1}], 'operator': 'equals', 'threshold': 0}],
        }, context)


async def test_workspace_aggregate_count_rejects_ambiguous_group_by_and_group_count_remains_explicit(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('support')
    manager.add_source(workspace['id'], 'complaints.csv', b'channel\nweb\nweb\nphone\n')
    task, _ = manager.create_task(workspace['id'], '统计当前投诉渠道。')
    table_id = manager.public_workspace(workspace['id'])['tables'][0]['id']
    tool = {tool.name: tool for tool in manager.tools(task['id'])}['workspace_aggregate_rows']
    context = type('Context', (), {'run': {'id': 'manual'}, 'evidence': set()})()

    with pytest.raises(ValueError, match='group_count'):
        await tool.execute({'tableId': table_id, 'operation': 'count', 'groupBy': 'channel'}, context)
    assert await tool.execute({'tableId': table_id, 'operation': 'group_count', 'groupBy': 'channel'}, context) == {
        'counts': {'web': 2, 'phone': 1}, 'rowCount': 3,
    }


async def test_workspace_draft_is_not_counted_as_a_report_attempt(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance')
    manager.add_source(workspace['id'], 'orders.csv', b'order_id,status\na-1,canceled\n')
    task, questions = manager.create_task(workspace['id'], '列出取消订单并保存有证据的内部报告。')
    assert task and not questions
    table_id = manager.public_workspace(workspace['id'])['tables'][0]['id']

    class DraftThenPublish:
        model = 'draft-then-publish'
        settings = {}

        async def complete(self, messages, _tools):
            names = {call['function']['name'] for message in messages for call in message.get('tool_calls') or []}
            if 'workspace_preview_rows' not in names:
                return response('workspace_preview_rows', {'tableId': table_id, 'page': 1, 'pageSize': 20})
            if 'workspace_save_draft' not in names:
                return response('workspace_save_draft', {'title': '内部草稿', 'body': '仅供人工复核。'})
            if 'workspace_publish_report' not in names:
                evidence = _evidence_from_messages(messages)
                return response('workspace_publish_report', {'metrics': {'reviewed_rows': 1}, 'selectedIds': ['a-1'],
                                                             'evidenceIds': evidence, 'summary': '已列出当前取消订单。'})
            return response()

    runner = TaskRunner(WorkspaceBank(manager), lambda _role: DraftThenPublish(), learning_enabled=False,
                        run_directory=tmp_path / 'runs', evolution_path=tmp_path / 'experience.json')
    run = await runner.start(TaskRunRequest(taskId=task['id'], strategy='react'))
    await runner.tasks[run['id']]
    assert run['status'] == 'completed'
    assert run['evaluation']['status'] == 'user_review_required'
    assert run['metrics']['reportAttempts'] == 1
    assert run['metrics']['failedReportAttempts'] == 0
    await runner.shutdown()


async def test_workspace_http_accepts_raw_file_bytes_and_rejects_json_body_requirement(tmp_path, monkeypatch):
    class Bank:
        def __init__(self):
            self.root = tmp_path
            self.tasks, self.gold, self.manifest = {}, {}, None
        def load(self):
            pass
    monkeypatch.setattr('backend.app.TaskBank', Bank)
    monkeypatch.setattr('backend.app.install_workpack', lambda _manager, _bank, _pack_id: ({'id': 'workspace'}, {'id': 'task'}))
    app = create_app(RunService(tmp_path / 'legacy'))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            created = await client.post('/api/workspaces', json={'role': 'support', 'label': '投诉资料'})
            assert created.status_code == 201
            workspace_id = created.json()['id']
            uploaded = await client.post(f'/api/workspaces/{workspace_id}/files?name=complaints.csv', content=b'id,channel\n1,web\n', headers={'Content-Type': 'application/octet-stream'})
            assert uploaded.status_code == 201
            detail = (await client.get('/api/workspaces/' + workspace_id)).json()
            assert detail['tables'][0]['fields'] == ['id', 'channel']
            runs = await client.get(f'/api/workspaces/runs?workspaceId={workspace_id}')
            assert runs.status_code == 200
            assert runs.json()['runs'] == []
            clarification = await client.post(f'/api/workspaces/{workspace_id}/tasks', json={'request': '请比较两期投诉变化。'})
            assert clarification.status_code == 201
            assert clarification.json()['status'] == 'needs_clarification'
            installed = await client.post('/api/workpacks/example/workspace')
            assert installed.status_code == 201
            assert installed.json()['task']['id'] == 'task'


def test_workpacks_freeze_72_source_traceable_instances_and_use_workspace_parser(tmp_path):
    bank = TaskBank()
    bank.load()
    packs = list_workpacks(bank)
    assert len(packs) == 72
    assert {scenario: sum(item['scenario'] == scenario for item in packs) for scenario in ['finance', 'support', 'tickets']} == {
        'finance': 24, 'support': 24, 'tickets': 24,
    }
    assert {split: sum(item['split'] == split for item in packs) for split in ['train', 'validation', 'test']} == {
        'train': 48, 'validation': 12, 'test': 12,
    }
    manager = WorkspaceManager(tmp_path)
    for pack_id in ['finance-reconciliation-01', 'support-policy-draft-01', 'tickets-export-comparison-01']:
        workspace, task = install_workpack(manager, bank, pack_id)
        internal = manager.tasks[task['id']]
        assert workspace['provenance'] == 'predefined_workpack'
        assert workspace['sources'] and workspace['tables']
        assert internal['privateValidation']['requiredEvidenceIds']
        assert 'privateValidation' not in task
        assert task['deliveryContract']['requiredSources']
        assert 'metrics' in task['deliveryContract']
        public_text = json.dumps(task, ensure_ascii=False)
        private_text = json.dumps(internal['privateValidation'], ensure_ascii=False)
        assert 'privateValidation' not in public_text
        assert 'requiredEvidenceIds' not in public_text
        assert private_text not in public_text
    ticket = next(item for item in packs if item['id'] == 'tickets-export-comparison-01')
    assert ticket['sourceProvenance']['injectedAnomaly'] is True
    finance = next(item for item in packs if item['id'] == 'finance-reconciliation-01')
    assert '严格大于 1 分' in finance['task']
    assert '仅列出待复核的 order_id' in finance['task']


def test_ticket_workpack_exposes_source_reference_time_without_private_answer(tmp_path):
    bank = TaskBank()
    bank.load()
    manager = WorkspaceManager(tmp_path)
    _, task = install_workpack(manager, bank, 'tickets-triage-01')
    internal = manager.task(task['id'])
    source = bank.task('tickets-unassigned-01')

    assert task['asOf'] == source['asOf']
    assert task['deliveryContract']['referenceTime'] == source['asOf']
    public_text = json.dumps(task, ensure_ascii=False)
    assert 'referenceTime' in public_text
    assert 'privateValidation' not in public_text
    assert 'requiredEvidenceIds' not in public_text


async def test_workspace_schema_plan_binds_only_current_workspace_tables(tmp_path):
    bank = TaskBank()
    bank.load()
    manager = WorkspaceManager(tmp_path)
    _, first = install_workpack(manager, bank, 'finance-reconciliation-01')
    _, second = install_workpack(manager, bank, 'finance-reconciliation-02')
    first_task, second_task = manager.task(first['id']), manager.task(second['id'])
    first_tools, second_tools = manager.tools(first['id']), manager.tools(second['id'])
    assert first_task['schemaContract'] == second_task['schemaContract']
    plan = {'steps': [
        {'id': 'orders', 'intent': '读取 orders 表中的 order_id、status 和日期字段。', 'dependencies': [], 'sourceTable': 'orders'},
        {'id': 'payments', 'intent': '读取 payments 表中的 order_id、支付金额和分期字段。', 'dependencies': [], 'sourceTable': 'payments'},
        {'id': 'items', 'intent': '读取 items 表中的 order_id、商品金额和运费字段。', 'dependencies': [], 'sourceTable': 'items'},
    ]}
    retrieval = {step['id']: [{'name': 'workspace_preview_rows', 'score': 1.0}] for step in plan['steps']}
    proposal = {'nodes': [{'id': step['id'], 'tool': 'workspace_preview_rows'} for step in plan['steps']]}
    graph = compile_intent_graph(plan, proposal, retrieval, first_tools)

    runtime_nodes = TaskRunner.resolve_runtime_nodes(graph, second_task)
    observed = []
    context = type('Context', (), {'run': {'id': 'bound'}, 'evidence': set()})()
    known = {tool.name: tool for tool in second_tools}

    async def invoke(name, arguments, node):
        observed.append((name, arguments, node))
        return await known[name].execute(arguments, context)

    await execute_graph(runtime_nodes, second_tools, invoke, lambda _node, _state: None)
    assert observed
    required_sources = set(manager.tasks[second['id']]['privateValidation']['requiredSources'])
    required_table_ids = {
        table['id'] for table in manager.workspace(second_task['workspaceId'])['tables'].values()
        if table['sourceName'] in required_sources
    }
    assert {arguments['tableId'] for _, arguments, _ in observed} == required_table_ids
    assert not {arguments['tableId'] for _, arguments, _ in observed} & set(first_task['tableBindings'].values())
    assert context.evidence


async def test_workspace_same_table_match_reuses_current_rows_and_filters_once(tmp_path):
    """A schema-slot selection is a local view, not a duplicate table read."""
    bank = TaskBank()
    bank.load()
    manager = WorkspaceManager(tmp_path)
    _, public_task = install_workpack(manager, bank, 'support-health-rollup-01')
    task = manager.task(public_task['id'])
    tools = manager.tools(public_task['id'])
    plan = {'steps': [
        {'id': 'complaints', 'intent': '读取投诉表全部记录。', 'dependencies': [], 'sourceTable': 'complaints'},
        {'id': 'late', 'intent': '从投诉表筛选 timely 为 No 的记录并提取 complaint_id。', 'dependencies': ['complaints'],
         'sourceTable': 'complaints', 'selection': {'kind': 'match', 'sourceStepId': 'complaints', 'field': 'timely', 'operator': 'equals', 'value': 'No'}},
    ]}
    retrieval = {step['id']: [{'name': 'workspace_preview_rows', 'score': 1.0}] for step in plan['steps']}
    proposal = {'nodes': [{'id': step['id'], 'tool': 'workspace_preview_rows'} for step in plan['steps']]}
    nodes = TaskRunner.resolve_runtime_nodes(compile_intent_graph(plan, proposal, retrieval, tools), task)
    late = next(node for node in nodes if node['id'] == 'late')
    assert late['reuse']['nodeId'] == 'complaints'
    assert late['reuse']['filter'] == {'field': 'timely', 'operator': 'equals', 'value': 'No'}

    observed = []
    context = type('Context', (), {'run': {'id': 'filtered'}, 'evidence': set()})()
    known = {tool.name: tool for tool in tools}

    async def invoke(name, arguments, node):
        observed.append((name, arguments, node))
        return await known[name].execute(arguments, context)

    filtered = []
    outputs = await execute_graph(nodes, tools, invoke, lambda _node, _state: None,
                                  on_filter=lambda _node, detail: filtered.append(detail))
    assert len(observed) == 1
    assert filtered and filtered[0]['selectedRecords'] < filtered[0]['totalRecords']
    assert all(row['timely'] == 'No' for page in outputs['late'] for row in page['records'])


def test_workspace_cross_table_match_fails_closed(tmp_path):
    bank = TaskBank()
    bank.load()
    manager = WorkspaceManager(tmp_path)
    _, public_task = install_workpack(manager, bank, 'tickets-triage-01')
    tools = manager.tools(public_task['id'])
    plan = {'steps': [
        {'id': 'issues', 'intent': '读取 issues 表全部记录。', 'dependencies': [], 'sourceTable': 'issues'},
        {'id': 'labels', 'intent': '读取 labels 表中 open issue 的标签。', 'dependencies': ['issues'], 'sourceTable': 'labels',
         'selection': {'kind': 'match', 'sourceStepId': 'issues', 'field': 'state', 'operator': 'equals', 'value': 'open'}},
    ]}
    retrieval = {step['id']: [{'name': 'workspace_preview_rows', 'score': 1.0}] for step in plan['steps']}
    proposal = {'nodes': [{'id': step['id'], 'tool': 'workspace_preview_rows'} for step in plan['steps']]}
    with pytest.raises(ValueError, match='Plan selection cannot be bound'):
        compile_intent_graph(plan, proposal, retrieval, tools)


def test_workspace_model_selection_hands_entire_dependency_suffix_to_model(tmp_path):
    bank = TaskBank()
    bank.load()
    manager = WorkspaceManager(tmp_path)
    _, public_task = install_workpack(manager, bank, 'tickets-triage-01')
    tools = manager.tools(public_task['id'])
    plan = {'steps': [
        {'id': 'issues', 'intent': '读取 issues 表全部记录。', 'dependencies': [], 'sourceTable': 'issues'},
        {'id': 'candidates', 'intent': '筛选需要人工判断的未分派 issue。', 'dependencies': ['issues'], 'sourceTable': 'issues',
         'selection': {'kind': 'model', 'reason': '条件包含日期范围和或逻辑。'}},
        {'id': 'labels', 'intent': '读取候选 issue 的标签。', 'dependencies': ['candidates'], 'sourceTable': 'labels'},
    ]}
    retrieval = {step['id']: [{'name': 'workspace_preview_rows', 'score': 1.0}] for step in plan['steps']}
    proposal = {'nodes': [{'id': step['id'], 'tool': 'workspace_preview_rows'} for step in plan['steps']]}
    nodes = compile_intent_graph(plan, proposal, retrieval, tools)
    by_id = {node['id']: node for node in nodes}
    assert not by_id['issues'].get('defer')
    assert by_id['candidates']['defer'] is True
    assert by_id['labels']['defer'] is True


def test_workspace_cross_table_dependency_still_selects_a_paginated_table_reader(tmp_path):
    from backend.intent_graph import select_retrieved_graph
    bank = TaskBank()
    bank.load()
    manager = WorkspaceManager(tmp_path)
    _, public_task = install_workpack(manager, bank, 'tickets-triage-01')
    tools = manager.tools(public_task['id'])
    plan = {'steps': [
        {'id': 'issues', 'intent': '读取 issues 表。', 'dependencies': [], 'sourceTable': 'issues'},
        {'id': 'activity', 'intent': '读取 activity 表中的评论和更新时间。', 'dependencies': ['issues'], 'sourceTable': 'activity'},
    ]}
    retrieval = {step['id']: [{'name': 'workspace_preview_rows', 'score': 1.0}] for step in plan['steps']}
    proposal, _ = select_retrieved_graph(plan, retrieval, tools)
    assert {node['id']: node['tool'] for node in proposal['nodes']} == {
        'issues': 'workspace_preview_rows', 'activity': 'workspace_preview_rows',
    }


def test_workspace_plan_accepts_descriptive_step_ids_within_graph_limit():
    from backend.intent_graph import validate_plan
    plan = {'steps': [
        {'id': 'filter_open_unassigned_no_milestone_or_stale_records', 'intent': '筛选当前记录。', 'dependencies': []},
        {'id': 'follow_up', 'intent': '读取后续字段。', 'dependencies': ['filter_open_unassigned_no_milestone_or_stale_records'],
         'selection': {'kind': 'model', 'reason': '组合条件需要模型确认。'}},
    ]}
    validate_plan(plan)


def test_workspace_schema_steps_are_not_removed_by_lexical_task_pruning():
    from backend.intent_graph import prune_unrequested_steps
    plan = {'steps': [
        {'id': 'issues', 'intent': '读取 issue 列表。', 'dependencies': [], 'sourceTable': 'issues'},
        {'id': 'labels', 'intent': '读取 labels 表以判断 priority。', 'dependencies': ['issues'], 'sourceTable': 'labels'},
    ]}
    kept, removed = prune_unrequested_steps(plan, '统计当前优先项数量并附证据。')
    assert [step['id'] for step in kept['steps']] == ['issues', 'labels']
    assert removed == []


async def test_workspace_train_graph_persists_g0_and_fast_reuses_current_table_slots(tmp_path):
    bank = TaskBank()
    bank.load()
    manager = WorkspaceManager(tmp_path)
    _, first_public = install_workpack(manager, bank, 'finance-reconciliation-01')
    _, second_public = install_workpack(manager, bank, 'finance-reconciliation-02')
    expected = {}

    class WorkspaceGraphModel:
        model = 'workspace-graph-regression'
        settings = {}

        async def complete(self, messages, tools):
            names = {tool.name for tool in tools}
            if 'submit_plan' in names:
                return response('submit_plan', {'steps': [
                    {'id': 'orders', 'intent': '读取 orders 表中的 order_id、status 和日期字段。', 'dependencies': [], 'sourceTable': 'orders'},
                    {'id': 'payments', 'intent': '读取 payments 表中的 order_id、支付金额和分期字段。', 'dependencies': [], 'sourceTable': 'payments'},
                    {'id': 'items', 'intent': '读取 items 表中的 order_id、商品金额和运费字段。', 'dependencies': [], 'sourceTable': 'items'},
                ]})
            if 'workspace_publish_report' not in names:
                return response('request_tools', {'intent': '提交当前工作区的有证据分析报告。'})
            observed = _evidence_from_messages(messages)
            return response('workspace_publish_report', {
                'metrics': expected['metrics'],
                'selectedIds': expected['selectedIds'],
                'evidenceIds': observed,
                'summary': '当前工作区资料已完成核对，结果等待人工复核。',
            })

    runner = TaskRunner(WorkspaceBank(manager), lambda _role: WorkspaceGraphModel(), learning_enabled=True,
                        run_directory=tmp_path / 'runs', evolution_path=tmp_path / 'experience.json')
    first_task = manager.tasks[first_public['id']]
    expected.update(first_task['privateValidation'])
    first = await runner.start(TaskRunRequest(taskId=first_public['id'], strategy='graph_rsi'))
    await runner.tasks[first['id']]

    assert first['status'] == 'completed'
    assert first['evaluation']['status'] == 'passed'
    assert 'maintenanceError' not in first['evolution']
    assert first['evolution']['tinyEdgeMaintenance']['workflowStatus'] == 'recorded'
    assert first['evolution']['graphOptimization']['reasonCode'] == 'workspace_table_slots'
    assert len(runner.evolution.versions) == 1
    g0 = runner.evolution.versions[0]

    second_task = manager.tasks[second_public['id']]
    expected.update(second_task['privateValidation'])
    second = await runner.start(TaskRunRequest(taskId=second_public['id'], strategy='graph_rsi'))
    await runner.tasks[second['id']]

    assert second['status'] == 'completed'
    assert second['evaluation']['status'] == 'passed'
    assert second['evolution']['planningPath'] == 'fast'
    assert second['evolution']['usedVersionId'] == g0['id']
    assert second['phaseMetrics']['plan']['requests'] == 0
    assert 'maintenanceError' not in second['evolution']
    bound_table_ids = {
        trace['arguments']['tableId'] for trace in second['toolTrace']
        if trace['executor'] == 'graph' and trace['tool'] == 'workspace_preview_rows'
    }
    assert bound_table_ids
    assert not bound_table_ids & set(first_task['tableBindings'].values())
    assert len(runner.evolution.workflows) == 2
    assert runner.evolution.tiny_edges
    await runner.shutdown()


async def test_workspace_delivery_contract_is_public_trace_context_not_private_validation(tmp_path):
    bank = TaskBank()
    bank.load()
    manager = WorkspaceManager(tmp_path)
    _, public_task = install_workpack(manager, bank, 'finance-cancel-installments-01')
    internal = manager.task(public_task['id'])
    expected = internal['privateValidation']
    captured = []

    class ContractModel:
        model = 'workspace-delivery-contract-regression'
        settings = {}

        async def complete(self, messages, tools):
            captured.extend(messages)
            names = {tool.name for tool in tools}
            if 'submit_plan' in names:
                return response('submit_plan', {'steps': [
                    {'id': 'orders', 'intent': '读取 orders 表。', 'dependencies': [], 'sourceTable': 'orders'},
                    {'id': 'payments', 'intent': '读取 payments 表。', 'dependencies': [], 'sourceTable': 'payments'},
                ]})
            if 'workspace_publish_report' not in names:
                return response('request_tools', {'intent': '完成公开交付口径的分析。'})
            return response('workspace_publish_report', {
                'metrics': expected['metrics'], 'selectedIds': expected['selectedIds'],
                'evidenceIds': _evidence_from_messages(messages), 'summary': '基于当前观察生成内部风险队列。',
            })

    runner = TaskRunner(WorkspaceBank(manager), lambda _role: ContractModel(), learning_enabled=False,
                        run_directory=tmp_path / 'runs', evolution_path=tmp_path / 'experience.json')
    run = await runner.start(TaskRunRequest(taskId=public_task['id'], strategy='graph_rsi'))
    await runner.tasks[run['id']]
    trace_contract = next(event for event in run['events'] if event['type'] == 'delivery_contract')
    assert trace_contract['detail'] == public_task['deliveryContract']
    model_text = json.dumps(captured, ensure_ascii=False)
    assert '本次公开交付口径' in model_text
    assert 'privateValidation' not in model_text
    assert 'requiredEvidenceIds' not in model_text
    assert run['evaluation']['status'] == 'passed'
    await runner.shutdown()


def _evidence_from_messages(messages):
    values = []

    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get('_evidenceRef'), str):
                values.append(value['_evidenceRef'])
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for message in messages:
        if message.get('role') != 'tool':
            continue
        walk(json.loads(message['content']))
    return sorted(set(values))


async def test_workspace_invalid_planner_does_not_inject_a_workpack_graph(tmp_path):
    bank = TaskBank()
    bank.load()
    manager = WorkspaceManager(tmp_path)
    _, public_task = install_workpack(manager, bank, 'finance-reconciliation-01')
    task = manager.tasks[public_task['id']]
    class InvalidPlanner:
        model = 'invalid-planner'
        settings = {}

        async def complete(self, messages, tools):
            # A malformed planner cannot be replaced by a benchmark-only
            # graph. The normal fallback stays observable for repair.
            return response()

    class PublishingExecutor:
        model = 'publishing-executor'
        settings = {}

        async def complete(self, messages, tools):
            return response()

    executor = PublishingExecutor()

    def provider(role):
        return InvalidPlanner() if role == 'planner' else executor

    runner = TaskRunner(WorkspaceBank(manager), provider, learning_enabled=False,
                        run_directory=tmp_path / 'runs', evolution_path=tmp_path / 'experience.json')
    run = await runner.start(TaskRunRequest(taskId=public_task['id'], strategy='graph_rsi'))
    await runner.tasks[run['id']]

    assert run['evaluation']['status'] == 'failed'
    assert not run.get('graph')
    assert not (run.get('evolution') or {}).get('workpackGraphPrefix')
    assert not any(row.get('selection') == 'workpack-schema-prefix' for row in run.get('graphSelection') or [])
    await runner.shutdown()
