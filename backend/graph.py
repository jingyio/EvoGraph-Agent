"""Trace-to-DAG compilation and guarded execution; no model HTTP dependency."""
import asyncio
from copy import deepcopy
import re
import networkx as nx
from .autotool import canonical, digest, path_value, UNSAFE


def task_key(task):
    normalized = re.sub(r'以\s*\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\s*为本次巡检时刻', '以<inspection-clock>为本次巡检时刻', task)
    return digest(re.sub(r'\s+', ' ', normalized).strip())


def contract_hash(tools):
    return digest(sorted([{'name': t.name, 'description': t.description, 'parameters': t.parameters, 'effect': t.effect, 'outputs': list(t.outputs or [])} for t in tools], key=lambda t: t['name']))


def candidates(samples, tool_name, parameter, value):
    found = []
    entity = re.sub(r'_?id$', '', parameter, flags=re.I).lower()
    for sample in samples:
        if sample['node']['tool'] == tool_name:
            continue
        for observation in sample['observations']:
            if isinstance(observation, list):
                rows, collection = observation, []
            elif isinstance(observation, dict) and isinstance(observation.get('records'), list):
                rows, collection = observation['records'], ['records']
            else:
                rows, collection = [observation], None
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for key, entry in row.items():
                    if type(entry) != type(value) or entry != value or isinstance(entry, (dict, list)) or key in UNSAFE:
                        continue
                    field = re.sub(r'_?id$', '', key, flags=re.I).lower()
                    identifier = key in ['id', 'name']
                    score = 90 if field == entity else 35 if identifier else 0
                    if identifier and entity in sample['node']['tool'].lower():
                        score += 80
                    if parameter == 'customerId' and key == 'party':
                        score += 75
                    if parameter == 'query' and key in ['subject', 'title', 'body']:
                        score += 70
                    if collection is not None:
                        score += 10
                    if score >= 70:
                        found.append({'nodeId': sample['node']['id'], 'collectionPath': collection, 'fieldPath': [key], 'score': score})
    return sorted(found, key=lambda item: -item['score'])


def compile_read_graph(run, tools):
    if run['request']['mode'] != 'live' or run['status'] != 'completed' or run['metrics']['modelRequests'] < 1:
        raise ValueError('仅从正常结束的真实模型运行学习，离线与失败轨迹不可用。')
    if run.get('evaluation', {}).get('status') == 'failed':
        raise ValueError('任务结果校验不通过，拒绝晋升为新经验。')
    samples, known = [], {t.name: t for t in tools}
    for index, event in enumerate(run['events']):
        if event['type'] != 'action':
            continue
        tool = known.get(event['title'])
        if tool is None or tool.effect != 'read':
            break
        observation = next((e for e in run['events'][index + 1:] if e['type'] in ['action', 'observation']), None)
        if not observation or observation['type'] != 'observation' or not observation.get('detail', {}).get('ok'):
            continue
        try:
            args = json_arguments(event)
        except (ValueError, KeyError, TypeError):
            continue
        bindings, iteration, valid = {}, None, True
        for parameter, value in args.items():
            enum = tool.parameters.get('properties', {}).get(parameter, {}).get('enum', [])
            dynamic = re.search('id$', parameter, re.I) or parameter in ['query', 'category']
            found = candidates(samples, tool.name, parameter, value) if dynamic else []
            if found:
                best = next((c for c in found if iteration is None or (c['nodeId'] == iteration['nodeId'] and c['collectionPath'] == iteration['collectionPath'])), None)
                if best is None:
                    valid = False
                    break
                iteration = {'nodeId': best['nodeId'], 'collectionPath': best['collectionPath']}
                bindings[parameter] = {'kind': 'item', 'path': best['fieldPath']}
            elif (dynamic and value not in enum) or not (value in enum or (parameter in ['page', 'pageSize'] and type(value) is int)):
                valid = False
                break
            else:
                bindings[parameter] = {'kind': 'literal', 'value': deepcopy(value)}
        if not valid:
            break
        result, paginate = observation['detail']['result'], None
        if 'page' in args and 'pageSize' in args and isinstance(result, dict) and isinstance(result.get('records'), list) and type(result.get('mayHaveMore')) is bool:
            controls = {k: v for k, v in bindings.items() if k != 'page'}
            previous = any(s['node']['tool'] == tool.name and s['node'].get('paginate') and {k: v for k, v in s['node']['arguments'].items() if k != 'page'} == controls for s in samples)
            if args['page'] == 1 or previous:
                bindings['page'], paginate = {'kind': 'literal', 'value': 1}, {'maxPages': 20}
        equivalent = next((s for s in samples if s['node']['tool'] == tool.name and s['node']['arguments'] == bindings and s['node'].get('foreach') == iteration and bool(s['node'].get('paginate')) == bool(paginate)), None)
        if equivalent:
            equivalent['observations'].append(deepcopy(result))
            equivalent['node']['sourceEventSeqs'].append(event['seq'])
            continue
        if len(samples) >= 40:
            break
        node = {'id': f'n{len(samples) + 1}', 'tool': tool.name, 'arguments': bindings, 'dependencies': [iteration['nodeId']] if iteration else [], 'sourceEventSeqs': [event['seq']]}
        if iteration is not None:
            node['foreach'] = iteration
        if paginate:
            node['paginate'] = paginate
        samples.append({'node': node, 'observations': [deepcopy(result)]})
    if not samples:
        raise ValueError('轨迹没有可安全编译的读取前缀。')
    return [s['node'] for s in samples]


