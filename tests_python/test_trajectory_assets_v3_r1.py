"""V3-r1 preserves the reviewed task corpus and clarifies only public ID semantics."""
import json

from backend.config import ROOT
from backend.trajectory_assets_v3_r1 import VERSION, build, install
from backend.workspace import WorkspaceManager


def test_v3_r1_preserves_record_selection_and_exposes_business_id_contract():
    revised = build(ROOT)
    original = json.loads((ROOT / 'benchmarks' / 'history' / 'trajectory-review-v3.json').read_text())
    original_by_id = {task['id']: task for task in original['tasks']}

    assert revised['version'] == VERSION
    assert [task['id'] for task in revised['tasks']] == [task['id'] for task in original['tasks']]
    assert all(task['recordIds'] == original_by_id[task['id']]['recordIds'] for task in revised['tasks'])

    spec = next(task for task in revised['tasks'] if task['id'] == 'F01')
    manager = WorkspaceManager(ROOT / 'artifacts' / 'test-v3-r1-contract')
    _, task = install(manager, ROOT, spec)
    assert task['deliveryContract']['selectedIdField'] == 'order_id'
    assert task['deliveryContract']['selectedIdPolicy'].startswith('selectedIds')
    assert '业务ID字段为 order_id' in task['task']
    assert 'workspace_' not in task['task'] and 'F01' not in task['task']
