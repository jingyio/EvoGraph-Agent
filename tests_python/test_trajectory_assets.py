"""Task design checks only; no model or experiment execution."""
from collections import Counter

from backend.trajectory_assets import GROUPS, material, request_for, task_plan


def records(role):
    if role == 'finance':
        return [dict(id='o1', status='canceled', purchased_at='2026-01-01 00:00:00',
                     payments=[dict(sequence=1, method='card', installments=8, amount_cents=106),
                               dict(sequence=2, method='voucher', installments=1, amount_cents=1)],
                     items=[dict(sequence=1, price_cents=100, freight_cents=0)])]
    if role == 'support':
        return [dict(id='c1', company='A', product='P', issue='I', timely='No', submitted_via='Web',
                     company_response='', company_public_response='', narrative='consumer text',
                     date_received='2026-01-01T00:00:00Z', date_sent_to_company='2026-01-04T01:00:00Z')]
    return [dict(id='1', title='Bug', state='open', milestone=None, url='https://example.test/1', comments=5,
                 assignee_count=0, updated_at='2026-01-01T00:00:00Z', labels=['bug'])]


def test_v2_has_shared_six_contracts_and_frozen_48_train_plan():
    plan = task_plan()
    assert Counter(row['split'] for row in plan) == {'train': 48, 'validation': 6, 'test': 6}
    assert sum(row['precheck'] for row in plan) == 9
    assert sum(len(groups) for groups in GROUPS.values()) == 6
    assert len({(row['scenario'], row['group'], row['split'], row['position']) for row in plan}) == 60


def test_every_contract_builds_business_ids_and_matches_public_request():
    for role, groups in GROUPS.items():
        for group, _ in groups:
            tables, request, expected = material(role, group, records(role), 1)
            assert request == request_for(role, group, 1)
            assert tables and set(expected) == {'metrics', 'groups', 'selectedIds'}
            assert all(not value or value in (['o1'], ['c1'], ['1']) for value in expected['groups'].values())
            assert 'selectedIds 是各组业务ID' in request


def test_installed_task_exposes_exact_grouped_report_tool_contract(tmp_path):
    import json
    from backend.config import ROOT
    from backend.trajectory_assets import DELIVERY_CONTRACTS, install
    from backend.workspace import WorkspaceManager

    manifest = json.loads((ROOT / 'benchmarks/history/trajectory-review-v2.json').read_text())
    spec = next(task for task in manifest['tasks'] if task['id'] == 'finance-reconciliation-train-01')
    manager = WorkspaceManager(tmp_path)
    _, task = install(manager, ROOT, spec)
    public = manager.task(task['id'])['deliveryContract']
    metric_keys, group_names = DELIVERY_CONTRACTS[('finance', 'reconciliation')]
    assert public['requiredMetricKeys'] == metric_keys
    assert public['requiredGroupNames'] == group_names
    publish = next(tool for tool in manager.tools(task['id']) if tool.name == 'workspace_publish_report')
    assert 'groups' in publish.parameters['required']
    assert publish.parameters['properties']['metrics']['required'] == metric_keys
    assert publish.parameters['properties']['metrics']['additionalProperties'] is False
    assert publish.parameters['properties']['groups']['items']['properties']['name']['enum'] == group_names
