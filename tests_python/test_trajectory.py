"""Injected protocol tests, not real business/model evidence."""
from copy import deepcopy
import json
import pytest
from backend import trajectory
from backend.workspace import WorkspaceManager, WorkspaceBank
from backend.tools import ToolContext
from backend.online_evolution import OnlineEvolution
from backend.business_report import render_report


def setup(manager, request='差额严格大于5分，分期达到8期。'):
    w = manager.create('finance')
    tables = {'orders': [{'order_id': f'o{i}'} for i in range(1, 6)],
              'payments': [{'order_id': 'o1', 'amount_cents': 60, 'installments': 8}, {'order_id': 'o1', 'amount_cents': 45, 'installments': 2},
                           {'order_id': 'o2', 'amount_cents': 106, 'installments': 9}, {'order_id': 'o3', 'amount_cents': 300, 'installments': 1},
                           {'order_id': 'o5', 'amount_cents': 100, 'installments': 8}],
              'items': [{'order_id': 'o1', 'price_cents': 50, 'freight_cents': 0}, {'order_id': 'o1', 'price_cents': 50, 'freight_cents': 0},
                        {'order_id': 'o2', 'price_cents': 100, 'freight_cents': 0}, {'order_id': 'o4', 'price_cents': 20, 'freight_cents': 0}]}
    manager.add_source(w['id'], 'data.json', json.dumps(tables).encode())
    t, questions = manager.create_task(w['id'], request, split='train')
    assert not questions
    task = manager.task(t['id']); ids = task['tableBindings']
    args = {'anchorTableId': ids['orders'], 'keyField': 'order_id', 'aggregates': [
        {'tableId': ids['payments'], 'keyField': 'order_id', 'field': 'amount_cents', 'alias': 'paid'},
        {'tableId': ids['payments'], 'keyField': 'order_id', 'field': 'installments', 'alias': 'terms', 'operation': 'max'},
        {'tableId': ids['items'], 'keyField': 'order_id', 'field': 'price_cents', 'alias': 'price'},
        {'tableId': ids['items'], 'keyField': 'order_id', 'field': 'freight_cents', 'alias': 'freight'}],
        'derivedTotals': [{'name': 'line', 'aliases': ['price', 'freight']}],
        'comparisons': [{'name': 'difference', 'leftAlias': 'paid', 'rightAliases': ['line'], 'operator': 'abs_gt', 'threshold': 5},
                        {'name': 'terms', 'leftAlias': 'terms', 'operator': 'gte', 'threshold': 8}]}
    return task, {t.name: t for t in manager.tools(task['id'])}, args


def fragment_ids(proposal):
    return [node['id'] for node in proposal['nodes']]


def dependency_closure(proposal, *targets):
    nodes = {node['id']: node for node in proposal['nodes']}
    selected = set(targets)
    pending = list(targets)
    while pending:
        current = pending.pop()
        for dependency in nodes[current].get('dependencies') or []:
            if dependency not in selected:
                selected.add(dependency); pending.append(dependency)
    return [node['id'] for node in proposal['nodes'] if node['id'] in selected]


async def test_finance_many_to_many_missing_strict_boundary_overlap_and_current_evidence(tmp_path):
    m=WorkspaceManager(tmp_path); task, tools, args=setup(m)
    ctx=ToolContext({'id':'protocol'})
    out=await tools['workspace_reconcile_keyed_sums'].execute(args,ctx)
    assert out['anchorCount']==5
    assert out['totals']['paid']==611 and out['totals']['line']==220
    assert out['comparisons'][0]['keys']==['o2']  # o1 difference exactly 5; missing side excluded
    assert out['comparisons'][1]['keys']==['o1','o2','o5']  # independently eligible despite missing item
    assert out['perKey']['o3']['line'] is None
    assert out['perKey']['o4']['paid'] is None
    assert out['comparisons'][0]['incompleteKeys']==['o3','o4','o5']
    assert set(out['evidenceByKey']['o1']).issubset(ctx.evidence)
    assert len(set(out['evidenceByKey']['o1']))==5
    args['comparisons'][0]['threshold']=1000
    empty=await tools['workspace_reconcile_keyed_sums'].execute(args,ctx)
    assert empty['comparisons'][0]['count']==0 and empty['comparisons'][0]['keys']==[]


