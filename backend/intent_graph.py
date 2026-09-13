"""Intent retrieval, locally selected read DAGs, and dependency-aware execution."""
from copy import deepcopy
import asyncio
import re
import networkx as nx
from .autotool import canonical, path_value
from .graph import ordered_nodes
from .tools import Tool, object_schema


def _terms(value):
    text = str(value).lower()
    words = set(re.findall(r'[a-z][a-z0-9_]*', text))
    # Taskbank tool outputs use stable English contract names while the task
    # instructions are Chinese. These aliases describe field semantics, not a
    # task-specific answer or record value.
    aliases = {
        'payments': '支付金额分期', 'items': '商品运费', 'reviews': '评价满意度',
        'labels': '标签', 'assignee_count': '负责人指派', 'milestone': '里程碑',
        'comments': '评论讨论', 'narrative': '叙述', 'timely': '及时',
    }
    for key, meaning in aliases.items():
        if key in text:
            text += ' ' + meaning
    for sequence in re.findall(r'[\u4e00-\u9fff]+', text):
        words.update(sequence[index:index + 2] for index in range(max(0, len(sequence) - 1)))
    return words


_GENERIC_TERMS = {'读取', '记录', '订单', '当前', '任务', '信息', '字段', '获取', '查看',
                  '返回', '列表', '全部', '每条', '数据', '结果', '明细', '本次', '工具', '状态'}


def _distinct_terms(value):
    return {term for term in _terms(value) if term not in _GENERIC_TERMS}


def _expects_list(intent):
    text = str(intent).lower()
    return bool(re.search(r'列表|列出|全部|每[条个]|records?|list', text))


def _capability_matches(intent, tool, role):
    """BM25 ranks candidates; this rejects candidates that cannot fulfill the step."""
    if role == 'list':
        return set(tool.parameters.get('required', [])) in ({'page', 'pageSize'}, {'tableId', 'page', 'pageSize'})
    meaningful = _distinct_terms(intent)
    capability = _distinct_terms(' '.join([tool.name, tool.description, *map(str, tool.outputs or [])]))
    return not meaningful or bool(meaningful & capability)


def prune_unrequested_steps(plan, task_text):
    """Drop independent detail requests whose semantic field is absent from the task.

    The model remains responsible for the Plan. This is a fail-closed compiler
    guard over an explicit task instruction: a list root is retained, while an
    unrelated detail branch is removed before tool selection. It never adds a
    tool, a condition, an ID, or an answer.
    """
    task_terms = _distinct_terms(task_text)
    kept, removed = [], []
    for step in plan['steps']:
        # A current-workspace ``sourceTable`` is an explicit schema-level
        # declaration from the Planner.  Word overlap cannot safely prove a
        # cross-table metric is unnecessary (for example a task can name a
        # business concept rather than the column that provides it).
        if step.get('sourceTable'):
            kept.append(deepcopy(step))
            continue
        terms = _distinct_terms(step.get('intent', ''))
        is_root = not step.get('dependencies')
        if not is_root and terms and not (terms & task_terms):
            removed.append(dict(id=step['id'], intent=step['intent'], reason='task_semantic_not_required'))
            continue
        kept.append(deepcopy(step))
    kept_ids = {step['id'] for step in kept}
    for step in kept:
        step['dependencies'] = [dep for dep in step['dependencies'] if dep in kept_ids]
        selection = step.get('selection')
        if selection and selection.get('kind') == 'match' and selection['sourceStepId'] not in kept_ids:
            raise ValueError('Task-relevance pruning removed a required selection source')
    result = dict(plan, steps=kept)
    validate_plan(result)
    return result, removed


def inclusive_task_constraints(task_text):
    """Return explicit inclusive constraints already stated by the task text.

    This describes comparison semantics only. It does not identify records,
    calculate metrics, or turn a model-only selection into a compiled filter.
    """
    seen, constraints = set(), []
    for phrase, value in re.findall(r'(至少|达到|不少于|不低于|大于等于)\s*(\d+)', task_text):
        key = (phrase, value)
        if key not in seen:
            seen.add(key)
            constraints.append(f'任务中的“{phrase} {value}”是包含式比较，必须按 >= {value} 解释，不能缩窄为等于 {value}。')
    return constraints