def json_arguments(event):
    import json
    args = json.loads(event['detail']['arguments'])
    if not isinstance(args, dict):
        raise ValueError('arguments must be an object')
    return args


def ordered_nodes(nodes, tools):
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 40:
        raise ValueError('任务图节点数量无效')
    graph = nx.DiGraph()
    known = {t.name: t for t in tools}
    allowed = {'id', 'tool', 'arguments', 'dependencies', 'foreach', 'paginate', 'reuse', 'sourceEventSeqs'}
    for node in nodes:
        if not isinstance(node, dict) or set(node) - allowed:
            raise ValueError('无效图节点字段')
        key = node.get('id')
        if not isinstance(key, str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}', key) or key in UNSAFE or key in graph:
            raise ValueError('重复或无效节点 ID')
        if node.get('tool') not in known or known[node['tool']].effect != 'read':
            raise ValueError('任务图禁止非读取工具')
        graph.add_node(key)
    by_id = {n['id']: n for n in nodes}
    for node in nodes:
        actual = set()
        for parameter, binding in node['arguments'].items():
            if parameter in UNSAFE or not isinstance(binding, dict):
                raise ValueError('无效图参数')
            kind = binding.get('kind')
            if kind == 'literal':
                if set(binding) != {'kind', 'value'} or len(canonical(binding['value'])) > 8000:
                    raise ValueError('无效常量绑定')
            elif kind in ['item', 'result']:
                path = binding.get('path')
                if not isinstance(path, list) or len(path) > 8 or any(not isinstance(p, str) or p in UNSAFE for p in path):
                    raise ValueError('不安全的参数路径')
                if kind == 'result':
                    actual.add(binding['nodeId'])
                elif not node.get('foreach'):
                    raise ValueError('item 绑定缺少遍历来源')
            else:
                raise ValueError('未知参数绑定类型')
        if node.get('foreach'):
            actual.add(node['foreach']['nodeId'])
            path = node['foreach']['collectionPath']
            if path is not None and (not isinstance(path, list) or any(not isinstance(p, str) or p in UNSAFE for p in path)):
                raise ValueError('遍历路径无效')
        if node.get('reuse'):
            reuse = node['reuse']
            if set(reuse) != {'nodeId', 'collectionPath', 'fields'} or node['arguments'] or node.get('foreach') or node.get('paginate'):
                raise ValueError('复用节点结构无效')
            path, fields = reuse['collectionPath'], reuse['fields']
            if not isinstance(path, list) or any(not isinstance(p, str) or p in UNSAFE for p in path):
                raise ValueError('复用路径无效')
            if not isinstance(fields, list) or not fields or any(not isinstance(field, str) or field in UNSAFE for field in fields):
                raise ValueError('复用字段无效')
            actual.add(reuse['nodeId'])
        deps = node['dependencies']
        if not isinstance(deps, list) or not actual.issubset(deps) or any(dep not in by_id for dep in deps):
            raise ValueError('任务图缺少数据依赖')
        if node.get('paginate') and (type(node['paginate'].get('maxPages')) is not int or not 1 <= node['paginate']['maxPages'] <= 20):
            raise ValueError('分页上限无效')
        graph.add_edges_from((dep, node['id']) for dep in deps)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError('任务图存在循环依赖')
    return [by_id[key] for key in nx.topological_sort(graph)]