async def test_induction_never_plan_answers_and_current_nested_slots(tmp_path):
    m=WorkspaceManager(tmp_path); task, tools, args=setup(m)
    ctx=ToolContext({'id':'source'})
    out=await tools['workspace_reconcile_keyed_sums'].execute(args,ctx)
    run={'id':'source','status':'completed','evaluation':{'status':'passed'},'plan':{'nodes':[{'tool':'unexecuted'}]},
         'toolTrace':[{'ok':True,'tool':'workspace_reconcile_keyed_sums','arguments':args,'result':out}]}
    proposal=trajectory.induce(run,task,list(tools.values()))
    assert [node['fragmentType'] for node in proposal['nodes']].count('aggregate')==4
    assert [node['fragmentType'] for node in proposal['nodes']].count('derivedTotal')==1
    assert [node['fragmentType'] for node in proposal['nodes']].count('comparison')==2
    assert [node['fragmentType'] for node in proposal['nodes']].count('missing')==4
    assert len(proposal['descriptor']['slots'])==2
    assert 'o1' not in json.dumps(proposal)
    assert not set(task['tableBindings'].values()) & set(str(v) for _,v in trajectory.walk(proposal))
    g=dict(proposal,id='g0',generation=0,matchVersion=0)
    new, newtools, _=setup(m,'请复核差额严格大于10分且分期达到12期，各自独立。')
    new.update(family='poison',template='poison',workpackId='poison',difficulty='poison',privateValidation={'secret':'poison'})
    choice={'graphId':'g0','decision':'partial','nodeIds':fragment_ids(proposal),'bindings':[
        {'slot':key,'value':10 if slot['sourceValue']==5 else 12,'quote':new['task']} for key,slot in g['descriptor']['slots'].items()],
        'reason':'protocol test','uncovered':['report']}
    resolved=trajectory.bind_selection(choice,[g],new,list(newtools.values()))
    assert len(resolved['nodes'])==1
    assert resolved['nodes'][0]['arguments']['comparisons'][0]['threshold']==10
    assert resolved['nodes'][0]['arguments']['aggregates'][0]['tableId']==new['tableBindings']['payments']
    assert 'poison' not in json.dumps(trajectory.selection_prompt(new,[g]))
    choice['bindings'][0]['quote']='missing text'
    with pytest.raises(ValueError,match='来源'):
        trajectory.bind_selection(choice,[g],new,list(newtools.values()))


async def test_train_only_readonly_load_and_actual_child_use(tmp_path):
    m=WorkspaceManager(tmp_path); task, tools, args=setup(m)
    evolution=OnlineEvolution(WorkspaceBank(m),tmp_path/'g.json')
    trace={'ok':True,'tool':'workspace_reconcile_keyed_sums','arguments':args,'result':{}}
    run={'id':'one','status':'completed','evaluation':{'status':'passed'},'toolTrace':[trace]}
    evolution.observe(run,task,list(tools.values()))
    assert len(evolution.versions)==1
    before=(tmp_path/'g.json').read_bytes()
    restored=OnlineEvolution(WorkspaceBank(m),tmp_path/'g.json');restored.restore()
    assert trajectory.candidates(restored.versions,task,list(tools.values()),readonly=True)[0]==[]
    assert before==(tmp_path/'g.json').read_bytes()
    for split in ['test','validation','user']:
        other=dict(task,split=split)
        trajectory.maintain(restored,dict(run,id=split),other,list(tools.values()))
        assert len(restored.versions)==1
    failed=dict(run,id='failure',status='limited',evolution={'usedVersionId':restored.versions[0]['id']})
    trajectory.maintain(restored,failed,task,list(tools.values()))
    assert len(restored.versions)==1
    # A successfully observed new compute is a real protocol-level extension.
    second=deepcopy(run);second['id']='two';second['evolution']={'usedVersionId':restored.versions[0]['id']}
    second['toolTrace'].append({'ok':True,'tool':'workspace_aggregate_rows','arguments':{'tableId':task['tableBindings']['orders'],'operation':'count'},'result':{'rowCount':5}})
    trajectory.maintain(restored,second,task,list(tools.values()))
    assert len(restored.versions)==2 and restored.versions[-1]['generation']==1
    third=deepcopy(second);third['id']='three';third['evolution']={'usedVersionId':restored.versions[-1]['id'],'matchVersion':1}
    trajectory.maintain(restored,third,task,list(tools.values()))
    assert len(restored.versions)==2 and restored.versions[-1]['evidence'][0]['runId']=='three'


