import asyncio
from io import BytesIO
import json
import shutil
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


def test_workspace_keeps_user_inputs_outside_hidden_runtime_directory_and_restores_them(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance', label='取消订单复核')
    first = manager.add_source(workspace['id'], 'orders.csv', b'order_id,status\na-1,canceled\n')
    task, questions = manager.create_task(workspace['id'], '核对当前订单并形成有证据的内部复核简报。')
    assert task and not questions
    second = manager.add_source(workspace['id'], 'orders.csv', b'order_id,status\na-2,paid\n')

    root = manager._workspace_path(workspace['id'])
    assert root.name.startswith('finance-取消订单复核-')
    assert root.name != workspace['id']
    assert (root / 'inputs' / 'orders.csv').read_bytes().startswith(b'order_id')
    assert (root / 'inputs' / 'orders-2.csv').read_bytes().endswith(b'paid\n')
    requests = sorted((root / 'requests').glob('request-*.txt'))
    assert len(requests) == 1
    assert requests[0].read_text(encoding='utf-8') == task['task'] + '\n'
    assert (root / '.rsi' / 'workspace.json').is_file()
    assert (root / '.rsi' / 'tables.json').is_file()
    assert not (root / 'workspace.json').exists()
    assert not (root / 'tables.json').exists()
    assert 'storageName' not in manager.public_workspace(workspace['id'])['sources'][0]
    assert 'storageKey' not in manager.public_workspace(workspace['id'])
    assert manager.public_workspace(workspace['id'])['folderName'] == root.name
    assert manager.public_workspace(workspace['id'])['folderPath'] == f'artifacts/workspaces/{root.name}'
    assert manager.source_path(workspace['id'], first['source']['id']).name == 'orders.csv'
    assert manager.source_path(workspace['id'], second['source']['id']).name == 'orders-2.csv'

    restored = WorkspaceManager(tmp_path)
    restored.restore()
    assert restored.task(task['id'])['task'] == task['task']
    assert restored.source_path(workspace['id'], second['source']['id']).name == 'orders-2.csv'
    restored.remove_source(workspace['id'], second['source']['id'])
    assert not (root / 'inputs' / 'orders-2.csv').exists()


def test_workspace_restores_legacy_metadata_and_source_paths_without_migrating_them(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance')
    source = manager.add_source(workspace['id'], 'orders.csv', b'order_id\na-1\n')['source']
    readable_root = manager._workspace_path(workspace['id'])
    root = tmp_path / 'artifacts' / 'workspaces' / workspace['id']
    root.mkdir(parents=True)
    metadata = manager.workspace(workspace['id']).copy()
    metadata.pop('storageKey')
    runtime = root / '.rsi'
    legacy_sources = root / 'sources'
    legacy_sources.mkdir()
    manager.source_path(workspace['id'], source['id']).replace(legacy_sources / f'{source["id"]}-orders.csv')
    (root / 'workspace.json').write_text(json.dumps(metadata), encoding='utf-8')
    (root / 'tables.json').write_text(json.dumps(manager.workspace(workspace['id'])['tables']), encoding='utf-8')
    shutil.rmtree(readable_root)

    restored = WorkspaceManager(tmp_path)
    restored.restore()
    assert restored.public_workspace(workspace['id'])['sources'][0]['name'] == 'orders.csv'
    assert restored.source_path(workspace['id'], source['id']).name == f'{source["id"]}-orders.csv'
    assert not (root / '.rsi').exists()


def test_workspace_followup_uses_only_parent_visible_report_context(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance')
    manager.add_source(workspace['id'], 'orders.csv', b'order_id,status\na-1,canceled\n')
    first, questions = manager.create_task(workspace['id'], '核对当前订单并形成内部复核简报。')
    assert first and not questions
    current = manager.workspace(workspace['id'])
    current['reports'].append({
        'id': 'report-parent', 'runId': 'run-parent', 'taskId': first['id'], 'title': first['title'],
        'createdAt': '2026-09-13T00:00:00Z', 'metrics': {'reviewed_rows': 1}, 'selectedIds': ['a-1'],
        'evidenceCount': 1, 'summary': '上一份用户可见的订单复核结论。',
    })

    followup, questions = manager.create_task(
        workspace['id'], '请补充上一份结论的风险说明。', followup_run_id='run-parent')
    assert followup and not questions
    stored = manager.task(followup['id'])
    assert followup['followupRunId'] == 'run-parent'
    assert stored['followupContext'] == {
        'parentRunId': 'run-parent', 'parentReportId': 'report-parent', 'title': first['title'],
        'metrics': {'reviewed_rows': 1}, 'selectedIds': ['a-1'], 'evidenceCount': 1,
        'summary': '上一份用户可见的订单复核结论。', 'summaryTruncated': False,
    }
    assert 'privateValidation' not in stored['followupContext']
    public_tasks = manager.public_workspace(workspace['id'])['tasks']
    public_followup = next(task for task in public_tasks if task['id'] == followup['id'])
    assert public_followup['followupRunId'] == 'run-parent'
    assert 'followupContext' not in public_followup
    with pytest.raises(ValueError, match='已保存的工作成果'):
        manager.create_task(workspace['id'], '尝试关联其他工作区运行。', followup_run_id='not-in-this-workspace')


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
                                      'count': 1, 'keys': ['o-1'], 'incompleteKeys': ['o-3'], 'truncated': False,
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
        'count': 2, 'keys': ['o-1', 'o-3'], 'incompleteKeys': [], 'truncated': False,
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


async def test_workspace_nonempty_count_ignores_null_and_blank_strings(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('support')
    manager.add_source(workspace['id'], 'narratives.json', json.dumps([
        {'complaint_id': 'c-1', 'narrative': 'detail'},
        {'complaint_id': 'c-2', 'narrative': '   '},
        {'complaint_id': 'c-3', 'narrative': None},
        {'complaint_id': 'c-4', 'narrative': 'second'},
    ]).encode())
    task, _ = manager.create_task(workspace['id'], '统计当前公开叙述。')
    table_id = manager.public_workspace(workspace['id'])['tables'][0]['id']
    tool = {tool.name: tool for tool in manager.tools(task['id'])}['workspace_aggregate_rows']
    context = type('Context', (), {'run': {'id': 'manual'}, 'evidence': set()})()

    result = await tool.execute({
        'tableId': table_id, 'operation': 'nonempty_count', 'field': 'narrative',
    }, context)

    assert result == {'nonemptyCount': 2, 'rowCount': 4}
    assert len(context.evidence) == 4


async def test_workspace_ordered_partition_uses_floor_prior_and_one_to_one_current_join(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('support')
    manager.add_source(workspace['id'], 'responses_dates.csv', b'complaint_id,date_received\nc-1,2024-01-01\nc-2,2024-01-02\nc-3,2024-01-03\nc-4,2024-01-04\nc-5,2024-01-05\n')
    manager.add_source(workspace['id'], 'complaints.csv', b'complaint_id,timely\nc-1,No\nc-2,Yes\nc-3,No\nc-4,Yes\nc-5,No\n')
    task, _ = manager.create_task(workspace['id'], '按日期比较两期投诉。')
    tables = {table['sheet']: table['id'] for table in manager.public_workspace(workspace['id'])['tables']}
    tool = {tool.name: tool for tool in manager.tools(task['id'])}['workspace_ordered_partition']
    context = type('Context', (), {'run': {'id': 'manual'}, 'evidence': set()})()

    result = await tool.execute({
        'primaryTableId': tables['responses_dates'], 'primaryKey': 'complaint_id', 'sortField': 'date_received',
        'relatedTableId': tables['complaints'], 'relatedKey': 'complaint_id',
        'measures': [
            {'name': 'prior_late_count', 'segment': 'prior', 'source': 'related',
             'filters': [{'field': 'timely', 'operator': 'equals', 'value': 'No'}]},
            {'name': 'current_late_count', 'segment': 'current', 'source': 'related',
             'filters': [{'field': 'timely', 'operator': 'equals', 'value': 'No'}]},
        ],
        'selectedIds': {'segment': 'current', 'source': 'related',
                        'filters': [{'field': 'timely', 'operator': 'equals', 'value': 'No'}]},
    }, context)

    assert result['totalCount'] == 5
    assert result['priorCount'] == 2 and result['currentCount'] == 3
    assert result['metricValues'] == {'prior_late_count': 1, 'current_late_count': 2}
    assert result['selectedIds'] == ['c-3', 'c-5']
    assert len(context.evidence) == 10


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
            prepared = await client.post(f'/api/workspaces/{workspace_id}/tasks', json={'request': '统计当前投诉渠道并形成内部复核简报。'})
            assert prepared.status_code == 201
            task_id = prepared.json()['task']['id']
            app.state.workspace_runner.runs['report-download'] = {
                'id': 'report-download', 'taskId': task_id, 'status': 'completed', 'events': [],
                'evaluation': {'status': 'user_review_required', 'issues': []},
                'submission': {'metrics': {'reviewed_rows': 1}, 'selectedIds': [], 'evidenceIds': [], 'summary': '基于当前上传资料形成内部复核简报。'},
            }
            downloaded = await client.get('/api/workspaces/runs/report-download/report/download')
            assert downloaded.status_code == 200
            assert downloaded.headers['content-type'].startswith('text/html')
            assert 'attachment; filename="operations-report-report-download.html"' == downloaded.headers['content-disposition']
            assert '内部复核简报' in downloaded.text
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


async def test_workspace_train_induces_receipts_and_matches_current_table_slots(tmp_path):
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
            if 'bind_trajectory' in names:
                data = json.loads(messages[-1]['content'])
                candidate = data['candidates'][0]
                return response('bind_trajectory', {'graphId': candidate['id'], 'decision': 'partial', 'nodeIds': [n['nodeId'] for n in candidate['descriptor']['operations']], 'bindings': [], 'reason': 'Injected schema compatibility protocol test', 'uncovered': ['current report']})
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
    assert first['evolution']['trajectoryCompilation']['sourceRunId'] == first['id']
    assert len(runner.evolution.versions) == 1
    g0 = runner.evolution.versions[0]

    second_task = manager.tasks[second_public['id']]
    expected.update(second_task['privateValidation'])
    second = await runner.start(TaskRunRequest(taskId=second_public['id'], strategy='graph_rsi'))
    await runner.tasks[second['id']]

    assert second['status'] == 'completed'
    assert second['evaluation']['status'] == 'passed'
    assert second['evolution']['planningPath'] == 'partial'
    assert second['evolution']['usedVersionId'] == g0['id']
    assert second['phaseMetrics']['plan']['requests'] == 0
    assert 'maintenanceError' not in second['evolution']
    bound_table_ids = {
        trace['arguments']['tableId'] for trace in second['toolTrace']
        if trace['executor'] == 'graph' and trace['tool'] == 'workspace_preview_rows'
    }
    assert bound_table_ids
    assert not bound_table_ids & set(first_task['tableBindings'].values())
    assert second['phaseMetrics']['match']['requests'] == 1
    assert not runner.evolution.tiny_edges
    assert len(runner.evolution.versions) == 1
    await runner.shutdown()


async def test_workspace_delivery_contract_stays_out_of_model_prompt_and_private_validation(tmp_path):
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
    assert '本次公开交付口径' not in model_text
    assert 'privateValidation' not in model_text
    assert 'requiredEvidenceIds' not in model_text
    contract_json = json.dumps(public_task['deliveryContract'], ensure_ascii=False, sort_keys=True)
    assert contract_json not in model_text
    assert 'requiredTableSlots' not in model_text
    assert run['evaluation']['status'] == 'passed'
    await runner.shutdown()


async def test_workspace_declared_fact_recovery_runs_once_without_reads_or_report_rewrite(tmp_path):
    bank = TaskBank()
    bank.load()
    manager = WorkspaceManager(tmp_path)
    _, public_task = install_workpack(manager, bank, 'support-policy-draft-01')
    internal = manager.task(public_task['id'])
    expected = internal['privateValidation']
    tables = manager.public_workspace(internal['workspaceId'])['tables']

    class FactRecoveryModel:
        model = 'fact-recovery-regression'
        settings = {}

        async def complete(self, messages, tools):
            prior_calls = [call for message in messages for call in message.get('tool_calls') or []]
            prior_names = {call['function']['name'] for call in prior_calls}
            if 'workspace_preview_rows' not in prior_names:
                return {
                    'message': {
                        'role': 'assistant', 'content': '读取当前资料。',
                        'tool_calls': [
                            {'id': 'preview-' + str(index), 'type': 'function', 'function': {
                                'name': 'workspace_preview_rows',
                                'arguments': json.dumps({'tableId': table['id'], 'page': 1, 'pageSize': 200}),
                            }}
                            for index, table in enumerate(tables, start=1)
                        ],
                    },
                    'usage': {'input': 4, 'output': 1}, 'finishReason': 'stop',
                }
            evidence = _evidence_from_messages(messages)
            runtime_fact_seen = any(
                str(message.get('tool_call_id') or '').startswith('facts_')
                for message in messages if message.get('role') == 'tool'
            )
            if 'workspace_publish_report' not in prior_names:
                metrics = dict(expected['metrics'])
                metrics['narrative_count'] += 1
                return response('workspace_publish_report', {
                    'metrics': metrics, 'selectedIds': expected['selectedIds'],
                    'evidenceIds': evidence, 'summary': '基于当前资料形成内部草稿。',
                })
            if runtime_fact_seen:
                return response('workspace_publish_report', {
                    'metrics': expected['metrics'], 'selectedIds': expected['selectedIds'],
                    'evidenceIds': evidence, 'summary': '依据当前观察与确定性统计修正内部草稿。',
                })
            return response()

    runner = TaskRunner(WorkspaceBank(manager), lambda _role: FactRecoveryModel(), learning_enabled=False,
                        run_directory=tmp_path / 'runs', evolution_path=tmp_path / 'experience.json')
    run = await runner.start(TaskRunRequest(taskId=public_task['id'], strategy='react'))
    await runner.tasks[run['id']]

    assert run['status'] == 'completed'
    assert run['evaluation']['status'] == 'passed'
    assert run['metrics']['reportAttempts'] == 2
    assert run['metrics']['failedReportAttempts'] == 1
    assert run['metrics']['deterministicFactRecoveryComputes'] == 1
    assert run['metrics']['deterministicFactRecoveryFailures'] == 0
    read_traces = [trace for trace in run['toolTrace'] if trace['effect'] == 'read']
    assert len(read_traces) == len(tables)
    assert all(trace['executor'] == 'model' for trace in read_traces)
    fact_traces = [trace for trace in run['toolTrace'] if trace['tool'] == 'workspace_aggregate_rows']
    assert len(fact_traces) == 1 and fact_traces[0]['executor'] == 'runtime' and fact_traces[0]['ok'] is True
    assert run['submission']['metrics'] == expected['metrics']
    await runner.shutdown()


async def test_workspace_deadline_guard_reserves_completed_scope_for_report(tmp_path, monkeypatch):
    import backend.task_runner as runner_module

    bank = TaskBank()
    bank.load()
    manager = WorkspaceManager(tmp_path)
    _, public_task = install_workpack(manager, bank, 'support-policy-draft-01')
    internal = manager.task(public_task['id'])
    expected = internal['privateValidation']
    tables = manager.public_workspace(internal['workspaceId'])['tables']
    monkeypatch.setattr(runner_module.config, 'RUN_TIMEOUT', .5)
    monkeypatch.setattr(runner_module.config, 'MODEL_TIMEOUT', .3)

    class DeadlineModel:
        model = 'deadline-guard-regression'
        settings = {}

        async def complete(self, messages, tools):
            prior_calls = [call for message in messages for call in message.get('tool_calls') or []]
            if not prior_calls:
                await asyncio.sleep(.24)
                return {
                    'message': {
                        'role': 'assistant', 'content': '读取完整公开范围。',
                        'tool_calls': [
                            {'id': 'preview-' + str(index), 'type': 'function', 'function': {
                                'name': 'workspace_preview_rows',
                                'arguments': json.dumps({'tableId': table['id'], 'page': 1, 'pageSize': 200}),
                            }}
                            for index, table in enumerate(tables, start=1)
                        ],
                    },
                    'usage': {'input': 4, 'output': 1}, 'finishReason': 'stop',
                }
            assert {tool.name for tool in tools} == {'workspace_publish_report'}
            return response('workspace_publish_report', {
                'metrics': expected['metrics'], 'selectedIds': expected['selectedIds'],
                'evidenceIds': _evidence_from_messages(messages), 'summary': '在当前证据范围内完成最终报告。',
            })

    runner = TaskRunner(WorkspaceBank(manager), lambda _role: DeadlineModel(), learning_enabled=False,
                        run_directory=tmp_path / 'runs', evolution_path=tmp_path / 'experience.json')
    run = await runner.start(TaskRunRequest(taskId=public_task['id'], strategy='react'))
    await runner.tasks[run['id']]

    assert run['status'] == 'completed'
    assert run['evaluation']['status'] == 'passed'
    assert run['metrics']['deadlineFinalizationGuards'] == 1
    assert not any(trace['tool'] == 'workspace_save_draft' for trace in run['toolTrace'])
    assert any(event['type'] == 'deadline_guard' for event in run['events'])
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


async def test_reconcile_tool_explains_text_keys_and_rejects_text_aggregate_fields(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = manager.create('finance')
    manager.add_source(workspace['id'], 'orders.csv', b'order_id\no-1\n')
    manager.add_source(workspace['id'], 'payments.csv', b'order_id,amount_cents\no-1,100\n')
    task, _ = manager.create_task(workspace['id'], '核对当前订单金额。')
    tables = {table['sheet']: table['id'] for table in manager.public_workspace(workspace['id'])['tables']}
    tool = {tool.name: tool for tool in manager.tools(task['id'])}['workspace_reconcile_keyed_sums']
    context = type('Context', (), {'run': {'id': 'manual'}, 'evidence': set()})()

    assert 'keyField 可以是文本业务 ID' in tool.description
    aggregate = tool.parameters['properties']['aggregates']['items']['properties']
    assert '完整数值列' in aggregate['field']['description']
    with pytest.raises(ValueError, match='keyField order_id 可以是文本业务 ID'):
        await tool.execute({
            'anchorTableId': tables['orders'], 'keyField': 'order_id',
            'aggregates': [{'tableId': tables['payments'], 'keyField': 'order_id', 'field': 'order_id', 'alias': 'bad'}],
        }, context)
