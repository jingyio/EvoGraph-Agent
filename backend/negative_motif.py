"""Restricted contrastive compilation; negative evidence is not a successful workflow."""
from copy import deepcopy
import asyncio
import json
from pathlib import Path
from uuid import uuid4
import networkx as nx
from .domain import now
from .graph import contract_hash, json_arguments
from .tools import ToolContext


ERROR = 'Case must cite existing invoice/payment records including its entity'
RULE = 'duplicate-bankref-as-entity-v1'
GUIDANCE = ('历史负 motif：登记 duplicate 异常时，entityId 必须绑定本次 list_payments 的 id，'
            '不能绑定 bankRef；evidenceIds 引用同一 bankRef 的全部回款 id。先核对本次数据，再调用工具。')


def call_pairs(run):
    pending = None
    for event in run['events']:
        if event['type'] == 'action':
            pending = event
        elif event['type'] == 'observation' and pending:
            if event['title'].split(' · ')[0] == pending['title']:
                try:
                    args = json_arguments(pending)
                    yield pending, event, args
                except (ValueError, KeyError, TypeError):
                    pass
            pending = None


def matched_rows(args, rows):
    """Match only the observed, unambiguous bankRef/record-ID confusion."""
    if not isinstance(args, dict) or args.get('kind') != 'duplicate' or not isinstance(rows, list):
        return []
    entity, evidence = args.get('entityId'), args.get('evidenceIds')
    if not isinstance(entity, str) or not isinstance(evidence, list) or any(not isinstance(v, str) for v in evidence):
        return []
    if any(not isinstance(r, dict) or not isinstance(r.get('id'), str) or not isinstance(r.get('bankRef'), str) for r in rows):
        return []
    if any(r['id'] == entity for r in rows):
        return []
    peers = [r for r in rows if r['bankRef'] == entity]
    if len(peers) < 2 or len({r['id'] for r in peers}) != len(peers):
        return []
    return peers if {r['id'] for r in peers} == set(evidence) else []


def motif_nodes(read_seq, fail_seq, repair_seq):
    return [
        dict(id='read', kind='observation', tool='list_payments', dependencies=[], sourceEventSeqs=[read_seq]),
        dict(id='bad_bind', kind='binding', tool='create_finance_case', field='entityId', path=['bankRef'], dependencies=['read'], sourceEventSeqs=[fail_seq]),
        dict(id='reject', kind='failure', errorCode=RULE, dependencies=['bad_bind'], sourceEventSeqs=[fail_seq + 1]),
        dict(id='repair_bind', kind='binding', tool='create_finance_case', field='entityId', path=['id'], dependencies=['read', 'reject'], sourceEventSeqs=[repair_seq]),
        dict(id='success', kind='local_success', dependencies=['repair_bind'], sourceEventSeqs=[repair_seq + 1]),
    ]


def applicable(motif, request, tools):
    from .graph_store import environment_hash
    return (motif.get('status') == 'validated' and motif.get('rule') == RULE
            and motif.get('source') == request['source'] == 'sandbox'
            and motif.get('scenario') == request['scenario'] == 'finance'
            and motif.get('contractHash') == contract_hash(tools)
            and motif.get('environmentHash') == environment_hash(request['source']))


