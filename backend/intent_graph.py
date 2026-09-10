"""Intent retrieval, model-selected read DAGs, and dependency-aware execution."""
from copy import deepcopy
import asyncio
import re
import networkx as nx
from .autotool import canonical, path_value
from .graph import ordered_nodes
from .tools import Tool, object_schema


def plan_tool():
    step = object_schema({'id': {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,30}$'},
                          'intent': {'type': 'string', 'minLength': 1, 'maxLength': 300},
                          'dependencies': {'type': 'array', 'uniqueItems': True, 'items': {'type': 'string'}}})
    return Tool('submit_plan', '提交数据获取子目标和依赖，独立的目标不互相依赖。', 'read',
                object_schema({'steps': {'type': 'array', 'minItems': 1, 'maxItems': 10, 'items': step}}), lambda args, ctx: args)


def validate_plan(plan):
    plan_tool().validator.validate(plan)
    steps = plan['steps']
    ids = [s['id'] for s in steps]
    if len(ids) != len(set(ids)) or any(dep not in ids for s in steps for dep in s['dependencies']):
        raise ValueError('Plan has duplicate IDs or missing dependencies')
    graph = nx.DiGraph()
    graph.add_nodes_from(ids)
    graph.add_edges_from((dep, s['id']) for s in steps for dep in s['dependencies'])
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError('Plan contains a dependency cycle')


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
        if required == {'page', 'pageSize'}:
            return 'list'
        if len(required) == 1 and next(iter(required)).endswith('Id'):
            return 'record'
        return 'unsupported'

    for key in nx.topological_sort(dag):
        rows = retrieval.get(key) or []
        candidates = [(row, known.get(row['name'])) for row in rows if row.get('score', 0) > 0]
        candidates = [(row, tool) for row, tool in candidates if tool and tool.effect == 'read' and signature(tool) != 'unsupported']
        list_ancestor = any(signature(known[selected[parent]]) == 'list' for parent in nx.ancestors(dag, key) if parent in selected)
        preferred = 'record' if list_ancestor else None
        eligible = [(row, tool) for row, tool in candidates if preferred is None or signature(tool) == preferred]
        if not eligible:
            eligible = candidates
        if not eligible:
            raise ValueError('No positive, compilable AutoTool candidate for ' + key)
        row, tool = eligible[0]
        selected[key] = tool.name
        diagnostics.append(dict(stepId=key, tool=tool.name, score=row['score'], candidateRank=rows.index(row) + 1,
                                signature=signature(tool), selection='local-retrieval-and-contract'))
    return {'nodes': [{'id': step['id'], 'tool': selected[step['id']]} for step in plan['steps']]}, diagnostics


def compile_intent_graph(plan, proposal, retrieval, tools):
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
        node.update(dependencies=steps[node['id']]['dependencies'], sourceEventSeqs=[])
        ignored = {'id', 'records', 'page', 'mayHaveMore', '_evidenceRef'}
        requested = {field for field in (tool.outputs or []) if field not in ignored and re.search(r'(?<![A-Za-z0-9_])' + re.escape(field) + r'(?![A-Za-z0-9_])', steps[node['id']]['intent'], re.I)}
        reusable = []
        for source in nx.ancestors(dag, node['id']):
            source_tool = known[selected[source]]
            if requested and requested.issubset(set(source_tool.outputs or [])):
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
    ordered_nodes(nodes, tools)
    return nodes


async def execute_graph(nodes, tools, invoke, on_node, on_elide=None):
    ordered_nodes(nodes, tools)
    dag = nx.DiGraph()
    dag.add_nodes_from(n['id'] for n in nodes)
    dag.add_edges_from((dep, n['id']) for n in nodes for dep in n['dependencies'])
    by_id, outputs = {n['id']: n for n in nodes}, {}

    async def execute(node):
        on_node(node['id'], 'running')
        try:
            if node.get('reuse'):
                source = outputs[node['reuse']['nodeId']]
                count = sum(len(path_value(page, node['reuse']['collectionPath'])) for page in source)
                outputs[node['id']] = source
                if on_elide:
                    on_elide(node['id'], count)
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
                if len(items) > 1000:
                    raise ValueError('Graph foreach exceeds 1000 records')
            arguments, seen = [], set()
            for item in items:
                args = {key: binding['value'] if binding['kind'] == 'literal' else path_value(item, binding['path']) for key, binding in node['arguments'].items()}
                signature = canonical(args)
                if signature not in seen:
                    arguments.append(args)
                    seen.add(signature)
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