async def test_groups_empty_overlap_idempotent_report_and_html(tmp_path):
    m=WorkspaceManager(tmp_path);task,tools,args=setup(m)
    ctx=ToolContext({'id':'report','events':[]})
    out=await tools['workspace_reconcile_keyed_sums'].execute(args,ctx)
    groups=[{'name':name,'reason':name,'condition':'本次条件','count':len(ids),'selectedIds':ids,'evidenceIds':sorted(ctx.evidence) if ids else []}
            for name,ids in [('difference',['o2']),('terms',['o1','o2','o5']),('empty',[])]]
    report={'metrics':{'paid_cents':611},'selectedIds':['o1','o2','o5'],'evidenceIds':sorted(ctx.evidence),'summary':'原始分，显示BRL；仅内部复核。','groups':groups}
    a=await tools['workspace_publish_report'].execute(report,ctx)
    b=await tools['workspace_publish_report'].execute(report,ctx)
    assert a==b and len(m.workspace(task['workspaceId'])['reports'])==1
    html=render_report(ctx.run,task)
    assert 'BRL 6.11' in html and 'empty · 0 项' in html
    bad=deepcopy(report);bad['groups'][0]['count']=2
    assert (await tools['workspace_publish_report'].execute(bad,ctx))['evaluation']['status']=='failed'


def test_public_evidence_scope_does_not_use_private_truth():
    from backend.task_runner import TaskRunner
    task={'publicScopeEvidenceIds':['workspace:current:r1'], 'privateValidation':{'requiredEvidenceIds':['private:poison']}}
    args,receipt=TaskRunner.canonical_report_evidence(task,'workspace_publish_report',{'evidenceIds':[]},{'workspace:current:r1'})
    assert args['evidenceIds']==['workspace:current:r1'] and 'poison' not in json.dumps(receipt)


def test_unfinished_pairs_never_enter_savings_curves():
    from backend.trajectory_experiment import summary
    r={'status':'running','evaluation':{'status':'failed'},'metrics':{'inputTokens':10,'outputTokens':5,'usageComplete':True,'durationMs':1}}
    item={'status':'running','manifest':[{}],'pairs':[{'status':'running','baseline':r,'rsi':r}]}
    s=summary(item)
    assert s['curves']==[] and s['arms']['rsi']['tokens']==15 and not s['qualityGate']


def test_unknown_usage_breaks_token_curve_without_hiding_latency_or_failure():
    from backend.trajectory_experiment import summary
    def run(tokens,usage,status='passed',duration=100):
        return {'status':'completed','evaluation':{'status':status},
                'metrics':{'inputTokens':tokens,'outputTokens':0,'usageComplete':usage,'durationMs':duration}}
    pairs=[{'status':'completed','spec':{'id':'one','group':'g','position':1},'baseline':run(100,True),'rsi':run(50,True)},
           {'status':'completed','spec':{'id':'two','group':'g','position':2},'baseline':run(100,False,'failed'),'rsi':run(40,True,duration=80)},
           {'status':'completed','spec':{'id':'three','group':'g','position':3},'baseline':run(100,True),'rsi':run(30,True)}]
    curves=summary({'status':'quality_stopped','manifest':[{}, {}, {}],'pairs':pairs})['curves']
    assert curves[0]['tokenSaving']==.5 and curves[0]['cumulativeTokenSaving']==.5
    assert curves[1]['tokenSaving'] is None and curves[1]['cumulativeTokenSaving'] is None
    assert curves[2]['tokenSaving']==.7 and curves[2]['cumulativeTokenSaving'] is None
    assert curves[1]['latencySaving']==pytest.approx(.2) and not curves[1]['baselinePassed']


