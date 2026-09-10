"""Conservative, train-only Tool Inertia Graph records and runtime binding."""
from collections import defaultdict
from copy import deepcopy
import math
import re
import time
from .autotool import canonical


SCHEMA_VERSION = 1
MIN_SUPPORT = 2
ACCEPT_THRESHOLD = .55


def _tokens(value):
    words = re.findall(r'[a-z0-9]+', str(value).lower())
    for phrase in re.findall(r'[\u4e00-\u9fff]+', str(value)):
        words.extend(phrase[index:index + 2] for index in range(max(0, len(phrase) - 1)))
    return set(words)


def _paths(value, prefix=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _paths(item, prefix + (str(key),))
    elif isinstance(value, list):
        for item in value:
            yield from _paths(item, prefix + ('*',))
    elif value is not None and not isinstance(value, (dict, list)):
        yield prefix, value


def _resolve(value, path):
    rows = [value]
    for part in path:
        next_rows = []
        for row in rows:
            if part == '*' and isinstance(row, list):
                next_rows.extend(row)
            elif isinstance(row, dict) and part in row:
                next_rows.append(row[part])
        rows = next_rows
    return rows


def _events(run):
    actions, observations = {}, {}
    for event in run.get('events', []):
        detail = event.get('detail') or {}
        if event.get('type') == 'action' and detail.get('executor') == 'model':
            try:
                args = __import__('json').loads(detail.get('arguments', '{}'))
            except (TypeError, ValueError):
                continue
            actions[detail.get('callId')] = dict(seq=event['seq'], tool=event['title'], args=args)
        elif event.get('type') == 'observation' and detail.get('executor') == 'model':
            observations[detail.get('callId')] = dict(seq=event['seq'], ok=detail.get('ok') is True, result=detail.get('result'))
    rows = []
    for call_id, action in actions.items():
        observation = observations.get(call_id)
        if observation and observation['ok']:
            rows.append(dict(**action, observationSeq=observation['seq'], result=observation['result']))
    return sorted(rows, key=lambda row: row['seq'])


def empty():
    return dict(schemaVersion=SCHEMA_VERSION, toolPaths=[], parameterEdges=[])


def update(store, run, task, tools):
    """Update only serial, successful, model-origin train observations."""
    started = time.perf_counter()
    info = dict(updatedPaths=0, updatedParameterEdges=0, source='model-origin-train-only')
    if task.get('split') != 'train' or run.get('evaluation', {}).get('status') != 'passed':
        return info | {'updateMs': round((time.perf_counter() - started) * 1000, 3)}
    if any(run['id'] in row.get('sourceRunIds', []) for row in store.get('toolPaths', [])):
        return info | {'duplicateRun': True, 'updateMs': round((time.perf_counter() - started) * 1000, 3)}
    paths = {tuple(row['tools']): row for row in store.setdefault('toolPaths', [])}
    edges = {(row['sourceTool'], tuple(row['sourcePath']), row['targetTool'], row['targetParameter']): row for row in store.setdefault('parameterEdges', [])}
    prior = None
    for current in _events(run):
        if prior and prior['observationSeq'] < current['seq']:
            key = (prior['tool'], current['tool'])
            row = paths.setdefault(key, dict(tools=list(key), support=0, sourceRunIds=[], sourceTaskIds=[]))
            row['support'] += 1
            if run['id'] not in row['sourceRunIds']:
                row['sourceRunIds'].append(run['id'])
                row['sourceTaskIds'].append(task['id'])
            info['updatedPaths'] += 1
            for parameter, value in current['args'].items():
                matches = [path for path, source_value in _paths(prior['result']) if source_value == value]
                if len(matches) == 1:
                    edge_key = (prior['tool'], matches[0], current['tool'], parameter)
                    edge = edges.setdefault(edge_key, dict(sourceTool=prior['tool'], sourcePath=list(matches[0]), targetTool=current['tool'], targetParameter=parameter, support=0, sourceRunIds=[], sourceTaskIds=[]))
                    edge['support'] += 1
                    if run['id'] not in edge['sourceRunIds']:
                        edge['sourceRunIds'].append(run['id'])
                        edge['sourceTaskIds'].append(task['id'])
                    info['updatedParameterEdges'] += 1
        prior = current
    store['schemaVersion'] = SCHEMA_VERSION
    store['toolPaths'] = sorted(paths.values(), key=lambda row: (row['tools'], row['sourceRunIds']))
    store['parameterEdges'] = sorted(edges.values(), key=lambda row: (row['sourceTool'], row['sourcePath'], row['targetTool'], row['targetParameter']))
    info['updateMs'] = round((time.perf_counter() - started) * 1000, 3)
    return info


def _runtime_observations(run):
    actions, observations = {}, {}
    for event in run.get('events', []):
        detail = event.get('detail') or {}
        if event.get('type') == 'action':
            actions[detail.get('callId')] = dict(seq=event['seq'], tool=event['title'], executor=detail.get('executor'))
        elif event.get('type') == 'observation' and detail.get('ok') is True:
            observations[detail.get('callId')] = dict(observationSeq=event['seq'], result=detail.get('result'))
    rows = []
    for call_id, action in actions.items():
        observation = observations.get(call_id)
        if observation:
            rows.append(action | observation)
    return sorted(rows, key=lambda row: row['seq'])


def _serial_context(history):
    """Exclude actions that share an unresolved concurrent batch.

    A tool becomes context only if its observation completed before the next
    action started. The final action of a batch is also excluded when its
    predecessor was still unresolved at its start; it has no proven order.
    """
    tools = []
    for index, row in enumerate(history):
        previous = history[index - 1] if index else None
        following = history[index + 1] if index + 1 < len(history) else None
        starts_after_previous = previous is None or previous['observationSeq'] < row['seq']
        finishes_before_next = following is None or row['observationSeq'] < following['seq']
        if starts_after_previous and finishes_before_next:
            tools.append(row['tool'])
    return tools[-2:]


def attempt(store, run, intent, tools):
    """Return an accepted read-only call or a structured rejection without model use."""
    started = time.perf_counter()
    history = _runtime_observations(run)
    recent = _serial_context(history)
    result = dict(recentTools=recent, candidates=[], accepted=False, queryMs=0)
    if not recent:
        result['reason'] = 'no_current_tool_context'
        result['queryMs'] = round((time.perf_counter() - started) * 1000, 3)
        return result
    candidates = defaultdict(int)
    window = recent[-2:]
    for row in store.get('toolPaths', []):
        path = row.get('tools', [])
        if len(path) == 2 and path[0] == window[-1]:
            candidates[path[1]] += row.get('support', 0)
    if not candidates:
        result['reason'] = 'no_supported_successor'
        result['queryMs'] = round((time.perf_counter() - started) * 1000, 3)
        return result
    by_name, total = {tool.name: tool for tool in tools}, sum(candidates.values())
    intent_tokens = _tokens(intent)
    for name, support in candidates.items():
        tool = by_name.get(name)
        if not tool:
            continue
        relevance = len(intent_tokens & _tokens(tool.description + ' ' + tool.name.replace('_', ' '))) / max(1, len(intent_tokens | _tokens(tool.description + ' ' + tool.name.replace('_', ' '))))
        frequency = support / total * (1 - math.pow(1.1, -total))
        score = .7 * frequency + .3 * relevance
        result['candidates'].append(dict(tool=name, support=support, totalSupport=total, frequency=round(frequency, 4), relevance=round(relevance, 4), score=round(score, 4), effect=tool.effect))
    result['candidates'].sort(key=lambda row: (-row['score'], -row['support'], row['tool']))
    if not result['candidates']:
        result['reason'] = 'candidate_tool_unavailable'
        result['queryMs'] = round((time.perf_counter() - started) * 1000, 3)
        return result
    best = result['candidates'][0]
    tool = by_name[best['tool']]
    if tool.effect != 'read':
        result['reason'] = 'candidate_not_read_only'
    elif best['support'] < MIN_SUPPORT or best['score'] < ACCEPT_THRESHOLD:
        result['reason'] = 'confidence_below_threshold'
    else:
        args, bindings = {}, []
        for parameter in tool.parameters.get('required', []):
            options = []
            for edge in store.get('parameterEdges', []):
                if edge.get('targetTool') != tool.name or edge.get('targetParameter') != parameter or edge.get('support', 0) < MIN_SUPPORT:
                    continue
                for observation in reversed(history):
                    if observation['tool'] != edge['sourceTool']:
                        continue
                    values = _resolve(observation['result'], edge['sourcePath'])
                    unique = {canonical(value): value for value in values}
                    if len(unique) == 1:
                        options.append((next(iter(unique.values())), edge, observation))
                    break
            if len(options) != 1:
                result['reason'] = 'parameter_missing_or_ambiguous:' + parameter
                break
            value, edge, observation = options[0]
            args[parameter] = value
            bindings.append(dict(parameter=parameter, sourceTool=edge['sourceTool'], sourcePath=edge['sourcePath'], sourceCallSeq=observation['seq']))
        else:
            errors = list(tool.validator.iter_errors(args))
            signature = canonical([tool.name, args])
            seen = {item.get('signature') for item in run.get('toolTrace', []) if item.get('ok') is True}
            if errors:
                result['reason'] = 'parameter_type_invalid'
            elif signature in seen:
                result['reason'] = 'duplicate_successful_call'
            else:
                result.update(accepted=True, call=dict(function=dict(name=tool.name, arguments=canonical(args))), bindings=bindings, reason='accepted')
    result['queryMs'] = round((time.perf_counter() - started) * 1000, 3)
    return result
