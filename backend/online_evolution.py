"""Graph revisions from normal task traffic. No provider, tool invocation or shadow rollout."""
from copy import deepcopy
import json
import re
import time
from uuid import uuid4
import networkx as nx
from .autotool import digest
from . import trajectory
from .domain import now
from .graph import ordered_nodes, contract_hash
from .graph_store import write_private
from .intent_graph import compile_intent_graph, prune_unrequested_steps
from .tinyedge import TinyEdgeMaintenanceError, mine as mine_tinyedges, candidate_rows, compose as compose_tinyedges


class OnlineEvolution:
    def __init__(self, bank, path=None):
        self.bank = bank
        self.path = path or bank.root / 'artifacts/online-graphs.json'
        self.versions = []
        self.workflows = []
        self.tiny_edges = []
        self.tool_inertia = dict(schemaVersion=1, toolPaths=[], parameterEdges=[])

    def restore(self):
        if self.path.exists():
            payload = json.loads(self.path.read_text())
            self.versions = payload.get('versions', [])
            self.workflows = payload.get('workflows', [])
            self.tiny_edges = payload.get('tinyEdges', [])
            self.tool_inertia = payload.get('toolInertia', self.tool_inertia)

    def save(self):
        started = time.perf_counter()
        write_private(self.path, dict(schemaVersion=3, versions=self.versions,
                                      workflows=self.workflows, tinyEdges=self.tiny_edges,
                                      toolInertia=self.tool_inertia))
        return round((time.perf_counter() - started) * 1000, 3)

    def context_key(self, task, tools):
        # Only the taskbank's explicit record-count/clock slots are generalized.
        text = task.get('template') or task['task'].replace(task['id'], '<task>')
        text = re.sub(r'工具可见的\s*\d+\s*条记录', '工具可见的 <N> 条记录', text)
        if task.get('asOf'):
            text = text.replace(task['asOf'], '<clock>')
        return digest(dict(scenario=task['scenario'], family=task.get('family', task['id']), template=text,
                           schema=task.get('schemaContract'), contract=contract_hash(tools),
                           corpus=getattr(self.bank, 'manifest', None), executor=2))

    def latest(self, task, tools):
        key = self.context_key(task, tools)
        return next((v for v in reversed(self.versions) if v['contextKey'] == key), None)

    def select(self, task, tools):
        if task.get('workspaceId'):
            return None  # Workspace selection uses witnessed trajectory descriptors.
        version = self.latest(task, tools)
        if not version or version['status'] == 'needs-repair':
            return None
        # A compiler correctness upgrade may invalidate an over-reading saved
        # Plan. Keep the parent immutable and let a passing normal train run
        # create the auditable child version.
        _, removed = prune_unrequested_steps(version['plan'], task['task'])
        if removed:
            version['status'] = 'needs-repair'
            version['scope'] = '旧图包含与当前任务无关的读取；等待重新编译后的正常训练证据'
            version['compilerInvalidation'] = dict(kind='task_semantic_pruning', removedSteps=removed)
            return None
        # Tests consume a frozen, previously supported version; never collect test evidence.
        if task['split'] == 'test' and version['status'] != 'family-supported':
            return None
        ordered_nodes(version['nodes'], tools)
        return deepcopy(version)

    def composition_candidates(self, task, tools):
        if task.get('workspaceId'):
            return []
        rows = []
        for edge in self.tiny_edges:
            if edge.get('scenario') == task['scenario'] and edge.get('contractHash') == contract_hash(tools):
                rows.append(deepcopy(edge))
        return rows

    def compose(self, task, tools, coarse_plan):
        candidates = self.composition_candidates(task, tools)
        if not candidates:
            raise ValueError('no_materialized_tinyedges')
        selected, retrieval = [], []
        for subgoal in coarse_plan['subgoals']:
            rows = candidate_rows(task, candidates, tools, subgoal['intent'])
            retrieval.append(dict(subgoalId=subgoal['id'], intent=subgoal['intent'], candidates=rows))
            if not rows:
                raise ValueError('composition_uncovered_subgoal:' + subgoal['id'])
            choice = next((row for row in rows if row['tinyEdgeId'] not in selected), rows[0])
            selected.append(choice['tinyEdgeId'])
        if len(set(selected)) < 2:
            raise ValueError('composition_requires_two_distinct_tinyedges')
        assembled = compose_tinyedges(selected, candidates, tools)
        known = {tool.name: tool for tool in tools}
        plan_steps = []
        for node in assembled['nodes']:
            step = dict(id=node['id'], intent=known[node['tool']].description, dependencies=deepcopy(node['dependencies']))
            condition = (node.get('foreach') or {}).get('filter')
            if condition:
                step['selection'] = dict(kind='match', sourceStepId=node['foreach']['nodeId'], **deepcopy(condition))
            plan_steps.append(step)
        return dict(plan=dict(steps=plan_steps), nodes=assembled['nodes'], origins=assembled['origins'],
                    selectedTinyEdgeIds=selected, retrieval=retrieval)

    def create(self, task, tools, run, nodes, plan, parent, patches):
        ordered_nodes(nodes, tools)
        version = dict(id=str(uuid4()), parentGraphId=parent['id'] if parent else None,
                       generation=parent['generation'] + 1 if parent else 0, contextKey=self.context_key(task, tools),
                       scenario=task['scenario'], family=task.get('family', task['id']), sourceTaskId=task['id'],
                       createdAt=now(), sourceRunId=run['id'], sourceSplit=task['split'], nodes=deepcopy(nodes),
                       plan=deepcopy(plan), patches=patches, status='probation', evidence=[],
                       scope='匹配工具契约与任务模板的同类任务试用')
        self.versions.append(version)
        return version

    def record_workflow(self, run, task, tools, info):
        """Only completed training graph executions contribute TinyEdge support."""
        graph = run.get('graph') or {}
        if task['split'] != 'train' or graph.get('status') != 'done' or run.get('evaluation', {}).get('status') != 'passed':
            return
        if any(item['id'] == run['id'] for item in self.workflows):
            return
        nodes = deepcopy(graph['nodes'])
        plan = self.safe_plan(run['plan'], nodes, tools)
        workflow = dict(id=run['id'], sourceRunId=run['id'], sourceGraphId=info.get('usedVersionId'),
                        sourceTaskId=task['id'], scenario=task['scenario'], family=task.get('family', task['id']),
                        sourceSplit='train', contractHash=contract_hash(tools), nodes=nodes, plan=plan)
        self.workflows.append(workflow)
        partition = dict(scenario=task['scenario'], contractHash=workflow['contractHash'])
        compatible = [item for item in self.workflows if item.get('scenario') == partition['scenario']
                      and item.get('contractHash') == partition['contractHash']]
        retained = [item for item in self.tiny_edges if not (item.get('scenario') == partition['scenario']
                    and item.get('contractHash') == partition['contractHash'])]
        maintenance = dict(recordedWorkflowId=workflow['id'], workflowStatus='recorded', partition=partition,
                           partitionWorkflowCount=len(compatible), supportThreshold=2,
                           extraModelRequests=0, extraToolCalls=0)
        try:
            mined = mine_tinyedges(compatible, tools)
            self.tiny_edges = retained + mined
            maintenance.update(miningStatus='ok', materializedCount=len(mined), totalMaterializedCount=len(self.tiny_edges))
        except TinyEdgeMaintenanceError as error:
            maintenance.update(miningStatus='failed', reasonCode=error.code, reason=error.detail,
                               materializedCount=0, totalMaterializedCount=len(self.tiny_edges))
        except Exception as error:
            maintenance.update(miningStatus='failed', reasonCode='unexpected_error', reason=str(error)[:500],
                               materializedCount=0, totalMaterializedCount=len(self.tiny_edges))
        info['tinyEdgeMaintenance'] = maintenance

    @staticmethod
    def has_workspace_table_slots(nodes):
        """Whether a graph relies on workspace-local semantic table slots.

        These slots are executable through ``TaskRunner.resolve_runtime_nodes``
        but are outside the generic intent-graph compiler's fixed list/detail
        binding signatures.  Treating that compiler limitation as a failed
        evolution step used to turn healthy workspace G0s into maintenance
        errors after they had already been saved.
        """
        return any(
            binding.get('kind') == 'workspaceTable'
            for node in nodes
            for binding in (node.get('arguments') or {}).values()
            if isinstance(binding, dict)
        )

    @staticmethod
    def safe_plan(plan, nodes, tools):
        # Store field requirements, not old record IDs, dates, answers or model prose.
        known = {t.name: t for t in tools}
        originals = {s['id']: s for s in plan['steps']}
        steps = []
        for node in nodes:
            tool = known[node['tool']]
            intent = originals[node['id']]['intent']
            fields = [f for f in (tool.outputs or []) if re.search(r'(?<![A-Za-z0-9_])' + re.escape(f) + r'(?![A-Za-z0-9_])', intent)]
            step = dict(id=node['id'], intent=('读取字段 ' + ', '.join(fields)) if fields else tool.description,
                        dependencies=deepcopy(node['dependencies']))
            if originals[node['id']].get('selection'):
                step['selection'] = deepcopy(originals[node['id']]['selection'])
            steps.append(step)
        return dict(steps=steps)

    def observe(self, run, task, tools):
        started = time.perf_counter()
        info = run.setdefault('evolution', {})
        info.update(extraModelRequests=0, extraToolCalls=0, shadowRollouts=0, generatedVersionIds=[])
        if task.get('workspaceId') and task['split'] != 'train':
            info['note'] = '非train工作区：不写经验文件或匹配描述'
            return
        try:
            if task.get('workspaceId'):
                trajectory.maintain(self, run, task, tools)
                return
            if task['split'] == 'test':
                info['note'] = '冻结测试：不学习、不反思、不更新版本证据'
                return
            if run['status'] in ['cancelled', 'interrupted', 'limited']:
                info['note'] = '任务中断或预算耗尽：保留轨迹，不生成图'
                return
            used = next((v for v in self.versions if v['id'] == info.get('usedVersionId')), None)
            passed = run['status'] == 'completed' and run['evaluation']['status'] == 'passed'
            if used:
                if any(e['runId'] == run['id'] for e in used['evidence']):
                    return
                used['evidence'].append(dict(runId=run['id'], taskId=task['id'], split=task['split'], passed=passed,
                    graphFallback=bool(run.get('fallback')), recoveryCalls=run['metrics'].get('recoveryToolCalls', 0),
                    modelRequests=run['metrics']['modelRequests'], tokens=run['metrics']['inputTokens'] + run['metrics']['outputTokens'],
                    durationMs=run['metrics']['durationMs'], usageComplete=run['metrics']['usageComplete']))
                clean = [e for e in used['evidence'] if e['passed'] and not e['graphFallback'] and e['usageComplete']]
                if not passed or run.get('fallback'):
                    used['status'] = 'needs-repair'
                elif used['status'] != 'needs-repair' and len({e['taskId'] for e in clean}) >= 3:
                    used['status'] = 'family-supported'
                    used['scope'] = '同模板同类任务已积累三个不同任务的成功证据；不扩展到全场景'
            if task['split'] != 'train':
                info['note'] = '验证任务仅累计适用证据；不生成结构修改'
                return
            graph = run.get('graph')
            if not graph or not run.get('plan') or not passed:
                info['note'] = '无通过评分的读取图或有效修复，失败保留待分析'
                return
            self.record_workflow(run, task, tools, info)
            if info.get('execution') == 'composition':
                info['note'] = 'Composition 正常训练轨迹已纳入 TinyEdge 支持；未从复用结果虚增完整图版本'
                return
            latest = self.latest(task, tools)
            if used and latest and latest['id'] != used['id']:
                info['note'] = '并发旧版本轨迹已记录；不覆盖已产生的后继版本'
                return
            parent = used
            if not parent:
                if latest and latest['status'] != 'needs-repair':
                    info['note'] = '并发冷启动已有版本，不重复生成'
                    return
                if graph['status'] != 'done':
                    info['note'] = '冷启动图未完整执行，保留恢复轨迹待分析'
                    return
                nodes = graph['nodes']
                # Cold graphs contain no task-specific literal parameters besides pagination.
                plan = self.safe_plan(run['plan'], nodes, tools)
                compiler_repair = info.get('compilerRepair')
                patches = [dict(operation='compile_observed_graph' if not latest else 'rebuild_after_failure',
                                reason='通用编译器语义/契约修复后重新保存读取结构' if compiler_repair else '正常训练任务完成，保存参数化读取结构',
                                origin='compiler_correctness_fix' if compiler_repair else 'normal_train_observation')]
                for node in nodes:
                    condition = (node.get('foreach') or {}).get('filter')
                    if condition:
                        patches.append(dict(operation='filter_then_enrich', nodeId=node['id'], sourceNodeId=node['foreach']['nodeId'],
                                            condition=deepcopy(condition), reason='规划语义绑定到已声明的列表字段；仅对命中记录调用详情工具',
                                            evidenceRunId=run['id']))
                parent = self.create(task, tools, run, nodes, plan, latest, patches)
                info['generatedVersionIds'].append(parent['id'])
                # Seed is not proof of improvement. A distinct child requires a real patch.
            nodes, patches = deepcopy(parent['nodes']), []
            if self.has_workspace_table_slots(nodes):
                info['graphOptimization'] = dict(
                    status='not_applicable',
                    reasonCode='workspace_table_slots',
                    reason='工作区图使用语义表槽；当前 runtime 可在执行前绑定当前资料表，但通用列表/详情编译器不重编译此类节点',
                )
                info['note'] = ('保存初始工作区图；通用补丁编译不适用，后续同契约任务可 Fast 绑定当前表槽'
                                if info['generatedVersionIds'] else
                                '工作区图已记录；通用补丁编译不适用，不将其误记为维护失败或虚构后继版本')
                return
            failures = [t for t in run.get('toolTrace', []) if t.get('executor') == 'graph' and t.get('ok') is False and t.get('nodeId')]
            repaired = []
            for failure in failures:
                # A successful model continuation is evidence for handing off this subgraph,
                # not proof that a general parameter repair has been learned.
                if any(t.get('executor') == 'model' and t.get('ok') is True and t['tool'] == failure['tool']
                       for t in run['toolTrace'][run['toolTrace'].index(failure) + 1:]):
                    repaired.append(failure)
            dag = nx.DiGraph()
            dag.add_nodes_from(n['id'] for n in nodes)
            dag.add_edges_from((d, n['id']) for n in nodes for d in n['dependencies'])
            for failure in repaired:
                affected = {failure['nodeId']} | nx.descendants(dag, failure['nodeId'])
                for node in nodes:
                    if node['id'] in affected and not node.get('defer'):
                        node['defer'] = True
                        patches.append(dict(operation='defer_subgraph', nodeId=node['id'], reason='图读取失败，当前任务中模型接管同一工具且最终评分通过',
                                            evidenceRunId=run['id'], failureTool=failure['tool']))
            if not failures:
                proposal = dict(nodes=[dict(id=n['id'], tool=n['tool']) for n in nodes])
                retrieval = {n['id']: [dict(name=n['tool'], score=1)] for n in nodes}
                optimized = compile_intent_graph(parent['plan'], proposal, retrieval, tools)
                by_id = {n['id']: n for n in optimized}
                for index, node in enumerate(nodes):
                    replacement = by_id[node['id']]
                    if not node.get('defer') and replacement.get('reuse') and not node.get('reuse'):
                        replacement['reuse']['onMissing'] = 'detail'
                        nodes[index] = replacement
                        patches.append(dict(operation='reuse_with_fallback', nodeId=node['id'], sourceNode=replacement['reuse']['nodeId'],
                                            fields=replacement['reuse']['fields'], reason='字段契约覆盖；运行时逐条校验，缺失时只补查该记录'))
            if patches:
                child = self.create(task, tools, run, nodes, parent['plan'], parent, patches)
                info['generatedVersionIds'].append(child['id'])
                info['note'] = '由正常任务轨迹生成后继图；下次任务使用，无额外 rollout'
            else:
                info['note'] = ('保存初始图；无进一步结构修改' if info['generatedVersionIds'] else '结构未变化，累计证据；不虚增版本') if not run.get('fallback') else '未提取可验证修复，保留问题；下次正常任务重新规划'
        finally:
            info['maintenanceMs'] = round((time.perf_counter() - started) * 1000, 3)
            info['persistMs'] = self.save()