async def test_group_row_ids_bound_only_to_current_observations(tmp_path):
    from backend.task_runner import TaskRunner,TaskRunRequest
    from test_workspace import response
    m=WorkspaceManager(tmp_path);task,tools,args=setup(m)
    expected=[]
    class Model:
        model='injected-group-evidence-protocol';settings={}
        async def complete(self,messages,available):
            if any(t.name=='submit_plan' for t in available):
                return response('submit_plan',{'steps':[{'id':'orders','intent':'读取订单','dependencies':[],'sourceTable':'orders'}]})
            obs=[json.loads(x['content']) for x in messages if x.get('role')=='tool']
            rows=[r for o in obs for r in (o.get('result') or {}).get('records',[])]
            if not rows:
                return response('workspace_preview_rows',{'tableId':task['tableBindings']['orders'],'page':1,'pageSize':50})
            ref=rows[0]['_evidenceRef'];expected.append(ref)
            return response('workspace_publish_report',{'metrics':{},'selectedIds':['o1'],'evidenceIds':[ref], 'summary':'注入协议测试，不是业务实证',
                'groups':[{'name':'one','reason':'test','condition':'test','count':1,'selectedIds':['o1'],'evidenceIds':[rows[0]['rowId']]}]})
    runner=TaskRunner(WorkspaceBank(m),lambda role:Model(),learning_enabled=False,run_directory=tmp_path/'runs')
    run=await runner.start(TaskRunRequest(taskId=task['id'],strategy='plan_react'))
    await runner.tasks[run['id']]
    assert run['evaluation']['status']=='user_review_required'
    assert run['submission']['groups'][0]['evidenceIds']==[expected[0]]
    assert any(e['type']=='group_evidence_binding' for e in run['events'])
    await runner.shutdown()


async def test_matching_schema_revision_changes_later_recall_without_new_graph(tmp_path):
    m=WorkspaceManager(tmp_path);task,tools,args=setup(m)
    evo=OnlineEvolution(WorkspaceBank(m),tmp_path/'experience.json')
    trace={'ok':True,'tool':'workspace_preview_rows','arguments':{'tableId':task['tableBindings']['orders'],'page':1,'pageSize':50},'result':{'records':[],'mayHaveMore':False}}
    first={'id':'first','status':'completed','evaluation':{'status':'passed'},'toolTrace':[trace]}
    trajectory.maintain(evo,first,task,list(tools.values()))
    current=deepcopy(task)
    current['schemaContract']['tables'][0]['types']['freight_cents']='number'
    assert trajectory.candidates(evo.versions,current,list(tools.values()))[0]==[]
    next_run=dict(first,id='current',evolution={})
    trajectory.maintain(evo,next_run,current,list(tools.values()))
    assert len(evo.versions)==1 and evo.versions[0]['generation']==0 and evo.versions[0]['matchVersion']==1
    assert next_run['evolution']['generatedVersionIds']==[]
    assert trajectory.candidates(evo.versions,current,list(tools.values()))[0][0]['matchVersion']==1
    evo.save();before=(tmp_path/'experience.json').read_bytes()
    evo.observe(dict(first,id='test'),dict(current,split='test'),list(tools.values()))
    assert (tmp_path/'experience.json').read_bytes()==before


async def test_report_idempotency_respects_new_evidence_and_current_call_result(tmp_path):
    m=WorkspaceManager(tmp_path);task,tools,args=setup(m)
    evidence_context=ToolContext({'id':'read'})
    await tools['workspace_reconcile_keyed_sums'].execute(args,evidence_context)
    report={'metrics':{},'selectedIds':[],'evidenceIds':sorted(evidence_context.evidence),'summary':'protocol test'}
    ctx=ToolContext({'id':'report'})
    first=await tools['workspace_publish_report'].execute(report,ctx)
    assert first['evaluation']['status']=='failed'
    ctx.evidence.update(evidence_context.evidence)
    second=await tools['workspace_publish_report'].execute(report,ctx)
    assert second['evaluation']['status']=='user_review_required' and first['reportId']!=second['reportId']
    bad=dict(report,evidenceIds=['unobserved'])
    failed=await tools['workspace_publish_report'].execute(bad,ctx)
    assert ctx.run['evaluation']['status']=='failed'
    good_cached=await tools['workspace_publish_report'].execute(report,ctx)
    assert good_cached==second and ctx.run['evaluation']['status']=='user_review_required'
    bad_cached=await tools['workspace_publish_report'].execute(bad,ctx)
    assert bad_cached==failed and ctx.run['evaluation']['status']=='failed'