def reject_semantic_narrowing(plan, task_text):
    """Task text is authoritative when a Plan explicitly narrows an inclusive number condition."""
    inclusive = re.findall(r'(?:至少|达到|不少于|不低于|大于等于)\s*(\d+)', task_text)
    if not inclusive:
        return
    plan_text = ' '.join(str(step.get('intent', '')) for step in plan.get('steps', []))
    for value in inclusive:
        if re.search(rf'(?:为|等于|=)\s*{re.escape(value)}(?:\D|$)', plan_text) and not re.search(
                rf'(?:至少|达到|不少于|不低于|大于等于)\s*{re.escape(value)}', plan_text):
            raise ValueError('Plan explicitly narrows an inclusive task condition')


def plan_tool():
    selection = {
        'type': 'object',
        'properties': {
            'kind': {'type': 'string', 'enum': ['match', 'model']},
            'sourceStepId': {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,63}$'},
            'field': {'type': 'string', 'pattern': '^[A-Za-z][A-Za-z0-9_]{0,80}$'},
            'operator': {'type': 'string', 'enum': ['equals']},
            'value': {'type': ['string', 'integer', 'boolean', 'null']},
            'reason': {'type': 'string', 'minLength': 1, 'maxLength': 300},
        },
        'required': ['kind'],
        'additionalProperties': False,
    }
    step = object_schema({'id': {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,63}$'},
                          'intent': {'type': 'string', 'minLength': 1, 'maxLength': 300},
                          'dependencies': {'type': 'array', 'uniqueItems': True, 'items': {'type': 'string'}},
                          # A workspace table is a semantic slot such as
                          # ``orders``. The runtime maps it to only the
                          # current workspace's generated table ID.
                          'sourceTable': {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,50}$'},
                          # Some providers serialize an omitted optional field
                          # as JSON null.  Treat that exact encoding as absent
                          # at the runtime boundary; all non-null selections
                          # still receive the strict semantic validation below.
                          'selection': {'anyOf': [selection, {'type': 'null'}]}}, required=['id', 'intent', 'dependencies'])
    return Tool('submit_plan', '提交数据获取子目标和依赖，独立的目标不互相依赖。', 'read',
                object_schema({'steps': {'type': 'array', 'minItems': 1, 'maxItems': 10, 'items': step}}), lambda args, ctx: args)


def validate_plan(plan):
    plan_tool().validator.validate(plan)
    steps = plan['steps']
    ids = [s['id'] for s in steps]
    if len(ids) != len(set(ids)) or any(dep not in ids for s in steps for dep in s['dependencies']):
        raise ValueError('Plan has duplicate IDs or missing dependencies')
    for step in steps:
        selection = step.get('selection')
        if not selection:
            continue
        if selection['kind'] == 'match':
            if set(selection) != {'kind', 'sourceStepId', 'field', 'operator', 'value'}:
                raise ValueError('Plan match selection must bind one source field and literal value')
            if selection['sourceStepId'] not in step['dependencies']:
                raise ValueError('Plan match selection must depend on its source step')
        elif set(selection) != {'kind', 'reason'}:
            raise ValueError('Plan model selection must explain the handoff')
    graph = nx.DiGraph()
    graph.add_nodes_from(ids)
    graph.add_edges_from((dep, s['id']) for s in steps for dep in s['dependencies'])
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError('Plan contains a dependency cycle')


def normalize_optional_plan_fields(plan):
    """Remove provider null encodings for otherwise omitted optional fields.

    This is deliberately narrower than schema repair: only ``selection: null``
    becomes an omitted selection.  A malformed non-null selection still fails
    closed in ``validate_plan`` and cannot turn into a local graph filter.
    """
    normalized, removed = deepcopy(plan), []
    for step in normalized.get('steps') or []:
        if step.get('selection', object()) is None:
            step.pop('selection', None)
            removed.append(step.get('id'))
    return normalized, removed


def graph_tool(plan, retrieval):
    ids = [s['id'] for s in plan['steps']]
    node = object_schema({'id': {'type': 'string', 'enum': ids}, 'tool': {'type': 'string', 'enum': sorted({r['name'] for rows in retrieval.values() for r in rows})}})
    return Tool('submit_graph', '为每个 Plan 子目标选择一个召回工具。参数、分页和遍历由编译器绑定，不输出参数或记录 ID。', 'read',
                object_schema({'nodes': {'type': 'array', 'minItems': 1, 'maxItems': 10, 'items': node}}), lambda args, ctx: args)


