"""Frozen twelve-task finance asset for learning attribution.

The opportunity labels stay in the offline manifest. Runtime tasks contain only
the business request, current attachments, public delivery contract and private
validation used after report submission.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .graph_store import write_private
from .workspace import WorkspaceManager


VERSION = 'finance-rsi-attribution-v5-12'
SOURCE_VERSION = 'trajectory-review-v3-r3'

# The first eight instances stay inside one reconciliation cohort. The final
# four introduce the existing payment-health obligation and then repeat it.
# These labels describe the frozen audit opportunity only and never enter the
# task, model messages, matcher, or score.
TASKS = [
    {'id': 'FX01', 'sourceTaskId': 'F01', 'title': '订单财务复核 1', 'opportunity': 'create_reconciliation'},
    {'id': 'FX02', 'sourceTaskId': 'F02', 'title': '订单财务复核 2', 'opportunity': 'reuse_and_rebind'},
    {'id': 'FX03', 'sourceTaskId': 'F03', 'title': '订单财务复核 3', 'opportunity': 'continued_reuse'},
    {'id': 'FX04', 'sourceTaskId': 'F04', 'title': '订单财务复核 4', 'opportunity': 'amount_threshold_rebind'},
    {'id': 'FX05', 'sourceTaskId': 'F05', 'title': '订单财务复核 5', 'opportunity': 'continued_reuse'},
    {'id': 'FX06', 'sourceTaskId': 'F06', 'title': '订单财务复核 6', 'opportunity': 'installment_threshold_rebind'},
    {'id': 'FX07', 'sourceTaskId': 'F07', 'title': '订单财务复核 7', 'opportunity': 'sustained_reuse'},
    {'id': 'FX08', 'sourceTaskId': 'F08', 'title': '订单财务复核 8', 'opportunity': 'mixed_threshold_rebind'},
    {'id': 'FX09', 'sourceTaskId': 'F09', 'title': '支付结构健康复核 1', 'opportunity': 'coverage_extension'},
    {'id': 'FX10', 'sourceTaskId': 'F10', 'title': '支付结构健康复核 2', 'opportunity': 'use_extension'},
    {'id': 'FX11', 'sourceTaskId': 'F11', 'title': '支付结构健康复核 3', 'opportunity': 'continued_extension_reuse'},
    {'id': 'FX12', 'sourceTaskId': 'F12', 'title': '支付结构健康复核 4', 'opportunity': 'extension_threshold_rebind'},
]


# Public report-field semantics. Values and expected selections remain private;
# both experiment arms receive the same definitions through the report schema.
METRIC_DESCRIPTIONS = {
    'order_count': '当前订单表中不同 order_id 的数量。',
    'payment_record_count': '当前支付表的记录行数；多笔支付分别计数。',
    'paid_cents': '当前支付表 amount_cents 的总和，保持原始分单位。',
    'line_cents': '当前商品表 price_cents 与 freight_cents 的总和，保持原始分单位。',
    'period_count': '当前订单表 purchased_month 的不同非空值数量。',
    'difference_count': '支付总额与商品加运费总额满足当前差额条件的订单数。',
    'installments_count': '最大分期满足当前阈值条件的订单数。',
    'multiple_payment_count': '同一 order_id 在支付表中出现两行及以上的订单数。',
    'high_installment_count': '同一订单最大 installments 满足当前阈值的订单数。',
    'canceled_paid_count': '订单状态为 canceled 且存在至少一条支付记录的订单数。',
    'missing_payment_count': '订单表中存在但支付表中没有对应 order_id 的订单数。',
    'missing_items_count': '订单表中存在但商品表中没有对应 order_id 的订单数。',
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extended_expected(inputs: dict, expected: dict, enabled: bool) -> dict:
    """Compatibility helper retained for the frozen V4 protocol tests."""
    result = deepcopy(expected)
    if not enabled:
        return result
    status_ids = sorted(str(row['order_id']) for row in inputs['orders'] if row.get('status') != 'delivered')
    result['metrics']['status_review_count'] = len(status_ids)
    result['groups']['status_review'] = status_ids
    result['selectedIds'] = sorted(set(result['selectedIds']) | set(status_ids))
    return result


def build(root: Path) -> dict:
    root = Path(root)
    source_root = root / 'artifacts' / SOURCE_VERSION
    source_manifest_path = source_root / 'manifest.json'
    if not source_manifest_path.exists():
        raise ValueError('缺少已冻结的 V3-r3 财务来源资产')
    source_manifest = json.loads(source_manifest_path.read_text())
    source_by_id = {row['id']: row for row in source_manifest['tasks']}
    output = root / 'artifacts' / VERSION
    manifest = {
        'version': VERSION,
        'sourceAssetVersion': SOURCE_VERSION,
        'scenario': 'finance',
        'split': 'train',
        'taskCount': len(TASKS),
        'taskOrderFrozen': True,
        'labelsOfflineOnly': True,
        'protocol': {
            'comparison': 'graph execution without cross-task learning vs the same graph execution with online learning',
            'modelRunsPerArm': len(TASKS),
            'runModelReadLimits': [1, 1, 1],
            'order': 'same task order per arm; pair arm order alternates',
            'cohorts': ['finance-reconciliation:8', 'finance-payment-health:4'],
        },
        'tasks': [],
    }
    for index, row in enumerate(TASKS, 1):
        source = source_by_id.get(row['sourceTaskId'])
        if not source or source.get('scenario') != 'finance' or source.get('split') != 'train':
            raise ValueError('扩展归因任务引用了无效的财务 train 来源')
        source_dir = source_root / row['sourceTaskId']
        inputs_path = source_dir / 'inputs.json'
        request_path = source_dir / 'request.txt'
        private_path = source_dir / 'private.json'
        if _sha(inputs_path) != source['inputHash'] or _sha(request_path) != source['requestHash']:
            raise ValueError('扩展归因任务来源附件或题面摘要不一致')
        inputs = json.loads(inputs_path.read_text())
        request = request_path.read_text().strip()
        expected = json.loads(private_path.read_text())
        task_dir = output / row['id']
        write_private(task_dir / 'inputs.json', inputs)
        write_private(task_dir / 'request.txt', request + '\n')
        write_private(task_dir / 'private.json', expected)
        manifest['tasks'].append({
            **row,
            'position': index,
            'split': 'train',
            'scenario': 'finance',
            'cohort': source.get('cohort'),
            'recordIds': deepcopy(source['recordIds']),
            'sourceInputHash': source['inputHash'],
            'sourceRequestHash': source['requestHash'],
            'inputHash': _sha(task_dir / 'inputs.json'),
            'requestHash': _sha(task_dir / 'request.txt'),
            'scoreHash': _sha(task_dir / 'private.json'),
            'requiredMetricKeys': list(expected['metrics']),
            'requiredGroupNames': list(expected['groups']),
            'features': deepcopy(source['features']),
        })
    write_private(output / 'manifest.json', manifest)
    write_private(root / 'benchmarks' / f'{VERSION}.json', manifest)
    return manifest


def install(manager: WorkspaceManager, root: Path, spec: dict):
    directory = Path(root) / 'artifacts' / VERSION / spec['id']
    workspace = manager.create('finance', label=spec['title'], provenance='public_historical_finance_attribution_v5')
    manager.add_source(
        workspace['id'], 'inputs.json', (directory / 'inputs.json').read_bytes(),
        provenance={'source': f'Olist 公开历史记录；附件复用自 {SOURCE_VERSION}/{spec["sourceTaskId"]}；题面来自同一冻结资产'},
    )
    task, questions = manager.create_task(
        workspace['id'], (directory / 'request.txt').read_text(), title=spec['title'], split='train',
    )
    if questions:
        raise ValueError(questions)
    internal = manager.tasks[task['id']]
    required = sorted(
        f'workspace:{workspace["id"]}:{record["rowId"]}'
        for table in manager.workspace(workspace['id'])['tables'].values()
        for record in table['rows']
    )
    expected = json.loads((directory / 'private.json').read_text())
    internal['computeInterface'] = 'granular-compute-v1'
    internal['publicScopeEvidenceIds'] = required
    internal['privateValidation'] = dict(expected, requiredEvidenceIds=required)
    internal['deliveryContract'] = {
        'requiredTableSlots': list(internal['tableBindings']),
        'requiredMetricKeys': list(spec['requiredMetricKeys']),
        'metricDescriptions': {name: METRIC_DESCRIPTIONS[name] for name in spec['requiredMetricKeys']},
        'requiredGroupNames': list(spec['requiredGroupNames']),
        'selectedIdField': 'order_id',
        'selectedIdPolicy': 'Machine selections use current order_id values; evidence uses current workspace row references.',
        'evidenceScope': 'current attachment rows only',
    }
    manager._persist(manager.workspace(workspace['id']))
    return workspace, manager.public_task(task['id'])