async def test_induction_records_explicit_nested_output_binding_and_replays_current_output(tmp_path):
    m=WorkspaceManager(tmp_path);task,tools,_=setup(m)
    ctx=ToolContext({'id':'source'})
    preview_args={'tableId':task['tableBindings']['orders'],'page':1,'pageSize':50}
    preview=await tools['workspace_preview_rows'].execute(preview_args,ctx)
    row_args={'tableId':task['tableBindings']['orders'],'rowId':preview['records'][0]['rowId']}
    row=await tools['workspace_get_row'].execute(row_args,ctx)
    run={'id':'nested','status':'completed','evaluation':{'status':'passed'},'toolTrace':[
        {'ok':True,'tool':'workspace_preview_rows','arguments':preview_args,'result':preview},
        {'ok':True,'tool':'workspace_get_row','arguments':row_args,'result':row,
         'argumentSources':{'rowId':{'$output':{'traceIndex':0,'path':['records',0,'rowId']}}}},
    ]}
    proposal=trajectory.induce(run,task,list(tools.values()))
    assert proposal['nodes'][1]['dependencies']==['t0']
    assert proposal['nodes'][1]['arguments']['rowId']=={'$output':{'nodeId':'t0','path':['records',0,'rowId']}}
    version=dict(proposal,id='nested-g',generation=0,matchVersion=0)
    choice={'graphId':'nested-g','decision':'partial','nodeIds':['t0','t1'],'bindings':[], 'reason':'nested protocol', 'uncovered':['report']}
    selected=trajectory.bind_selection(choice,[version],task,list(tools.values()))
    first=trajectory.resolve_arguments(selected['nodes'][0]['arguments'],task,selected['currentBindings'],{})
    second=trajectory.resolve_arguments(selected['nodes'][1]['arguments'],task,selected['currentBindings'],{'t0':preview})
    assert first==preview_args and second==row_args


def test_multi_fragment_selection_rejects_duplicate_and_accepts_independent_dag(tmp_path):
    m=WorkspaceManager(tmp_path);task,tools,_=setup(m)
    contract=trajectory.api_hash(list(tools.values()))
    def graph(key,tool,args):
        return {'id':key,'protocol':trajectory.PROTOCOL,'generation':0,'matchVersion':0,'contractHash':contract,
                'descriptor':{'schema':task['schemaContract'],'slots':{},'purpose':'当前附件复核'},
                'nodes':[{'id':'t0','tool':tool,'arguments':args,'dependencies':[],'effect':'read','paginate':False}],
                'plan':{'steps':[]}}
    one=graph('one','workspace_preview_rows',{'tableId':{'$table':'orders'},'page':1,'pageSize':50})
    two=graph('two','workspace_get_schema',{})
    choice={'decision':'partial','reason':'independent fragments','uncovered':['report'],'selections':[
        {'graphId':'one','nodeIds':['t0'],'bindings':[]}, {'graphId':'two','nodeIds':['t0'],'bindings':[]},
    ]}
    selected=trajectory.bind_selection(choice,[one,two],task,list(tools.values()))
    assert selected['sourceVersionIds']==['one','two']
    assert [node['id'] for node in selected['nodes']]==['c0_t0','c1_t0']
    with pytest.raises(ValueError,match='重复'):
        trajectory.bind_selection(choice,[one,dict(one,id='two')],task,list(tools.values()))