async def run_read_graph(nodes, tools, invoke, node_event=lambda key, state: None):
    outputs = {}
    for node in ordered_nodes(nodes, tools):
        await asyncio.sleep(0)
        node_event(node['id'], 'running')
        try:
            if node.get('reuse'):
                outputs[node['id']] = deepcopy(outputs[node['reuse']['nodeId']])
                node_event(node['id'], 'reused')
                continue
            items = [None]
            if node.get('foreach'):
                source = outputs[node['foreach']['nodeId']]
                path = node['foreach']['collectionPath']
                if path is None:
                    items = source
                else:
                    items = []
                    for value in source:
                        array = path_value(value, path)
                        if not isinstance(array, list):
                            raise ValueError('上游集合形状发生变化')
                        items.extend(array)
                if len(items) > 1000:
                    raise ValueError('图遍历超过 1000 条记录')
            values, seen = [], set()
            for item in items:
                args = {}
                for parameter, binding in node['arguments'].items():
                    if binding['kind'] == 'literal':
                        args[parameter] = deepcopy(binding['value'])
                    elif binding['kind'] == 'item':
                        args[parameter] = path_value(item, binding['path'])
                    else:
                        source = outputs[binding['nodeId']]
                        if len(source) != 1:
                            raise ValueError('单值参数来源不唯一')
                        args[parameter] = path_value(source[0], binding['path'])
                signature = canonical(args)
                if signature in seen:
                    continue
                seen.add(signature)
                page_limit = node.get('paginate', {}).get('maxPages', 1)
                for page in range(1, page_limit + 1):
                    await asyncio.sleep(0)
                    result = await invoke(node['tool'], dict(args, page=page) if node.get('paginate') else args, node['id'])
                    values.append(deepcopy(result))
                    if not node.get('paginate'):
                        break
                    if not isinstance(result, dict) or not isinstance(result.get('records'), list) or type(result.get('mayHaveMore')) is not bool:
                        raise ValueError('分页接口返回形状变化')
                    if not result['mayHaveMore']:
                        break
                    if page == page_limit:
                        raise ValueError('达到任务图分页上限，剩余数据交给模型')
            outputs[node['id']] = values
            node_event(node['id'], 'done')
        except BaseException:
            node_event(node['id'], 'failed')
            raise
    return outputs


def applicable(graph, request, tools, environment):
    if graph['scenario'] != request['scenario'] or graph['source'] != request['source']:
        return '场景或数据源不匹配'
    if graph['taskKey'] != task_key(request['task']):
        return '任务要求变化，检查相似经验'
    if graph['contractHash'] != contract_hash(tools):
        return '工具契约变化，需重新验证'
    if graph['environmentHash'] != environment:
        return '实例或执行器变化，需重新验证'
    return None
