"""Run-local, composable table computations. No task/gold/policy access.

Receipts refer to current computed views, never persisted business answers. Each
primitive exposes one operation; the caller chooses fields, joins and criteria.
"""
from copy import deepcopy
import math
import re
from uuid import uuid4

from .tools import Tool, object_schema

INTERFACE = 'granular-compute-v1'
NAMES = {
    'workspace_map_fields', 'workspace_aggregate_keyed', 'workspace_align_keyed',
    'workspace_derive_values', 'workspace_compare_values', 'workspace_select_missing',
    'workspace_distinct_values',
}


def tools_for(manager, workspace_id, table_schema, max_rows=200):
    def load(context, receipt_id, kind=None):
        receipt = context.computations.get(receipt_id)
        if not receipt or receipt['workspaceId'] != workspace_id:
            raise ValueError('计算收据不属于当前运行和工作区；必须引用此前成功工具返回的 receiptId')
        if kind and receipt['kind'] != kind:
            raise ValueError('上游收据类型不匹配')
        return receipt

    def store(context, data):
        key = 'receipt_' + str(uuid4())
        context.computations[key] = dict(deepcopy(data), workspaceId=workspace_id)
        return key

    def publish(context, data, **extra):
        key = store(context, data)
        values = data.get('perKey', {})
        missing = {name: [key for key, row in values.items() if row.get(name) is None]
                   for name in data.get('columns', [])}
        return {
            'receiptId': key, 'kind': data['kind'], 'keyCount': len(values),
            'columns': data.get('columns', []),
            'totals': {name: sum(row[name] for row in values.values() if row.get(name) is not None)
                       for name in data.get('columns', [])},
            'missingByAlias': missing,
            'perKey': dict(list(values.items())[:max_rows]),
            'truncated': len(values) > max_rows, **extra,
        }

    def distinct(args, context):
        table = manager.table(workspace_id, args['tableId'])
        manager._validate_field(table, args['field'])
        counts = {}
        missing = 0
        for row in table['rows']:
            value = row['values'].get(args['field'])
            if value is None or (isinstance(value, str) and not value.strip()):
                missing += 1
                continue
            key = str(value)
            counts[key] = counts.get(key, 0) + 1
        manager._record_evidence(workspace_id, context, table['rows'])
        values = sorted(counts)
        return {
            'field': args['field'],
            'distinctCount': len(values),
            'values': values[:max_rows],
            'counts': {key: counts[key] for key in values[:max_rows]},
            'nonemptyCount': sum(counts.values()),
            'missingCount': missing,
            'truncated': len(values) > max_rows,
        }

    def project(args, context):
        table = manager.table(workspace_id, args['tableId'])
        for field in [args['keyField'], *args['fields']]:
            manager._validate_field(table, field)
        if args['keyField'] in args['fields']:
            raise ValueError('keyField 是业务键，fields 仅放需要计算的数值字段')
        rows = []
        evidence = {}
        for row in table['rows']:
            raw_key = row['values'].get(args['keyField'])
            if raw_key is None or raw_key == '':
                raise ValueError('计算主键不能为空')
            key = str(raw_key)
            rows.append({'key': key, 'values': {f: row['values'].get(f) for f in args['fields']}})
            evidence.setdefault(key, []).append(f'workspace:{workspace_id}:{row["rowId"]}')
        manager._record_evidence(workspace_id, context, table['rows'])
        receipt = store(context, {'kind': 'mapped_rows', 'rows': rows, 'columns': args['fields'], 'evidenceByKey': evidence})
        return {'receiptId': receipt, 'kind': 'mapped_rows', 'rowCount': len(rows),
                'keyCount': len(evidence), 'columns': args['fields'],
                'types': {f: table['types'][f] for f in args['fields']},
                'preview': rows[:5], 'truncated': len(rows) > 5}

    def aggregate(args, context):
        source = load(context, args['receiptId'], 'mapped_rows')
        aliases = [m['alias'] for m in args['measures']]
        if len(set(aliases)) != len(aliases):
            raise ValueError('聚合别名必须唯一')
        if any(re.search(r'(^|_)count($|_)', alias.lower()) for alias in aliases):
            raise ValueError('键控数值聚合不产生记录计数；请使用映射收据的 rowCount、keyCount 或表行数计数工具')
        grouped = {}
        for row in source['rows']:
            grouped.setdefault(row['key'], []).append(row['values'])
        per_key = {}
        for key, rows in sorted(grouped.items()):
            output = {}
            for measure in args['measures']:
                if measure['field'] not in source['columns']:
                    raise ValueError('聚合字段不在映射收据中')
                values = [row.get(measure['field']) for row in rows]
                if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
                    raise ValueError('聚合字段必须为完整有限数值列，缺失不得按零计算')
                output[measure['alias']] = {'sum': sum, 'max': max, 'min': min}[measure['operation']](values)
            per_key[key] = output
        return publish(context, {'kind': 'keyed_values', 'columns': aliases,
                                'perKey': per_key, 'evidenceByKey': source['evidenceByKey']})

    def align(args, context):
        anchor = manager.table(workspace_id, args['anchorTableId'])
        manager._validate_field(anchor, args['keyField'])
        per_key, evidence = {}, {}
        for row in anchor['rows']:
            raw_key = row['values'].get(args['keyField'])
            if raw_key is None or raw_key == '':
                raise ValueError('主表业务键不能为空')
            key = str(raw_key)
            per_key.setdefault(key, {})
            evidence.setdefault(key, set()).add(f'workspace:{workspace_id}:{row["rowId"]}')
        columns = []
        for receipt in args['receiptIds']:
            source = load(context, receipt, 'keyed_values')
            if set(columns) & set(source['columns']):
                raise ValueError('关联收据的数值别名不能重叠')
            columns.extend(source['columns'])
            for key in per_key:
                per_key[key].update({name: source['perKey'].get(key, {}).get(name) for name in source['columns']})
                evidence[key].update(source['evidenceByKey'].get(key, []))
        manager._record_evidence(workspace_id, context, anchor['rows'])
        return publish(context, {'kind': 'keyed_values', 'columns': columns,
                                'perKey': dict(sorted(per_key.items())),
                                'evidenceByKey': {k: sorted(v) for k, v in evidence.items()}},
                       anchorRowCount=len(anchor['rows']))

    def derive(args, context):
        data = deepcopy(load(context, args['receiptId'], 'keyed_values'))
        for definition in args['totals']:
            name, aliases = definition['name'], definition['aliases']
            if name in data['columns'] or any(alias not in data['columns'] for alias in aliases):
                raise ValueError('派生别名不得重复；只能引用此前数值列')
            for row in data['perKey'].values():
                row[name] = None if any(row[alias] is None for alias in aliases) else sum(row[a] for a in aliases)
            data['columns'].append(name)
        return publish(context, data)

    def finding(context, source, name, keys, **extra):
        data = {'kind': 'finding', 'name': name, 'keys': keys,
                'evidenceByKey': {k: source['evidenceByKey'].get(k, []) for k in keys}}
        receipt = store(context, data)
        return {'receiptId': receipt, 'kind': 'finding', 'name': name, 'count': len(keys),
                'selectedIds': keys[:max_rows], 'truncated': len(keys) > max_rows,
                'evidenceByKey': dict(list(data['evidenceByKey'].items())[:max_rows]),
                'matchingTotals': {col: sum(source['perKey'][k][col] for k in keys if source['perKey'][k][col] is not None)
                                   for col in source['columns']}, **extra}

    def compare(args, context):
        source = load(context, args['receiptId'], 'keyed_values')
        if isinstance(args['threshold'], bool) or not math.isfinite(args['threshold']):
            raise ValueError('比较阈值必须是有限数值')
        left, rights = args['leftAlias'], args.get('rightAliases', [])
        if any(col not in source['columns'] for col in [left, *rights]):
            raise ValueError('比较只能引用当前收据的数值别名')
        eligible, selected, incomplete = [], [], []
        for key, row in source['perKey'].items():
            if any(row[col] is None for col in [left, *rights]):
                incomplete.append(key); continue
            eligible.append(key)
            value = row[left] - sum(row[col] for col in rights)
            t, op = args['threshold'], args['operator']
            match = {'abs_gt': abs(value) > t, 'gt': value > t, 'gte': value >= t,
                     'lt': value < t, 'lte': value <= t, 'equals': value == t}[op]
            if match: selected.append(key)
        return finding(context, source, args['name'], sorted(selected),
                       operator=args['operator'], threshold=args['threshold'],
                       incompleteKeys=sorted(incomplete), eligibleCount=len(eligible))

    def missing(args, context):
        source = load(context, args['receiptId'], 'keyed_values')
        if any(a not in source['columns'] for a in args['aliases']):
            raise ValueError('缺失检查只能引用当前收据的数值别名')
        keys = sorted(key for key, row in source['perKey'].items() if any(row[a] is None for a in args['aliases']))
        return finding(context, source, args['name'], keys)

    receipt = {'type': 'string', 'minLength': 1, 'description': '本次已成功工具返回的 receiptId，不是表ID或历史收据。'}
    label = {'type': 'string', 'minLength': 1, 'maxLength': 80}
    labels = {'type': 'array', 'minItems': 1, 'maxItems': 20, 'uniqueItems': True, 'items': label}
    operators = {'type': 'string', 'enum': ['abs_gt', 'gt', 'gte', 'lt', 'lte', 'equals']}
    return [
        Tool('workspace_distinct_values', '统计当前表一个字段的不同非空值数量，并返回每个值的记录数。适用于月份数、渠道数等去重计数；distinctCount 不是表行数。', 'compute', object_schema({
            'tableId': table_schema, 'field': label}), distinct,
             outputs=['distinctCount', 'values', 'counts', 'nonemptyCount', 'missingCount']),
        Tool('workspace_map_fields', '选择当前表的业务键和需计算字段，保留一对多行，返回映射收据 receiptId。', 'compute', object_schema({
            'tableId': table_schema, 'keyField': label, 'fields': labels}), project,
             outputs=['receiptId', 'columns', 'rowCount', 'keyCount', 'preview']),
        Tool('workspace_aggregate_keyed', '按映射收据的业务键聚合数值列，独立选择每列 sum/max/min 与别名；返回键控数值收据。它不统计记录数，行数使用映射收据的 rowCount，业务键数使用 keyCount。', 'compute', object_schema({
            'receiptId': receipt, 'measures': {'type': 'array', 'minItems': 1, 'maxItems': 20, 'items': object_schema({
                'field': label, 'alias': label, 'operation': {'type': 'string', 'enum': ['sum', 'max', 'min']}})}}), aggregate,
             outputs=['receiptId', 'totals', 'perKey', 'keyCount', 'missingByAlias']),
        Tool('workspace_align_keyed', '以当前主表业务键对齐多个键控数值收据；缺少关联保留 null，避免一对多金额放大。', 'compute', object_schema({
            'anchorTableId': table_schema, 'keyField': label,
            'receiptIds': {'type': 'array', 'minItems': 1, 'maxItems': 12, 'uniqueItems': True, 'items': receipt}}), align,
             outputs=['receiptId', 'totals', 'perKey', 'keyCount', 'missingByAlias']),
        Tool('workspace_derive_values', '从当前键控数值收据的显式别名相加得到派生列，任一来源缺失则结果 null。', 'compute', object_schema({
            'receiptId': receipt, 'totals': {'type': 'array', 'minItems': 1, 'maxItems': 12, 'items': object_schema({
                'name': label, 'aliases': labels})}}), derive,
             outputs=['receiptId', 'totals', 'perKey', 'keyCount', 'missingByAlias']),
        Tool('workspace_compare_values', '在当前数值收据上比较 leftAlias 减 rightAliases 之和与 threshold；abs_gt 比较绝对差。阈值必须为字段原始单位，由当前模型核对转换。返回业务ID清单、计数和证据；缺失排除。', 'compute', object_schema({
            'receiptId': receipt, 'name': label, 'leftAlias': label,
            'rightAliases': {'type': 'array', 'maxItems': 20, 'items': label},
            'operator': operators, 'threshold': {'type': 'number'}}, required=['receiptId', 'name', 'leftAlias', 'operator', 'threshold']), compare,
             outputs=['receiptId', 'selectedIds', 'count', 'evidenceByKey', 'matchingTotals', 'incompleteKeys']),
        Tool('workspace_select_missing', '从当前数值收据选出指定别名任一缺失的业务对象，返回独立原因清单、计数与当前证据。', 'compute', object_schema({
            'receiptId': receipt, 'name': label, 'aliases': labels}), missing,
             outputs=['receiptId', 'selectedIds', 'count', 'evidenceByKey']),
    ]