async def test_brl_threshold_is_auditable_cents_slot_and_rebinds_current_value(tmp_path):
    manager = WorkspaceManager(tmp_path)
    source, tools, arguments = setup(manager, '请复核差额严格超过 0.05 BRL、最大分期达到 8 期及以上。')
    context = ToolContext({'id': 'source-brl'})
    result = await tools['workspace_reconcile_keyed_sums'].execute(arguments, context)
    run = {'id': 'source-brl', 'status': 'completed', 'evaluation': {'status': 'passed'}, 'toolTrace': [
        {'ok': True, 'tool': 'workspace_reconcile_keyed_sums', 'arguments': arguments, 'result': result},
    ]}
    proposal = trajectory.induce(run, source, list(tools.values()))
    assert proposal['nodes'][0]['tool'] == 'workspace_reconcile_keyed_sums'
    transformed = next((name, slot) for name, slot in proposal['descriptor']['slots'].items() if slot.get('transform'))
    assert transformed[1]['sourceValue'] == .05
    assert transformed[1]['transform'] == {'kind': 'scale', 'factor': 100, 'resultType': 'int'}

    current, current_tools, _ = setup(manager, '请复核差额严格超过 0.10 BRL、最大分期达到 12 期及以上。')
    version = dict(proposal, id='brl-g0', generation=0, matchVersion=0)
    bindings = []
    for name, slot in proposal['descriptor']['slots'].items():
        if slot.get('transform'):
            bindings.append({'slot': name, 'value': .10, 'quote': '0.10 BRL'})
        else:
            bindings.append({'slot': name, 'value': 12, 'quote': '12 期'})
    selected = trajectory.bind_selection({
        'graphId': 'brl-g0', 'decision': 'partial', 'nodeIds': fragment_ids(proposal), 'bindings': bindings,
        'reason': '当前阈值已重新绑定', 'uncovered': ['report'],
    }, [version], current, list(current_tools.values()))
    comparison = selected['nodes'][0]['arguments']['comparisons']
    assert comparison[0]['threshold'] == 10
    assert comparison[1]['threshold'] == 12


async def test_reconcile_fragments_keep_valid_clauses_and_merge_one_physical_call(tmp_path):
    manager = WorkspaceManager(tmp_path)
    source, tools, arguments = setup(manager)
    arguments['comparisons'].extend([
        {'name': 'unbound', 'leftAlias': 'paid', 'operator': 'gt', 'threshold': 777},
        {'name': 'missing_payment', 'leftAlias': 'paid', 'operator': 'equals', 'threshold': 0},
        {'name': 'missing_items', 'leftAlias': 'price', 'operator': 'equals', 'threshold': 0},
    ])
    result = await tools['workspace_reconcile_keyed_sums'].execute(arguments, ToolContext({'id': 'fragment-source'}))
    proposal = trajectory.induce({
        'id': 'fragment-source', 'status': 'completed', 'evaluation': {'status': 'passed'},
        'toolTrace': [{'ok': True, 'tool': 'workspace_reconcile_keyed_sums', 'arguments': arguments, 'result': result}],
    }, source, list(tools.values()))
    comparisons = [node for node in proposal['nodes'] if node.get('fragmentType') == 'comparison']
    assert [node['arguments']['name']['$literal'] for node in comparisons] == ['difference', 'terms']
    assert any(boundary.get('fragmentType') == 'comparison' and boundary.get('name') == 'unbound'
               for boundary in proposal['descriptor']['modelBoundaries'])
    assert {'missing_payment', 'missing_items'}.issubset({
        boundary.get('name') for boundary in proposal['descriptor']['modelBoundaries']
        if boundary.get('fragmentType') == 'comparison'
    })
    assert len([node for node in proposal['nodes'] if node.get('fragmentType') == 'aggregate']) == 4
    assert len([node for node in proposal['nodes'] if node.get('fragmentType') == 'missing']) == 4

    current, current_tools, _ = setup(manager, '差额严格大于10分，分期达到12期。')
    bindings = [
        {'slot': name, 'value': 10 if slot['sourceValue'] == 5 else 12, 'quote': current['task']}
        for name, slot in proposal['descriptor']['slots'].items()
    ]
    selected = trajectory.bind_selection({
        'graphId': 'fragment-g0', 'decision': 'partial', 'nodeIds': fragment_ids(proposal),
        'bindings': bindings, 'reason': '保留可验证片段', 'uncovered': ['report'],
    }, [dict(proposal, id='fragment-g0', generation=0, matchVersion=0)], current, list(current_tools.values()))
    assert len(selected['nodes']) == 1
    physical = selected['nodes'][0]
    assert physical['tool'] == 'workspace_reconcile_keyed_sums'
    assert len(physical['arguments']['aggregates']) == 4
    assert len(physical['arguments']['derivedTotals']) == 1
    assert [item['threshold'] for item in physical['arguments']['comparisons']] == [10, 12]
    assert set(physical['missingAliases']) == {'paid', 'terms', 'price', 'freight'}


