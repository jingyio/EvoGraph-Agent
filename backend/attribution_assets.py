"""Frozen six-task finance asset for learning attribution.

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


VERSION = 'finance-rsi-attribution-v4'
SOURCE_VERSION = 'trajectory-review-v3-r3'

TASKS = [
    {
        'id': 'FA01', 'sourceTaskId': 'F01', 'title': '订单财务复核 1',
        'opportunity': 'create',
        'request': '请基于本次附件完成订单财务复核，范围只限本次资料。重点标记支付总额与商品金额加运费总额相差严格超过 0.05 BRL、最大分期达到 8 期及以上，以及缺少支付或商品资料的订单。缺失资料不得按金额为零视为已对账。请给出整体汇总、需关注订单、原因、资料依据和简短内部建议。以订单为复核单位，同一订单可有多笔支付或商品明细；原始金额字段为分，报告按 BRL 展示。仅分析和生成本地报告，不执行退款或改账。',
    },
    {
        'id': 'FA02', 'sourceTaskId': 'F02', 'title': '订单财务复核 2',
        'opportunity': 'reuse_and_rebind',
        'request': '请检查本次附件中的订单对账情况。支付与商品加运费的总额差异严格超过 0.05 BRL、最大分期达到 10 期及以上，或任一侧资料缺失时，需要列入复核清单并保留独立原因。请汇总订单数和金额，附订单 ID、当前资料依据及内部建议。一个订单可以对应多笔支付和多条商品明细；金额原始单位为分，报告使用 BRL。只生成内部报告，不执行外部操作。',
    },
    {
        'id': 'FA03', 'sourceTaskId': 'F03', 'title': '订单财务与状态复核 1',
        'opportunity': 'coverage_extension',
        'request': '请基于本次附件完成订单财务与状态复核。分别列出支付总额与商品加运费总额相差严格超过 0.05 BRL、最大分期达到 8 期及以上、缺支付、缺商品，以及订单 status 不等于 delivered 的记录；原因可以重叠。请给出整体金额和订单汇总、各类清单、当前资料依据及内部建议。以订单为复核单位，一对多明细不得误删；原始金额为分，报告按 BRL 展示。仅生成本地报告，不修改订单或账务。',
    },
    {
        'id': 'FA04', 'sourceTaskId': 'F06', 'title': '订单财务与状态复核 2',
        'opportunity': 'use_revision',
        'request': '请复核本次附件中的订单金额、分期、资料完整性和交付状态。金额差异严格超过 0.05 BRL、最大分期达到 12 期及以上、缺支付、缺商品或 status 不等于 delivered 的订单均需独立列出并说明依据。请提供整体汇总、复核清单和简短内部建议。订单可有多笔支付和商品明细，原始金额单位为分，报告使用 BRL。只分析当前附件，不执行退款、改账或订单操作。',
    },
    {
        'id': 'FA05', 'sourceTaskId': 'F04', 'title': '订单财务与状态复核 3',
        'opportunity': 'continued_reuse',
        'request': '请形成当前附件的订单复核简报。需要分别检查支付与商品加运费的差异是否严格超过 0.10 BRL、最大分期是否达到 8 期、支付或商品资料是否缺失，以及 status 是否不等于 delivered。各类原因可重叠，空结果也应明确说明。请附整体金额、订单 ID、资料依据和内部建议。按订单汇总一对多明细，金额原始字段为分、报告按 BRL 展示；不得执行外部业务动作。',
    },
    {
        'id': 'FA06', 'sourceTaskId': 'F05', 'title': '订单复核交接简报',
        'opportunity': 'mixed_obligations',
        'request': '请为主管准备本次附件的订单复核交接简报。完整保留以下独立原因：支付与商品加运费差异严格超过 0.05 BRL、最大分期达到 10 期及以上、缺支付、缺商品、status 不等于 delivered。请汇总订单与金额，列出每类业务订单 ID 和当前资料依据，并给出简短处置建议；没有命中的类别也应明确说明。订单是一对多明细的复核主体，原始金额以分保存，报告使用 BRL。仅生成内部成果，不退款、不改账、不修改订单。',
    },
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extended_expected(inputs: dict, expected: dict, enabled: bool) -> dict:
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
        'taskCount': 6,
        'taskOrderFrozen': True,
        'labelsOfflineOnly': True,
        'protocol': {
            'comparison': 'graph execution without cross-task learning vs the same graph execution with online learning',
            'modelRunsPerArm': 6,
            'runModelReadLimits': [1, 1, 1],
            'order': 'same task order per arm; pair arm order alternates',
        },
        'tasks': [],
    }
    for index, row in enumerate(TASKS, 1):
        source = source_by_id.get(row['sourceTaskId'])
        if not source or source.get('scenario') != 'finance' or source.get('split') != 'train':
            raise ValueError('归因任务引用了无效的财务 train 来源')
        source_dir = source_root / row['sourceTaskId']
        inputs_path = source_dir / 'inputs.json'
        private_path = source_dir / 'private.json'
        if _sha(inputs_path) != source['inputHash']:
            raise ValueError('归因任务来源附件摘要不一致')
        inputs = json.loads(inputs_path.read_text())
        expected = _extended_expected(inputs, json.loads(private_path.read_text()), index >= 3)
        task_dir = output / row['id']
        write_private(task_dir / 'inputs.json', inputs)
        write_private(task_dir / 'request.txt', row['request'] + '\n')
        write_private(task_dir / 'private.json', expected)
        required_groups = list(expected['groups'])
        manifest['tasks'].append({
            **row,
            'position': index,
            'split': 'train',
            'scenario': 'finance',
            'recordIds': deepcopy(source['recordIds']),
            'sourceInputHash': source['inputHash'],
            'inputHash': _sha(task_dir / 'inputs.json'),
            'requestHash': _sha(task_dir / 'request.txt'),
            'scoreHash': _sha(task_dir / 'private.json'),
            'requiredMetricKeys': list(expected['metrics']),
            'requiredGroupNames': required_groups,
            'features': deepcopy(source['features']),
        })
    write_private(output / 'manifest.json', manifest)
    write_private(root / 'benchmarks' / f'{VERSION}.json', manifest)
    return manifest


def install(manager: WorkspaceManager, root: Path, spec: dict):
    directory = Path(root) / 'artifacts' / VERSION / spec['id']
    workspace = manager.create('finance', label=spec['title'], provenance='public_historical_finance_attribution_v4')
    manager.add_source(
        workspace['id'], 'inputs.json', (directory / 'inputs.json').read_bytes(),
        provenance={'source': f'Olist 公开历史记录；附件复用自 {SOURCE_VERSION}/{spec["sourceTaskId"]}；任务由项目编写'},
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
        'requiredGroupNames': list(spec['requiredGroupNames']),
        'selectedIdField': 'order_id',
        'selectedIdPolicy': 'Machine selections use current order_id values; evidence uses current workspace row references.',
        'evidenceScope': 'current attachment rows only',
    }
    manager._persist(manager.workspace(workspace['id']))
    return workspace, manager.public_task(task['id'])
