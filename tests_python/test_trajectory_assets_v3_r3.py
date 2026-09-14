"""V3-r3 keeps V3-r2 records while adding one auditable finance data definition."""
import hashlib
import json
import re

from backend.config import ROOT
from backend.trajectory_assets_v3_r2 import VERSION as R2_VERSION, build as build_r2
from backend.trajectory_assets_v3_r3 import VERSION, build, install
from backend.workspace import WorkspaceManager


FORBIDDEN = re.compile(r'\b(metrics|groups|selectedIds|evidenceIds|workspace_)\b', re.I)
FINANCE_DEFINITION = '本次以订单为复核单位；同一订单可对应多笔支付或商品明细，金额原始字段以分保存，报告按 BRL 展示。'


def test_v3_r3_preserves_r2_records_and_adds_only_the_concise_finance_data_definition():
    build_r2(ROOT)
    before = (ROOT / 'benchmarks' / f'{R2_VERSION}.json').read_bytes()
    revised = build(ROOT)
    original = json.loads(before)
    original_by_id = {task['id']: task for task in original['tasks']}

    assert revised['version'] == VERSION
    assert [task['id'] for task in revised['tasks']] == [task['id'] for task in original['tasks']]
    assert all(task['recordIds'] == original_by_id[task['id']]['recordIds'] for task in revised['tasks'])
    assert all(task['inputHash'] == original_by_id[task['id']]['inputHash'] for task in revised['tasks'])
    assert (ROOT / 'benchmarks' / f'{R2_VERSION}.json').read_bytes() == before

    for task in revised['tasks']:
        request = (ROOT / 'artifacts' / VERSION / task['id'] / 'request.txt').read_text()
        assert hashlib.sha256(request.encode()).hexdigest() == task['requestHash']
        assert not FORBIDDEN.search(request)
        if task['scenario'] == 'finance':
            assert request.count(FINANCE_DEFINITION) == 1
        else:
            old_request = (ROOT / 'artifacts' / R2_VERSION / task['id'] / 'request.txt').read_text()
            assert request == old_request


def test_v3_r3_keeps_machine_contract_out_of_the_model_prompt(tmp_path):
    manifest = build(ROOT)
    spec = next(task for task in manifest['tasks'] if task['id'] == 'F01')
    manager = WorkspaceManager(tmp_path)
    _, public = install(manager, ROOT, spec)

    assert FINANCE_DEFINITION in public['task']
    assert not FORBIDDEN.search(public['task'])
    assert public['deliveryContract']['selectedIdField'] == 'order_id'
    assert public['deliveryContract']['requiredMetricKeys']
