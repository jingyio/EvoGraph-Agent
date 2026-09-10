"""Bounded Persistent TinyEdge mining and deterministic composition for read DAGs."""
from copy import deepcopy
import hashlib
import json
import re
import networkx as nx
from .graph import ordered_nodes, contract_hash


CANONICAL_VERSION = 'rsi-read-tinyedge-v1'
MIN_SUPPORT = 2
MAX_LENGTH = 3


def stable(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def identity(value):
    return hashlib.sha256(stable(value).encode()).hexdigest()


def grams(value):
    compact = ''.join(c for c in str(value).lower() if c.isalnum())
    return {compact[index:index + 2] for index in range(max(0, len(compact) - 1))}


def _slot(binding):
    if binding['kind'] == 'literal':
        value = binding['value']
        return {'kind': 'literal', 'type': type(value).__name__, 'value': value if type(value) not in (dict, list) else stable(value)}
    return {'kind': binding['kind'], 'path': list(binding['path'])}


def canonical_node(node, tool):
    """Identity excludes source IDs while retaining executable binding contracts."""
    output = sorted(str(item) for item in (tool.outputs or []))
    foreach = node.get('foreach') or {}
    reuse = node.get('reuse') or {}
    return {
        'tool': node['tool'],
        'parameters': tool.parameters,
        'outputs': output,
        'arguments': {key: _slot(value) for key, value in sorted(node['arguments'].items())},
        'foreach': ({'collectionPath': foreach['collectionPath'], 'filter': deepcopy(foreach.get('filter'))} if foreach else None),
        'paginate': deepcopy(node.get('paginate')),
        'reuse': ({'collectionPath': reuse['collectionPath'], 'fields': sorted(reuse['fields']), 'onMissing': reuse.get('onMissing')} if reuse else None),
    }


def _linear_chains(nodes, tools):
    """Never mine across defer, fan-in, fan-out, or non-contiguous dependencies."""
    ordered = ordered_nodes(nodes, tools)
    by_id = {node['id']: node for node in ordered}
    graph = nx.DiGraph()
    graph.add_nodes_from(by_id)
    graph.add_edges_from((dep, node['id']) for node in ordered for dep in node['dependencies'])
    executable = {key for key, node in by_id.items() if not node.get('defer')}
    chains, visited = [], set()
    for key in graph.nodes:
        if key not in executable or key in visited:
            continue
        predecessors = [item for item in graph.predecessors(key) if item in executable]
        if len(predecessors) == 1 and len([item for item in graph.successors(predecessors[0]) if item in executable]) == 1:
            continue
        chain, current = [key], key
        while True:
            successors = [item for item in graph.successors(current) if item in executable]
            if len(successors) != 1:
                break
            following = successors[0]
            incoming = [item for item in graph.predecessors(following) if item in executable]
            if len(incoming) != 1 or following in chain:
                break
            chain.append(following)
            current = following
        visited.update(chain)
        chains.append(chain)
    return [[by_id[key] for key in chain] for chain in chains]


def extract_fragments(nodes, plan, tools):
    known = {tool.name: tool for tool in tools}
    intents = {step['id']: step['intent'] for step in plan.get('steps', [])}
    fragments = {}
    for chain in _linear_chains(nodes, tools):
        for length in range(1, min(MAX_LENGTH, len(chain)) + 1):
            for start in range(0, len(chain) - length + 1):
                templates = deepcopy(chain[start:start + length])
                canonical = [canonical_node(node, known[node['tool']]) for node in templates]
                signature = identity({'version': CANONICAL_VERSION, 'nodes': canonical})
                fragments.setdefault(signature, dict(
                    id='tiny_' + signature[:20], signature=signature, canonicalNodes=canonical,
                    nodeTemplates=templates, planStepIds=[node['id'] for node in templates],
                    intent='；'.join(str(intents.get(node['id']) or node['tool']) for node in templates),
                    inputSlots=sorted({key for node in canonical for key, value in node['arguments'].items() if value['kind'] != 'literal'}),
                    outputSlots=sorted({field for node in canonical for field in node['outputs']}),
                    length=length,
                ))
    return fragments


def mine(workflows, tools):
    """Materialize frequent, closed, executable fragments from train workflows."""
    known = {tool.name: tool for tool in tools}
    grouped = {}
    for workflow in workflows:
        fragments = extract_fragments(workflow['nodes'], workflow['plan'], tools)
        for signature, fragment in fragments.items():
            key = (workflow['scenario'], workflow['contractHash'], signature)
            record = grouped.setdefault(key, dict(fragment, scenario=workflow['scenario'], contractHash=workflow['contractHash'],
                                                  sourceWorkflowIds=set(), sourceRunIds=set(), sources=[]))
            record['sourceWorkflowIds'].add(workflow['id'])
            record['sourceRunIds'].add(workflow['sourceRunId'])
            record['sources'].append(dict(workflowId=workflow['id'], runId=workflow['sourceRunId'], taskId=workflow['sourceTaskId'], family=workflow['family']))
    materialized = []
    for _, candidate in grouped.items():
        support = len(candidate['sourceWorkflowIds'])
        if support < MIN_SUPPORT:
            continue
        closed = not any(
            len(other['canonicalNodes']) > len(candidate['canonicalNodes'])
            and other['sourceWorkflowIds'] == candidate['sourceWorkflowIds']
            and any(other['canonicalNodes'][index:index + len(candidate['canonicalNodes'])] == candidate['canonicalNodes']
                    for index in range(len(other['canonicalNodes']) - len(candidate['canonicalNodes']) + 1))
            for other in grouped.values()
        )
        executable = all(node['tool'] in known and known[node['tool']].effect == 'read' for node in candidate['nodeTemplates'])
        if not closed or not executable:
            continue
        item = deepcopy(candidate)
        item.update(support=support, closed=True, executable=True,
                    sourceWorkflowIds=sorted(item['sourceWorkflowIds']), sourceRunIds=sorted(item['sourceRunIds']),
                    sources=sorted(item['sources'], key=lambda source: (source['workflowId'], source['runId'])))
        materialized.append(item)
    return sorted(materialized, key=lambda item: item['id'])


def candidate_rows(task, tiny_edges, tools, intent):
    query = grams(intent)
    current_contract = contract_hash(tools)
    rows = []
    for edge in tiny_edges:
        if edge.get('scenario') != task['scenario'] or edge.get('contractHash') != current_contract or not edge.get('executable'):
            continue
        other = grams(edge.get('intent', ''))
        score = len(query & other) / max(1, len(query | other))
        if score >= .12:
            rows.append(dict(tinyEdgeId=edge['id'], score=round(score, 4), support=edge['support'], length=edge['length'],
                             sourceWorkflowIds=edge['sourceWorkflowIds'], intent=edge['intent']))
    return sorted(rows, key=lambda item: (-item['score'], -item['support'], item['tinyEdgeId']))[:5]


def _renamed_node(node, edge_id, offset, mapping):
    result = deepcopy(node)
    old = result['id']
    result['id'] = f'c{offset}_{old}'
    mapping[old] = result['id']
    return result


def compose(selected_ids, tiny_edges, tools):
    """Expand exactly selected fragments; reject any ambiguous or invalid composition."""
    by_id = {edge['id']: edge for edge in tiny_edges}
    if len(selected_ids) < 2 or len(set(selected_ids)) < 2 or any(key not in by_id for key in selected_ids):
        raise ValueError('composition_requires_two_distinct_selected_tinyedges')
    nodes, origins, canonical_seen = [], [], {}
    for offset, edge_id in enumerate(selected_ids, 1):
        edge = by_id[edge_id]
        mapping, local = {}, []
        for template, canonical in zip(edge['nodeTemplates'], edge['canonicalNodes']):
            marker = stable(canonical)
            if marker in canonical_seen:
                mapping[template['id']] = canonical_seen[marker]
                continue
            node = _renamed_node(template, edge_id, offset, mapping)
            canonical_seen[marker] = node['id']
            local.append(node)
            origins.append(dict(nodeId=node['id'], tinyEdgeId=edge_id, sourceWorkflowIds=edge['sourceWorkflowIds'], sourceRunIds=edge['sourceRunIds']))
        for node in local:
            node['dependencies'] = [mapping[dep] for dep in node['dependencies'] if dep in mapping]
            if node.get('foreach'):
                node['foreach']['nodeId'] = mapping[node['foreach']['nodeId']]
            if node.get('reuse'):
                node['reuse']['nodeId'] = mapping[node['reuse']['nodeId']]
            for binding in node['arguments'].values():
                if binding['kind'] == 'result':
                    binding['nodeId'] = mapping[binding['nodeId']]
            nodes.append(node)
    # A fragment can only depend on nodes retained from itself or an exact canonical merge.
    ordered_nodes(nodes, tools)
    return dict(nodes=nodes, origins=origins)
