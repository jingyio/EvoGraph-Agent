"""Run-local, composable table computations. No task/gold/policy access.

Receipts refer to current computed views, never persisted business answers. Each
primitive exposes one operation; the caller chooses fields, joins and criteria.
"""
from copy import deepcopy
from datetime import datetime
import math
import re
from uuid import uuid4

from .tools import Tool, object_schema

INTERFACE = 'granular-compute-v1'
NAMES = {
    'workspace_map_fields', 'workspace_filter_mapped_rows',
    'workspace_restrict_to_keys', 'workspace_select_keys',
    'workspace_count_keyed', 'workspace_aggregate_keyed',
    'workspace_align_keyed', 'workspace_derive_values',
    'workspace_compare_values', 'workspace_select_missing',
    'workspace_compare_datetimes', 'workspace_select_invalid_datetimes',
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

    def publish_mapped(context, source, rows, restricted_to_keys=None):
        keys = sorted({row['key'] for row in rows})
        evidence = {key: deepcopy(source['evidenceByKey'].get(key, [])) for key in keys}
        data = {
            'kind': 'mapped_rows', 'rows': deepcopy(rows),
            'columns': deepcopy(source['columns']), 'evidenceByKey': evidence,
        }
        scope = restricted_to_keys
        if scope is None and 'restrictedToKeys' in source:
            scope = source['restrictedToKeys']
        if scope is not None:
            data['restrictedToKeys'] = sorted(set(scope))
        receipt = store(context, data)
        return {
            'receiptId': receipt, 'kind': 'mapped_rows', 'rowCount': len(rows),
            'keyCount': len(keys), 'columns': deepcopy(source['columns']),
            'preview': deepcopy(rows[:5]), 'truncated': len(rows) > 5,
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
            raise ValueError('keyField 是业务键，fields 仅放需要处理的当前字段')
        rows = []
        evidence = {}
        for row in table['rows']:
            raw_key = row['values'].get(args['keyField'])
            if raw_key is None or raw_key == '':
                raise ValueError('计算主键不能为空')
            key = str(raw_key)
            rows.append({'key': key, 'values': {field: row['values'].get(field) for field in args['fields']}})
            evidence.setdefault(key, []).append(f'workspace:{workspace_id}:{row["rowId"]}')
        manager._record_evidence(workspace_id, context, table['rows'])
        receipt = store(context, {
            'kind': 'mapped_rows', 'rows': rows,
            'columns': args['fields'], 'evidenceByKey': evidence,
        })
        return {
            'receiptId': receipt, 'kind': 'mapped_rows', 'rowCount': len(rows),
            'keyCount': len(evidence), 'columns': args['fields'],
            'types': {field: table['types'][field] for field in args['fields']},
            'preview': rows[:5], 'truncated': len(rows) > 5,
        }

    def empty(value):
        return value is None or (isinstance(value, str) and not value.strip())

    def matches(value, condition):
        operator = condition['operator']
        if operator == 'empty':
            return empty(value)
        if operator == 'nonempty':
            return not empty(value)
        if operator == 'zero':
            return not isinstance(value, bool) and isinstance(value, (int, float)) and value == 0
        expected = condition.get('value')
        if operator in {'equals', 'not_equals'}:
            matched = value == expected
            return matched if operator == 'equals' else not matched
        if operator == 'contains_token':
            if isinstance(value, list):
                tokens = [str(item).strip().lower() for item in value]
            else:
                tokens = [item.strip().lower() for item in re.split(r'[,;|]', str(value or ''))]
            return str(expected).strip().lower() in tokens
        if (isinstance(value, bool) or isinstance(expected, bool)
                or not isinstance(value, (int, float)) or not isinstance(expected, (int, float))
                or not math.isfinite(value) or not math.isfinite(expected)):
            raise ValueError('数值筛选要求当前字段和值都是有限数值')
        return {
            'gt': value > expected, 'gte': value >= expected,
            'lt': value < expected, 'lte': value <= expected,
        }[operator]

    def filter_mapped(args, context):
        source = load(context, args['receiptId'], 'mapped_rows')
        for condition in args['filters']:
            if condition['field'] not in source['columns']:
                raise ValueError('筛选字段不在映射收据中')
            if condition['operator'] not in {'empty', 'nonempty', 'zero'} and 'value' not in condition:
                raise ValueError('该筛选操作必须提供 value')
        rows = [row for row in source['rows'] if all(
            matches(row['values'].get(condition['field']), condition)
            for condition in args['filters']
        )]
        return publish_mapped(context, source, rows)

    def restrict(args, context):
        source = load(context, args['receiptId'])
        selected = load(context, args['keysReceiptId'])
        if source['kind'] not in {'mapped_rows', 'keyed_values'}:
            raise ValueError('待限制收据必须是映射行或键控数值')
        if selected['kind'] == 'finding':
            allowed = set(selected['keys'])
        elif selected['kind'] == 'mapped_rows':
            allowed = {row['key'] for row in selected['rows']}
        elif selected['kind'] == 'keyed_values':
            allowed = set(selected['perKey'])
        else:
            raise ValueError('键来源必须是 finding、筛选后映射行或键控数值收据')
        prior_scope = set(source['restrictedToKeys']) if 'restrictedToKeys' in source else None
        scope = allowed if prior_scope is None else prior_scope & allowed
        if source['kind'] == 'mapped_rows':
            return publish_mapped(
                context, source,
                [row for row in source['rows'] if row['key'] in allowed],
                restricted_to_keys=scope,
            )
        return publish(context, {
            'kind': 'keyed_values', 'columns': deepcopy(source['columns']),
            'perKey': {key: deepcopy(value) for key, value in source['perKey'].items() if key in allowed},
            'evidenceByKey': {key: deepcopy(value) for key, value in source['evidenceByKey'].items() if key in allowed},
            'restrictedToKeys': sorted(scope),
        })

    def count_keyed(args, context):
        source = load(context, args['receiptId'], 'mapped_rows')
        counts = {}
        for row in source['rows']:
            counts[row['key']] = counts.get(row['key'], 0) + 1
        data = {
            'kind': 'keyed_values', 'columns': [args['alias']],
            'perKey': {key: {args['alias']: value} for key, value in sorted(counts.items())},
            'evidenceByKey': source['evidenceByKey'],
        }
        if 'restrictedToKeys' in source:
            data['restrictedToKeys'] = deepcopy(source['restrictedToKeys'])
        return publish(context, data)

    def aggregate(args, context):
        source = load(context, args['receiptId'], 'mapped_rows')
        aliases = [measure['alias'] for measure in args['measures']]
        if len(set(aliases)) != len(aliases):
            raise ValueError('聚合别名必须唯一')
        if any(re.search(r'(^|_)count($|_)', alias.lower()) for alias in aliases):
            raise ValueError('键控数值聚合不产生记录计数；请使用 workspace_count_keyed')
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
                if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                       for value in values):
                    raise ValueError('聚合字段必须为完整有限数值列，缺失不得按零计算')
                output[measure['alias']] = {'sum': sum, 'max': max, 'min': min}[measure['operation']](values)
            per_key[key] = output
        data = {
            'kind': 'keyed_values', 'columns': aliases,
            'perKey': per_key, 'evidenceByKey': source['evidenceByKey'],
        }
        if 'restrictedToKeys' in source:
            data['restrictedToKeys'] = deepcopy(source['restrictedToKeys'])
        return publish(context, data)

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
        anchor_keys = set(per_key)
        columns = []
        restricted_input = False
        for receipt in args['receiptIds']:
            source = load(context, receipt, 'keyed_values')
            if 'restrictedToKeys' in source:
                restricted_input = True
                if not anchor_keys <= set(source['restrictedToKeys']):
                    raise ValueError(
                        '受限键控收据不能对齐到范围外主表业务键；'
                        '请使用未限制的全域收据，或保持相同业务键范围'
                    )
            if set(columns) & set(source['columns']):
                raise ValueError('关联收据的数值别名不能重叠')
            columns.extend(source['columns'])
            for key in per_key:
                per_key[key].update({name: source['perKey'].get(key, {}).get(name) for name in source['columns']})
                evidence[key].update(source['evidenceByKey'].get(key, []))
        manager._record_evidence(workspace_id, context, anchor['rows'])
        data = {
            'kind': 'keyed_values', 'columns': columns,
            'perKey': dict(sorted(per_key.items())),
            'evidenceByKey': {key: sorted(value) for key, value in evidence.items()},
        }
        if restricted_input:
            data['restrictedToKeys'] = sorted(anchor_keys)
        return publish(context, data, anchorRowCount=len(anchor['rows']))

    def derive(args, context):
        data = deepcopy(load(context, args['receiptId'], 'keyed_values'))
        for definition in args['totals']:
            name, aliases = definition['name'], definition['aliases']
            if name in data['columns'] or any(alias not in data['columns'] for alias in aliases):
                raise ValueError('派生别名不得重复；只能引用此前数值列')
            for row in data['perKey'].values():
                row[name] = None if any(row[alias] is None for alias in aliases) else sum(row[alias] for alias in aliases)
            data['columns'].append(name)
        return publish(context, data)

    def finding(context, source, name, keys, **extra):
        data = {
            'kind': 'finding', 'name': name, 'keys': keys,
            'evidenceByKey': {key: source['evidenceByKey'].get(key, []) for key in keys},
        }
        receipt = store(context, data)
        matching_totals = {}
        if source.get('kind') == 'keyed_values':
            matching_totals = {
                column: sum(source['perKey'][key][column] for key in keys
                            if source['perKey'][key][column] is not None)
                for column in source['columns']
            }
        return {
            'receiptId': receipt, 'kind': 'finding', 'name': name, 'count': len(keys),
            'selectedIds': keys[:max_rows], 'truncated': len(keys) > max_rows,
            'evidenceByKey': dict(list(data['evidenceByKey'].items())[:max_rows]),
            'matchingTotals': matching_totals, **extra,
        }

    def select_keys(args, context):
        source = load(context, args['receiptId'], 'mapped_rows')
        return finding(context, source, args['name'], sorted({row['key'] for row in source['rows']}))

    def compare(args, context):
        source = load(context, args['receiptId'], 'keyed_values')
        if isinstance(args['threshold'], bool) or not math.isfinite(args['threshold']):
            raise ValueError('比较阈值必须是有限数值')
        left, rights = args['leftAlias'], args.get('rightAliases', [])
        if any(column not in source['columns'] for column in [left, *rights]):
            raise ValueError('比较只能引用当前收据的数值别名')
        eligible, selected, incomplete = [], [], []
        for key, row in source['perKey'].items():
            if any(row[column] is None for column in [left, *rights]):
                incomplete.append(key)
                continue
            eligible.append(key)
            value = row[left] - sum(row[column] for column in rights)
            threshold, operator = args['threshold'], args['operator']
            matched = {
                'abs_gt': abs(value) > threshold, 'gt': value > threshold,
                'gte': value >= threshold, 'lt': value < threshold,
                'lte': value <= threshold, 'equals': value == threshold,
            }[operator]
            if matched:
                selected.append(key)
        return finding(context, source, args['name'], sorted(selected),
                       operator=args['operator'], threshold=args['threshold'],
                       incompleteKeys=sorted(incomplete), eligibleCount=len(eligible))

    def missing(args, context):
        source = load(context, args['receiptId'], 'keyed_values')
        if any(alias not in source['columns'] for alias in args['aliases']):
            raise ValueError('缺失检查只能引用当前收据的数值别名')
        keys = sorted(key for key, row in source['perKey'].items()
                      if any(row[alias] is None for alias in args['aliases']))
        return finding(context, source, args['name'], keys)

    def parse_datetime(value):
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            return None

    def datetime_rows(source, fields):
        start_field, end_field = fields
        if any(field not in source['columns'] for field in fields):
            raise ValueError('日期字段不在映射收据中')
        for row in source['rows']:
            yield row['key'], parse_datetime(row['values'].get(start_field)), parse_datetime(row['values'].get(end_field))

    def compare_datetimes(args, context):
        source = load(context, args['receiptId'], 'mapped_rows')
        if isinstance(args['thresholdHours'], bool) or not math.isfinite(args['thresholdHours']):
            raise ValueError('小时阈值必须是有限数值')
        selected, invalid = set(), set()
        for key, start, end in datetime_rows(source, args['fields']):
            if start is None or end is None or end < start:
                invalid.add(key)
                continue
            hours = (end - start).total_seconds() / 3600
            if {'gt': hours > args['thresholdHours'], 'gte': hours >= args['thresholdHours']}[args['operator']]:
                selected.add(key)
        return finding(context, source, args['name'], sorted(selected),
                       operator=args['operator'], thresholdHours=args['thresholdHours'],
                       incompleteKeys=sorted(invalid))

    def invalid_datetimes(args, context):
        source = load(context, args['receiptId'], 'mapped_rows')
        invalid = sorted({key for key, start, end in datetime_rows(source, args['fields'])
                          if start is None or end is None or end < start})
        return finding(context, source, args['name'], invalid)

    receipt = {'type': 'string', 'minLength': 1, 'description': '本次已成功工具返回的 receiptId，不是表ID或历史收据。'}
    label = {'type': 'string', 'minLength': 1, 'maxLength': 80}
    labels = {'type': 'array', 'minItems': 1, 'maxItems': 20, 'uniqueItems': True, 'items': label}
    operators = {'type': 'string', 'enum': ['abs_gt', 'gt', 'gte', 'lt', 'lte', 'equals']}
    row_filter = object_schema({
        'field': label,
        'operator': {'type': 'string', 'enum': [
            'equals', 'not_equals', 'empty', 'nonempty', 'zero',
            'contains_token', 'gt', 'gte', 'lt', 'lte',
        ]},
        'value': {},
    }, required=['field', 'operator'])
    return [
        Tool('workspace_distinct_values', '统计当前表一个字段的不同非空值数量，并返回每个值的记录数。适用于业务键数、月份数、渠道数等去重计数；distinctCount 不是表行数。', 'compute', object_schema({
            'tableId': table_schema, 'field': label,
        }), distinct, outputs=['distinctCount', 'values', 'counts', 'nonemptyCount', 'missingCount']),
        Tool('workspace_map_fields', '选择当前表的业务键和后续步骤所需字段，保留一对多行，返回映射收据 receiptId。字段可以是数值、文本、布尔值或日期字符串。', 'compute', object_schema({
            'tableId': table_schema, 'keyField': label, 'fields': labels,
        }), project, outputs=['receiptId', 'columns', 'rowCount', 'keyCount', 'preview']),
        Tool('workspace_filter_mapped_rows', '在映射收据上按显式字段条件筛选行，返回新的映射收据。empty/nonempty/zero 不需要 value；contains_token 按逗号、分号或竖线分隔后精确匹配。', 'compute', object_schema({
            'receiptId': receipt,
            'filters': {'type': 'array', 'minItems': 1, 'maxItems': 8, 'items': row_filter},
        }), filter_mapped, outputs=['receiptId', 'rowCount', 'keyCount', 'columns', 'preview']),
        Tool('workspace_restrict_to_keys', '按另一个收据中的业务键限制当前映射行或键控数值。键来源可直接使用筛选后的映射收据、finding 或键控数值收据；无需先额外转换。', 'compute', object_schema({
            'receiptId': {'type': 'string', 'minLength': 1, 'description': '要被限制的 mapped_rows 或 keyed_values receiptId。'},
            'keysReceiptId': {'type': 'string', 'minLength': 1, 'description': '提供保留业务键的 filtered mapped_rows、finding 或 keyed_values receiptId。'},
        }), restrict, outputs=['receiptId', 'kind', 'rowCount', 'keyCount', 'columns', 'preview', 'totals', 'perKey']),
        Tool('workspace_select_keys', '把映射收据中的不同业务键保存为独立 finding，返回清单、计数和当前证据。', 'compute', object_schema({
            'receiptId': receipt, 'name': label,
        }), select_keys, outputs=['receiptId', 'selectedIds', 'count', 'evidenceByKey']),
        Tool('workspace_count_keyed', '按映射收据的业务键统计当前行数并返回键控数值收据。适用于多笔记录数、关联存在性和活动行数。', 'compute', object_schema({
            'receiptId': receipt, 'alias': label,
        }), count_keyed, outputs=['receiptId', 'totals', 'perKey', 'keyCount', 'missingByAlias']),
        Tool('workspace_aggregate_keyed', '按映射收据的业务键聚合数值列，独立选择每列 sum/max/min 与别名；返回键控数值收据。记录计数使用 workspace_count_keyed。', 'compute', object_schema({
            'receiptId': receipt,
            'measures': {'type': 'array', 'minItems': 1, 'maxItems': 20, 'items': object_schema({
                'field': label, 'alias': label,
                'operation': {'type': 'string', 'enum': ['sum', 'max', 'min']},
            })},
        }), aggregate, outputs=['receiptId', 'totals', 'perKey', 'keyCount', 'missingByAlias']),
        Tool('workspace_align_keyed', '以当前主表业务键对齐多个键控数值收据；缺少关联保留 null，避免一对多金额放大。', 'compute', object_schema({
            'anchorTableId': table_schema, 'keyField': label,
            'receiptIds': {'type': 'array', 'minItems': 1, 'maxItems': 12, 'uniqueItems': True, 'items': receipt},
        }), align, outputs=['receiptId', 'totals', 'perKey', 'keyCount', 'missingByAlias']),
        Tool('workspace_derive_values', '从当前键控数值收据的显式别名相加得到派生列，任一来源缺失则结果 null。', 'compute', object_schema({
            'receiptId': receipt,
            'totals': {'type': 'array', 'minItems': 1, 'maxItems': 12, 'items': object_schema({
                'name': label, 'aliases': labels,
            })},
        }), derive, outputs=['receiptId', 'totals', 'perKey', 'keyCount', 'missingByAlias']),
        Tool('workspace_compare_values', '在当前数值收据上比较 leftAlias 减 rightAliases 之和与 threshold；abs_gt 比较绝对差。阈值使用字段原始单位。返回业务ID、计数和证据；缺失排除。', 'compute', object_schema({
            'receiptId': receipt, 'name': label, 'leftAlias': label,
            'rightAliases': {'type': 'array', 'maxItems': 20, 'items': label},
            'operator': operators, 'threshold': {'type': 'number'},
        }, required=['receiptId', 'name', 'leftAlias', 'operator', 'threshold']), compare,
             outputs=['receiptId', 'selectedIds', 'count', 'evidenceByKey', 'matchingTotals', 'incompleteKeys']),
        Tool('workspace_select_missing', '从当前数值收据选出指定别名任一缺失的业务对象，返回独立原因清单、计数与当前证据。', 'compute', object_schema({
            'receiptId': receipt, 'name': label, 'aliases': labels,
        }), missing, outputs=['receiptId', 'selectedIds', 'count', 'evidenceByKey']),
        Tool('workspace_compare_datetimes', '比较映射收据中两个 ISO 日期时间字段的小时差；缺失、无法解析或结束早于开始的记录不进入比较，并在 incompleteKeys 返回。', 'compute', object_schema({
            'receiptId': receipt, 'name': label,
            'fields': {'type': 'array', 'minItems': 2, 'maxItems': 2, 'items': label},
            'operator': {'type': 'string', 'enum': ['gt', 'gte']},
            'thresholdHours': {'type': 'number'},
        }), compare_datetimes,
             outputs=['receiptId', 'selectedIds', 'count', 'evidenceByKey', 'incompleteKeys']),
        Tool('workspace_select_invalid_datetimes', '选择两个 ISO 日期时间字段缺失、无法解析或结束早于开始的业务键，返回独立 finding。', 'compute', object_schema({
            'receiptId': receipt, 'name': label,
            'fields': {'type': 'array', 'minItems': 2, 'maxItems': 2, 'items': label},
        }), invalid_datetimes, outputs=['receiptId', 'selectedIds', 'count', 'evidenceByKey']),
    ]