def select_retrieved_graph(plan, retrieval, tools):
    """Choose graph tools locally from retrieval scores and compilable signatures."""
    validate_plan(plan)
    known = {tool.name: tool for tool in tools}
    dag = nx.DiGraph()
    dag.add_nodes_from(step['id'] for step in plan['steps'])
    dag.add_edges_from((dep, step['id']) for step in plan['steps'] for dep in step['dependencies'])
    selected, diagnostics = {}, []

    def signature(tool):
        required = set(tool.parameters['required'])
        if not required:
            return 'scope'
        if required in ({'page', 'pageSize'}, {'tableId', 'page', 'pageSize'}):
            return 'list'
        if len(required) == 1 and next(iter(required)).endswith('Id'):
            return 'record'
        return 'unsupported'

    for key in nx.topological_sort(dag):
        rows = retrieval.get(key) or []
        candidates = [(row, known.get(row['name'])) for row in rows if row.get('score', 0) > 0]
        candidates = [(row, tool) for row, tool in candidates if tool and tool.effect == 'read' and signature(tool) != 'unsupported']
        ancestors = nx.ancestors(dag, key)
        list_ancestor = any(signature(known[selected[parent]]) == 'list' for parent in ancestors if parent in selected)
        descendants = nx.descendants(dag, key)
        step = next(step for step in plan['steps'] if step['id'] == key)
        selection = step.get('selection') or {}
        selection_source = selection.get('sourceStepId')
        source_step = next((item for item in plan['steps'] if item['id'] == selection_source), None)
        # A same-table exact selection is a local view of its upstream list,
        # not a per-record detail lookup.  Preserve the generic list reader so
        # the compiler can reuse and filter the actual current observation.
        local_table_selection = bool(
            selection.get('kind') == 'match'
            and step.get('sourceTable')
            and source_step
            and source_step.get('sourceTable') == step.get('sourceTable')
        )
        # ``sourceTable`` is an explicit request to read rows from the current
        # workspace schema. Profiles and report indexes may rank higher in
        # lexical retrieval, but cannot supply row-level evidence or a graph
        # root. Require the paginated list signature before local selection.
        requires_list = _expects_list(step['intent']) or bool(descendants) or bool(step.get('sourceTable'))
        # A semantic workspace table slot always denotes a paginated table
        # read.  Dependency on an earlier table does not turn it into a
        # single-record lookup; cross-table joins remain explicit model/tool
        # work unless a later compiler rule can prove their binding.
        preferred = 'list' if step.get('sourceTable') or local_table_selection else 'record' if list_ancestor else 'list' if requires_list else None
        eligible = [(row, tool) for row, tool in candidates
                    if (preferred is None or signature(tool) == preferred)
                    and _capability_matches(step['intent'], tool, preferred or signature(tool))]
        if not eligible:
            raise ValueError('No positive, capability-compatible AutoTool candidate for ' + key)
        row, tool = eligible[0]
        selected[key] = tool.name
        diagnostics.append(dict(stepId=key, tool=tool.name, score=row['score'], candidateRank=rows.index(row) + 1,
                                signature=signature(tool), selection='local-retrieval-and-contract'))
    return {'nodes': [{'id': step['id'], 'tool': selected[step['id']]} for step in plan['steps']]}, diagnostics