async def compile_negative_motifs(run, tools):
    """Learn local repairs even if the overall task failed, never replay platform writes."""
    from .graph_store import environment_hash
    if run['request']['mode'] != 'live' or run['request']['source'] != 'sandbox' or run['request']['scenario'] != 'finance' or run['status'] == 'running':
        return {'motifs': [], 'unexplainedFailures': [dict(eventSeq=a['seq'], tool=a['title'], error=o['detail'].get('error'))
                for a, o, _ in call_pairs(run) if o['detail'].get('ok') is False], 'note': '仅编译已结束的真实模型财务沙箱轨迹，其他错误保留待分析'}
    pairs = list(call_pairs(run))
    known = {t.name: t for t in tools}
    motifs, explained = [], set()
    for index, (action, observation, args) in enumerate(pairs):
        if action['title'] != 'create_finance_case' or observation['detail'].get('ok') is not False or observation['detail'].get('error') != ERROR:
            continue
        reads = [(a, o) for a, o, _ in pairs[:index] if a['title'] == 'list_payments' and o['detail'].get('ok') is True]
        if not reads:
            continue
        read, data = reads[-1]
        rows = data['detail'].get('result')
        peers = matched_rows(args, rows)
        if not peers:
            continue
        for repair, success, corrected in pairs[index + 1:]:
            if repair['title'] != action['title'] or success['detail'].get('ok') is not True:
                continue
            # Prose changes carry no evidence. All structural parameters except entityId must agree.
            structural = lambda value: {k: v for k, v in value.items() if k not in ['entityId', 'summary']}
            if structural(args) != structural(corrected) or corrected.get('entityId') not in [p['id'] for p in peers]:
                continue
            # Contrast on the same isolated pre-call state; only sandbox tools are replayed.
            probe = dict(run, state=deepcopy(run['initial']), events=[])
            context = ToolContext(probe)
            replay_calls, verified = 0, True
            for prior, prior_result, prior_args in pairs[:index]:
                if prior_result['detail'].get('ok') is not True:
                    continue
                tool = known.get(prior['title'])
                if not tool or replay_calls >= 60:
                    verified = False
                    break
                try:
                    await tool.execute(prior_args, context)
                    replay_calls += 1
                except Exception:
                    verified = False
                    break
            if not verified or not matched_rows(args, probe['state']['payments']):
                break
            before = deepcopy(probe['state'])
            try:
                replay_calls += 1
                await known['create_finance_case'].execute(args, context)
                break
            except ValueError as error:
                if str(error) != ERROR or probe['state'] != before:
                    break
            try:
                replay_calls += 1
                await known['create_finance_case'].execute(corrected, context)
            except Exception:
                break
            nodes = motif_nodes(read['seq'], action['seq'], repair['seq'])
            nodes[2]['sourceEventSeqs'] = [observation['seq']]
            nodes[4]['sourceEventSeqs'] = [success['seq']]
            graph = nx.DiGraph((dep, node['id']) for node in nodes for dep in node['dependencies'])
            if not nx.is_directed_acyclic_graph(graph):
                raise ValueError('负 motif 存在循环依赖')
            motifs.append(dict(id=str(uuid4()), rule=RULE, status='validated', createdAt=now(), scenario='finance', source='sandbox',
                               sourceRunId=run['id'], sourceRunStatus=run['status'], sourceEvaluation=deepcopy(run.get('evaluation')),
                               contractHash=contract_hash(tools), environmentHash=environment_hash('sandbox'), nodes=nodes,
                               failureEventSeq=action['seq'], repairEventSeq=repair['seq'],
                               reflection=GUIDANCE, validation=dict(method='isolated-contrast-replay', toolCalls=replay_calls, modelRequests=0,
                               scope='局部参数修复，不证明整任务成功或平均收益')))
            explained.add(action['seq'])
            break
    unexplained = [dict(eventSeq=a['seq'], tool=a['title'], error=o['detail'].get('error')) for a, o, _ in pairs
                   if o['detail'].get('ok') is False and a['seq'] not in explained]
    return dict(motifs=motifs, unexplainedFailures=unexplained)


class NegativeMotifStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.motifs = {}
        self.lock = asyncio.Lock()

    def restore(self):
        for path in self.directory.glob('*.json'):
            try:
                item = json.loads(path.read_text())
                if item['id'] == path.stem and item.get('status') == 'validated' and item.get('rule') == RULE:
                    self.motifs[item['id']] = item
            except (ValueError, KeyError, TypeError, OSError):
                continue

    def select(self, request, tools):
        # Equivalent evidence does not multiply prompts or guard checks.
        result = {}
        for motif in self.motifs.values():
            if applicable(motif, request, tools):
                result[motif['rule']] = deepcopy(motif)
        return list(result.values())

    async def learn(self, run, tools):
        async with self.lock:
            return await self._learn(run, tools)

    async def _learn(self, run, tools):
        from .graph_store import write_private
        result = await compile_negative_motifs(run, tools)
        for i, motif in enumerate(result['motifs']):
            existing = next((m for m in self.motifs.values() if all(m[k] == motif[k] for k in ['sourceRunId', 'failureEventSeq', 'contractHash', 'environmentHash'])), None)
            if existing:
                result['motifs'][i] = existing
            else:
                write_private(self.directory / (motif['id'] + '.json'), motif)
                self.motifs[motif['id']] = motif
        return result
