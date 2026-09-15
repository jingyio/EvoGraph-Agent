"""V3-r2 keeps public records but removes benchmark delivery language from task text."""
import json
import re

from backend.config import ROOT
from backend.trajectory_assets_v3_r2 import VERSION, build, install
from backend.workspace import WorkspaceManager


def test_v3_r2_keeps_source_records_and_builds_six_sequential_business_cohorts():
    revised = build(ROOT)
    original = json.loads((ROOT / 'benchmarks' / 'history' / 'trajectory-review-v3.json').read_text())
    original_by_id = {task['id']: task for task in original['tasks']}

    assert revised['version'] == VERSION
    assert [task['id'] for task in revised['tasks']] == [task['id'] for task in original['tasks']]
    assert all(task['recordIds'] == original_by_id[task['id']]['recordIds'] for task in revised['tasks'])
    train = [task for task in revised['tasks'] if task['split'] == 'train']
    cohorts = {}
    for task in train:
        cohorts.setdefault(task['cohort'], []).append(task)
    assert len(cohorts) == 6
    assert all(len(rows) == 8 for rows in cohorts.values())
    assert revised['protocol']['fastReuseMinimumRate'] == 0.5
    assert all(rows == sorted(rows, key=lambda task: task['position']) for rows in cohorts.values())


def test_v3_r2_user_prompts_are_business_requests_not_machine_delivery_sop(tmp_path):
    manifest = build(ROOT)
    forbidden = re.compile(r'\b(metrics|groups|selectedIds|evidenceIds|workspace_)\b', re.I)
    text_by_id = {}
    for spec in manifest['tasks']:
        text = (ROOT / 'artifacts' / VERSION / spec['id'] / 'request.txt').read_text()
        text_by_id[spec['id']] = text
        assert not forbidden.search(text)
        assert '不执行' in text or '不联系' in text or '不修改' in text
        assert '资料依据' in text

    finance = text_by_id['F01']
    assert '0.05 BRL' in finance and '8 期' in finance
    assert '待核查' in finance and '退款、改账' in finance
    manager = WorkspaceManager(tmp_path)
    spec = next(task for task in manifest['tasks'] if task['id'] == 'F01')
    _, public = install(manager, ROOT, spec)
    # The machine-checkable contract remains available to the report tool, not the user prompt.
    assert public['deliveryContract']['selectedIdField'] == 'order_id'
    assert public['deliveryContract']['requiredMetricKeys']
    assert not forbidden.search(public['task'])