def compile_intent_graph(plan, proposal, retrieval, tools, optimize=True):
    validate_plan(plan)
    graph_tool(plan, retrieval).validator.validate(proposal)
    steps = {s['id']: s for s in plan['steps']}
    nodes = deepcopy(proposal['nodes'])
    if len(nodes) != len(steps) or {n['id'] for n in nodes} != set(steps):
        raise ValueError('Graph must map every Plan step exactly once')
    known = {t.name: t for t in tools}
    dag = nx.DiGraph()
    dag.add_nodes_from(steps)
    dag.add_edges_from((dep, key) for key, step in steps.items() for dep in step['dependencies'])
    selected = {n['id']: n['tool'] for n in nodes}
    for node in nodes:
        if node['tool'] not in {r['name'] for r in retrieval[node['id']]}:
            raise ValueError('Selected tool was not retrieved for this intent')
        tool = known[node['tool']]
        if tool.effect != 'read':
            raise ValueError('Read graph cannot publish or write')
        required = set(tool.parameters.get('required', []))
        role = 'list' if required in ({'page', 'pageSize'}, {'tableId', 'page', 'pageSize'}) else 'record' if len(required) == 1 and next(iter(required)).endswith('Id') else 'scope'
        if not _capability_matches(steps[node['id']]['intent'], tool, role):
            raise ValueError('Selected tool does not satisfy requested output capability')
        node.update(dependencies=steps[node['id']]['dependencies'], sourceEventSeqs=[])
        ignored = {'id', 'records', 'page', 'mayHaveMore', '_evidenceRef'}
        requested = {field for field in (tool.outputs or []) if field not in ignored and re.search(r'(?<![A-Za-z0-9_])' + re.escape(field) + r'(?![A-Za-z0-9_])', steps[node['id']]['intent'], re.I)}
        reusable = []
        for source in nx.ancestors(dag, node['id']):
            source_tool = known[selected[source]]
            if (optimize and set(source_tool.parameters['required']) == {'page', 'pageSize'}
                    and len(tool.parameters['required']) == 1 and tool.parameters['required'][0].endswith('Id')
                    and requested and requested.issubset(set(source_tool.outputs or []))):
                reusable.append(source)
        if len(reusable) == 1:
            source = reusable[0]
            node['reuse'] = {'nodeId': source, 'collectionPath': ['records'], 'fields': sorted(requested)}
            node['dependencies'] = sorted(set(node['dependencies']) | {source})
            node['arguments'] = {}
            continue
        parameters = set(tool.parameters['required'])
        node['arguments'] = {}
        if parameters == {'page', 'pageSize'}:
            node['arguments'] = {'page': {'kind': 'literal', 'value': 1}, 'pageSize': {'kind': 'literal', 'value': 50}}
            node['paginate'] = {'maxPages': 20}
        elif parameters == {'tableId', 'page', 'pageSize'}:
            table = steps[node['id']].get('sourceTable')
            if not table:
                raise ValueError('Workspace table reads require a sourceTable from the current schema')
            node['arguments'] = {
                'tableId': {'kind': 'workspaceTable', 'table': table},
                'page': {'kind': 'literal', 'value': 1},
                'pageSize': {'kind': 'literal', 'value': 50},
            }
            node['paginate'] = {'maxPages': 20}
        elif len(parameters) == 1 and next(iter(parameters)).endswith('Id'):
            sources = [key for key in nx.ancestors(dag, node['id']) if set(known[selected[key]].parameters['required']) == {'page', 'pageSize'}]
            if len(sources) != 1:
                raise ValueError('Record binding requires one unambiguous upstream list')
            source = sources[0]
            node['arguments'] = {next(iter(parameters)): {'kind': 'item', 'path': ['id']}}
            node['foreach'] = {'nodeId': source, 'collectionPath': ['records']}
            node['dependencies'] = sorted(set(node['dependencies']) | {source})
        elif parameters:
            raise ValueError('No deterministic binding for this tool signature')
        selection = steps[node['id']].get('selection')
        if selection:
            if selection['kind'] == 'model':
                node['defer'] = True
            else:
                source = selection['sourceStepId']
                source_tool = known.get(selected.get(source))
                source_step = steps.get(source) or {}
                same_workspace_table = bool(
                    steps[node['id']].get('sourceTable')
                    and steps[node['id']].get('sourceTable') == source_step.get('sourceTable')
                    and set(tool.parameters.get('required', [])) == {'tableId', 'page', 'pageSize'}
                    and source_tool
                    and set(source_tool.parameters.get('required', [])) == {'tableId', 'page', 'pageSize'}
                )
                if same_workspace_table:
                    # The current schema slot is identical on both nodes.  A
                    # second preview would merely repeat the source read, so
                    # preserve a filtered view of that source instead.  The
                    # executor validates the field and type against current
                    # rows before applying the condition.
                    node['reuse'] = {
                        'nodeId': source,
                        'collectionPath': ['records'],
                        'fields': [selection['field']],
                        'filter': dict(field=selection['field'], operator=selection['operator'], value=deepcopy(selection['value'])),
                    }
                    node['dependencies'] = sorted(set(node['dependencies']) | {source})
                    node['arguments'] = {}
                    node.pop('paginate', None)
                    continue
                if (not node.get('foreach') or node['foreach']['nodeId'] != source or not source_tool
                        or selection['field'] not in set(source_tool.outputs or [])):
                    raise ValueError('Plan selection cannot be bound to a declared upstream list field')
                node['foreach']['filter'] = dict(field=selection['field'], operator=selection['operator'], value=deepcopy(selection['value']))
    # A model-only subgoal has no deterministic executable output.  Retain
    # any safe ancestors, but hand its whole dependency suffix back to the
    # model instead of letting a descendant consume an empty pseudo-result.
    deferred = {node['id'] for node in nodes if node.get('defer')}
    if deferred:
        for node in nodes:
            if any(parent in deferred for parent in nx.ancestors(dag, node['id'])):
                node['defer'] = True
    # Two model subgoals can resolve to the exact same current-data read. Keep
    # the first node and remap consumers rather than issuing duplicate calls.
    # This is based solely on executable structure, never record values.
    retained, aliases, fingerprints = [], {}, {}
    for node in nodes:
        fingerprint = canonical(dict(tool=node['tool'], arguments=node.get('arguments', {}), foreach=node.get('foreach'),
                                     paginate=node.get('paginate'), reuse=node.get('reuse'), defer=bool(node.get('defer'))))
        prior = fingerprints.get(fingerprint)
        if prior is None:
            fingerprints[fingerprint] = node['id']
            retained.append(node)
        else:
            aliases[node['id']] = prior
    if aliases:
        for node in retained:
            node['dependencies'] = sorted({aliases.get(dep, dep) for dep in node['dependencies'] if aliases.get(dep, dep) != node['id']})
            if node.get('foreach'):
                node['foreach']['nodeId'] = aliases.get(node['foreach']['nodeId'], node['foreach']['nodeId'])
            if node.get('reuse'):
                node['reuse']['nodeId'] = aliases.get(node['reuse']['nodeId'], node['reuse']['nodeId'])
        nodes = retained
    ordered_nodes(nodes, tools)
    return nodes


