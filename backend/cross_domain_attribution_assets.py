"""Frozen 48-task, three-scenario asset for cross-task learning attribution.

The source rows come from the frozen trajectory V3-r3 asset. This adapter adds
the granular compute interface, public delivery-field semantics and concise
field-value definitions needed to bind categorical filters without hidden
defaults. Both attribution arms receive the same text and tools.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .graph_store import write_private
from .trajectory_assets_v3_r3 import VERSION as SOURCE_VERSION, build as build_source
from .workspace import WorkspaceManager


VERSION = 'cross-domain-rsi-attribution-v1-48'
ROLE_LABELS = {'finance': '财务', 'support': '客服', 'tickets': '技术工单'}
IDENTIFIERS = {'finance': 'order_id', 'support': 'complaint_id', 'tickets': 'issue_id'}
CAMPAIGN_STAGE1_POSITIONS = frozenset({1, 5, 10, 11})
CAMPAIGN_STAGE2_POSITIONS = frozenset({2, 6, 12, 16})
CAMPAIGN_STAGE3_POSITIONS = frozenset(range(1, 17)) - CAMPAIGN_STAGE1_POSITIONS - CAMPAIGN_STAGE2_POSITIONS
REQUIRED_TABLES = {
    ('finance', 'reconcile'): ('orders', 'payments', 'items'),
    ('finance', 'payment'): ('orders', 'payments'),
    ('support', 'timing'): ('complaints', 'responses'),
    ('support', 'coverage'): ('complaints', 'responses', 'narratives'),
    ('tickets', 'activity'): ('issues', 'activity'),
    ('tickets', 'readiness'): ('issues', 'activity'),
}
FIELD_VALUE_NOTES = {
    'finance': '资料字段口径：orders.status 中已取消记录的值为 canceled。',
    'support': '资料字段口径：complaints.timely 中不及时记录的值为 No。',
    'tickets': '资料字段口径：issues.state 中开放值为 open、关闭值为 closed；activity.labels 使用逗号分隔标签名。',
}

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
    'complaint_count': '当前投诉表中不同 complaint_id 的数量。',
    'company_count': '当前投诉表 company 的不同非空值数量。',
    'channel_count': '当前投诉表 submitted_via 的不同非空值数量。',
    'late_count': '当前资料中 timely 为 No 的投诉数。',
    'delayed_transfer_count': '受理到转交企业时长严格超过当前阈值的投诉数。',
    'date_review_count': '日期缺失、无法计算或前后倒置的投诉数。',
    'missing_public_response_count': '缺少 company_public_response 的投诉数。',
    'missing_company_response_count': '缺少 company_response 的投诉数。',
    'narrative_followup_count': '存在消费者叙述且缺公开响应的投诉数。',
    'missing_link_count': '投诉与响应资料无法按 complaint_id 对应的记录数。',
    'issue_count': '当前问题表中不同 issue_id 的数量。',
    'open_count': '当前资料中 state 为 open 的问题数。',
    'closed_count': '当前资料中 state 为 closed 的问题数。',
    'open_comment_total': '所有开放问题 comments 字段的合计。',
    'focus_count': '开放且评论数达到当前阈值的问题数。',
    'unassigned_focus_count': '重点问题中 assignee_count 为零的问题数。',
    'no_milestone_count': '开放且没有里程碑的问题数。',
    'unassigned_count': '开放且 assignee_count 为零的问题数。',
    'bug_label_count': '开放且 labels 包含精确 bug 标签的问题数。',
    'missing_activity_count': '问题与活动资料无法按 issue_id 对应的记录数。',
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _opportunity(spec: dict) -> str:
    position = int(spec.get('position') or 0)
    if position in {1, 9}:
        return 'create_cohort_experience'
    if position in {2, 10}:
        return 'first_reuse_or_revision'
    return 'continued_reuse_or_revision'


def campaign_plan(tasks: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    stage1 = [row for row in tasks if row.get('scenarioPosition') in CAMPAIGN_STAGE1_POSITIONS]
    stage2 = [row for row in tasks if row.get('scenarioPosition') in CAMPAIGN_STAGE2_POSITIONS]
    stage3 = [row for row in tasks if row.get('scenarioPosition') in CAMPAIGN_STAGE3_POSITIONS]
    if (len(stage1), len(stage2), len(stage3)) != (12, 12, 24):
        raise ValueError('跨场景展示 campaign 必须冻结12、12、24对的三个阶段')
    ordered_ids = [row['id'] for row in stage1 + stage2 + stage3]
    if len(ordered_ids) != 48 or len(set(ordered_ids)) != 48:
        raise ValueError('跨场景展示 campaign 必须包含48个唯一任务')
    stage_ids = [{row['id'] for row in stage} for stage in (stage1, stage2, stage3)]
    if any(stage_ids[left] & stage_ids[right] for left, right in ((0, 1), (0, 2), (1, 2))):
        raise ValueError('跨场景展示 campaign 三阶段任务不得重叠')
    if set().union(*stage_ids) != {row['id'] for row in tasks}:
        raise ValueError('跨场景展示 campaign 三阶段必须覆盖全部48对任务')
    selected = stage1 + stage2
    counts = {scenario: sum(row['scenario'] == scenario for row in selected) for scenario in ROLE_LABELS}
    if counts != {'finance': 8, 'support': 8, 'tickets': 8}:
        raise ValueError('跨场景展示 campaign 前24对必须在每个场景冻结8对任务')
    return stage1, stage2, stage3


def campaign_stages(tasks: list[dict]) -> tuple[list[dict], list[dict]]:
    stage1, stage2, _ = campaign_plan(tasks)
    return stage1, stage2


def verify_task_files(root: Path, spec: dict) -> None:
    directory = Path(root) / 'artifacts' / VERSION / spec['id']
    for filename, field in (('inputs.json', 'inputHash'), ('request.txt', 'requestHash'), ('private.json', 'scoreHash')):
        path = directory / filename
        if not path.is_file() or _sha(path) != spec.get(field):
            raise ValueError(f'冻结跨场景资产已变化：{spec["id"]}/{filename}')


def build(root: Path) -> dict:
    root = Path(root)
    source = build_source(root)
    source_root = root / 'artifacts' / SOURCE_VERSION
    output = root / 'artifacts' / VERSION
    tasks = [row for row in source['tasks'] if row.get('split') == 'train']
    manifest = {
        'version': VERSION,
        'sourceAssetVersion': SOURCE_VERSION,
        'taskDesignVersion': 'cross-domain-learning-attribution-v1',
        'taskCount': len(tasks),
        'taskOrderFrozen': True,
        'labelsOfflineOnly': True,
        'protocol': {
            'comparison': 'graph execution without cross-task learning vs the same graph execution with online learning',
            'modelRunsPerArm': len(tasks),
            'runModelReadLimits': [1, 1, 1],
            'order': 'same frozen task order per arm; pair arm order alternates',
            'scenarios': ['finance:16', 'support:16', 'tickets:16'],
            'cohorts': [
                'finance-reconciliation:8', 'finance-payment-health:8',
                'support-service-timing:8', 'support-response-coverage:8',
                'tickets-activity-triage:8', 'tickets-delivery-readiness:8',
            ],
            'precheckPairs': 12,
            'demoCampaignPairs': 24,
            'demoCampaignStage1Positions': sorted(CAMPAIGN_STAGE1_POSITIONS),
            'demoCampaignStage2Positions': sorted(CAMPAIGN_STAGE2_POSITIONS),
            'fullCampaignPairs': 48,
            'fullCampaignStage3Positions': sorted(CAMPAIGN_STAGE3_POSITIONS),
        },
        'tasks': [],
    }
    for sequence, source_spec in enumerate(tasks, 1):
        source_id = source_spec['id']
        source_dir = source_root / source_id
        task_dir = output / source_id
        task_dir.mkdir(parents=True, exist_ok=True)
        for name in ('inputs.json', 'private.json'):
            (task_dir / name).write_bytes((source_dir / name).read_bytes())
        # Preserve the frozen user-facing task verbatim. Public field-value
        # semantics belong to the runtime system context, not the business request.
        (task_dir / 'request.txt').write_bytes((source_dir / 'request.txt').read_bytes())
        expected = json.loads((task_dir / 'private.json').read_text())
        manifest['tasks'].append({
            **deepcopy(source_spec),
            'sourceTaskId': source_id,
            'sequence': sequence,
            'scenarioPosition': source_spec.get('position'),
            'position': sequence,
            'opportunity': _opportunity(source_spec),
            'campaignStage': (1 if source_spec.get('position') in CAMPAIGN_STAGE1_POSITIONS
                              else 2 if source_spec.get('position') in CAMPAIGN_STAGE2_POSITIONS
                              else 3),
            'sourceInputHash': source_spec.get('inputHash'),
            'sourceRequestHash': source_spec.get('requestHash'),
            'inputHash': _sha(task_dir / 'inputs.json'),
            'requestHash': _sha(task_dir / 'request.txt'),
            'scoreHash': _sha(task_dir / 'private.json'),
            'requiredMetricKeys': list(expected['metrics']),
            'requiredGroupNames': list(expected['groups']),
        })
    if len(manifest['tasks']) != 48:
        raise ValueError('跨场景归因资产必须恰好包含48个冻结train任务')
    campaign_plan(manifest['tasks'])
    write_private(output / 'manifest.json', manifest)
    write_private(root / 'benchmarks' / f'{VERSION}.json', manifest)
    return manifest


def install(manager: WorkspaceManager, root: Path, spec: dict):
    root = Path(root)
    verify_task_files(root, spec)
    directory = root / 'artifacts' / VERSION / spec['id']
    role = spec['scenario']
    workspace = manager.create(
        role,
        label=spec['title'],
        provenance=f'public_historical_{role}_cross_domain_attribution_v1',
    )
    manager.add_source(
        workspace['id'], 'inputs.json', (directory / 'inputs.json').read_bytes(),
        provenance={
            'source': f'{ROLE_LABELS[role]}公开历史资料；附件与题面复用自 {SOURCE_VERSION}/{spec["sourceTaskId"]}',
        },
    )
    answers = ({'policy_source': '仅输出不带政策依据的内部复核简报。'}
               if role == 'support' and spec.get('kind') == 'coverage' else None)
    task, questions = manager.create_task(
        workspace['id'], (directory / 'request.txt').read_text(), title=spec['title'],
        split='train', answers=answers,
    )
    if questions:
        raise ValueError(questions)
    internal = manager.tasks[task['id']]
    required_slots = REQUIRED_TABLES[(role, spec['kind'])]
    bindings = internal['tableBindings']
    required = sorted(
        f'workspace:{workspace["id"]}:{record["rowId"]}'
        for slot in required_slots
        for record in manager.workspace(workspace['id'])['tables'][bindings[slot]]['rows']
    )
    expected = json.loads((directory / 'private.json').read_text())
    missing_descriptions = [name for name in spec['requiredMetricKeys'] if name not in METRIC_DESCRIPTIONS]
    if missing_descriptions:
        raise ValueError(f'缺少公开指标语义：{missing_descriptions}')
    internal['computeInterface'] = 'granular-compute-v1'
    internal['publicScopeEvidenceIds'] = required
    internal['privateValidation'] = dict(expected, requiredEvidenceIds=required)
    internal['deliveryContract'] = {
        'requiredTableSlots': list(required_slots),
        'requiredMetricKeys': list(spec['requiredMetricKeys']),
        'metricDescriptions': {name: METRIC_DESCRIPTIONS[name] for name in spec['requiredMetricKeys']},
        'fieldValueNotes': FIELD_VALUE_NOTES[role],
        'requiredGroupNames': list(spec['requiredGroupNames']),
        'selectedIdField': IDENTIFIERS[role],
        'selectedIdPolicy': f'Machine selections use current {IDENTIFIERS[role]} values; top-level selectedIds is the deduplicated union of groups[].selectedIds; evidence uses current workspace row references.',
        'selectedIdsPolicy': 'union_of_groups',
        'evidenceScope': 'current attachment rows only',
    }
    manager._persist(manager.workspace(workspace['id']))
    return workspace, manager.public_task(task['id'])