async def test_reconcile_fragment_dependency_closure_and_missing_clause(tmp_path):
    manager = WorkspaceManager(tmp_path)
    task, tools, arguments = setup(manager)
    result = await tools['workspace_reconcile_keyed_sums'].execute(arguments, ToolContext({'id': 'closure-source'}))
    proposal = trajectory.induce({
        'id': 'closure-source', 'status': 'completed', 'evaluation': {'status': 'passed'},
        'toolTrace': [{'ok': True, 'tool': 'workspace_reconcile_keyed_sums', 'arguments': arguments, 'result': result}],
    }, task, list(tools.values()))
    version = dict(proposal, id='closure-g0', generation=0, matchVersion=0)
    derived = next(node for node in proposal['nodes'] if node.get('fragmentType') == 'derivedTotal')
    comparison = next(node for node in proposal['nodes'] if node.get('fragmentType') == 'comparison')
    with pytest.raises(ValueError, match='依赖'):
        trajectory.bind_selection({'graphId': 'closure-g0', 'decision': 'partial', 'nodeIds': [derived['id']],
                                   'bindings': [], 'reason': '缺少依赖', 'uncovered': []},
                                  [version], task, list(tools.values()))
    with pytest.raises(ValueError, match='依赖'):
        trajectory.bind_selection({'graphId': 'closure-g0', 'decision': 'partial', 'nodeIds': [comparison['id']],
                                   'bindings': [], 'reason': '缺少依赖', 'uncovered': []},
                                  [version], task, list(tools.values()))

    paid_missing = next(node for node in proposal['nodes']
                        if node.get('fragmentType') == 'missing' and node['arguments']['alias']['$literal'] == 'paid')
    selected = trajectory.bind_selection({
        'graphId': 'closure-g0', 'decision': 'partial',
        'nodeIds': dependency_closure(proposal, paid_missing['id']), 'bindings': [],
        'reason': '只复用支付缺失检查', 'uncovered': ['other clauses', 'report'],
    }, [version], task, list(tools.values()))
    assert len(selected['nodes']) == 1
    assert selected['nodes'][0]['arguments']['aggregates'] == [{
        'tableId': task['tableBindings']['payments'], 'keyField': 'order_id',
        'field': 'amount_cents', 'alias': 'paid',
    }]
    assert selected['nodes'][0]['missingAliases'] == ['paid']
    replayed = await tools['workspace_reconcile_keyed_sums'].execute(
        selected['nodes'][0]['arguments'], ToolContext({'id': 'closure-replay'}))
    assert replayed['missingByAlias']['paid'] == ['o4']

    corrupted = deepcopy(version)
    target = next(node for node in corrupted['nodes'] if node.get('fragmentType') == 'comparison')
    target['arguments']['leftAlias'] = {'$literal': 'unknown_alias'}
    ids = dependency_closure(corrupted, target['id'])
    bindings = [{'slot': name, 'value': slot['sourceValue'], 'quote': task['task']}
                for name, slot in corrupted['descriptor']['slots'].items() if slot['nodeId'] in ids]
    with pytest.raises(ValueError, match='别名'):
        trajectory.bind_selection({'graphId': 'closure-g0', 'decision': 'partial', 'nodeIds': ids,
                                   'bindings': bindings, 'reason': '损坏别名', 'uncovered': []},
                                  [corrupted], task, list(tools.values()))


def test_trajectory_contract_hash_ignores_dynamic_artifact_delivery_schema(tmp_path):
    manager = WorkspaceManager(tmp_path)
    task, tools, _ = setup(manager)
    original = trajectory.api_hash(list(tools.values()))
    changed = deepcopy(list(tools.values()))
    report = next(tool for tool in changed if tool.name == 'workspace_publish_report')
    report.parameters = {'type': 'object', 'properties': {'new_public_group': {'type': 'string'}}}
    assert trajectory.api_hash(changed) == original