async def execute_graph(nodes, tools, invoke, on_node, on_elide=None, on_recovery=None, on_filter=None, on_binding=None):
    ordered_nodes(nodes, tools)
    dag = nx.DiGraph()
    dag.add_nodes_from(n['id'] for n in nodes)
    dag.add_edges_from((dep, n['id']) for n in nodes for dep in n['dependencies'])
    by_id, outputs = {n['id']: n for n in nodes}, {}

    async def execute(node):
        on_node(node['id'], 'running')
        try:
            if node.get('defer'):
                outputs[node['id']] = []
                on_node(node['id'], 'model-handoff')
                return
            if node.get('reuse'):
                from .graph import reuse_output
                values, count, filter_detail = await reuse_output(node, outputs, tools, invoke, on_recovery)
                outputs[node['id']] = values
                if on_elide:
                    on_elide(node['id'], count)
                if filter_detail and on_filter:
                    on_filter(node['id'], filter_detail)
                on_node(node['id'], 'reused')
                return
            items = [None]
            if node.get('foreach'):
                items = []
                for page in outputs[node['foreach']['nodeId']]:
                    rows = path_value(page, node['foreach']['collectionPath'])
                    if not isinstance(rows, list):
                        raise ValueError('Graph foreach source is not a list')
                    items.extend(rows)
                condition = node['foreach'].get('filter')
                if condition:
                    field, expected = condition['field'], condition['value']
                    if any(field not in row for row in items):
                        raise ValueError('Motif filter field missing from current list records')
                    if any(type(row[field]) is not type(expected) for row in items):
                        raise ValueError('Motif filter value type changed in current list records')
                    total = len(items)
                    items = [row for row in items if row[field] == expected]
                    if on_filter:
                        on_filter(node['id'], dict(sourceNodeId=node['foreach']['nodeId'], condition=deepcopy(condition),
                                                    totalRecords=total, selectedRecords=len(items), filteredOutRecords=total - len(items)))
                if len(items) > 1000:
                    raise ValueError('Graph foreach exceeds 1000 records')
            arguments, seen = [], set()
            binding_start = asyncio.get_running_loop().time()
            for item in items:
                args = {key: binding['value'] if binding['kind'] == 'literal' else path_value(item, binding['path']) for key, binding in node['arguments'].items()}
                signature = canonical(args)
                if signature not in seen:
                    arguments.append(args)
                    seen.add(signature)
            if on_binding:
                on_binding(node['id'], dict(argumentSets=len(arguments), bindingMs=round((asyncio.get_running_loop().time() - binding_start) * 1000, 3),
                                             emptyBranch=bool(node.get('foreach')) and not arguments))
            async def call(args):
                result_pages = []
                for page in range(1, node.get('paginate', {}).get('maxPages', 1) + 1):
                    result = await invoke(node['tool'], dict(args, page=page) if node.get('paginate') else args, node['id'])
                    result_pages.append(result)
                    if not node.get('paginate'):
                        return result_pages
                    if not isinstance(result, dict) or type(result.get('mayHaveMore')) is not bool:
                        raise ValueError('Pagination shape changed')
                    if not result['mayHaveMore']:
                        return result_pages
                raise ValueError('Graph pagination exhausted')
            results = await asyncio.gather(*(call(args) for args in arguments), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            outputs[node['id']] = [value for batch in results for value in batch]
            on_node(node['id'], 'done')
        except BaseException:
            on_node(node['id'], 'failed')
            raise
    for layer in nx.topological_generations(dag):
        results = await asyncio.gather(*(execute(by_id[key]) for key in layer), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
    return outputs
