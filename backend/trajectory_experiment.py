"""Frozen serial, paired trajectory experiment; all attempts remain in ledger."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from uuid import uuid4, UUID
from . import config, trajectory
from .domain import now
from .graph_store import write_private
from .task_runner import TaskRunner, TaskRunRequest
from .workspace import WorkspaceManager, WorkspaceBank
from .trajectory_assets_v3_r3 import VERSION, install


def fingerprint(root):
    files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'backend').glob('*.py'))}
    return {'files':files,'digest':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()}


def totals(runs):
    metrics=[r['metrics'] for r in runs]
    return {'attempts':len(runs),'passed':sum(r.get('evaluation',{}).get('status')=='passed' and r['status']=='completed' for r in runs),
            **{k:sum(m.get(k,0) or 0 for m in metrics) for k in ('modelRequests','modelProviderAttempts','modelTransportRetries','toolCalls','toolErrors','inputTokens','outputTokens','durationMs','runtimeOverheadMs','failedReportAttempts','recoveryToolCalls')},
            'tokens':sum(m['inputTokens']+m['outputTokens'] for m in metrics),
            'usageComplete':all(m['usageComplete'] for m in metrics)}


def summary(item):
    arms={arm:totals([p[arm] for p in item['pairs'] if p.get(arm)]) for arm in ('baseline','rsi')}
    curves=[];acc={'baseline':0,'rsi':0};lat={'baseline':0,'rsi':0};token_chain_complete=True
    for pair in item['pairs']:
        if pair.get('status') != 'completed' or not pair.get('baseline') or not pair.get('rsi'):continue
        costs={a:pair[a]['metrics']['inputTokens']+pair[a]['metrics']['outputTokens'] for a in acc}
        usage_complete=all(pair[a]['metrics'].get('usageComplete') for a in acc)
        if usage_complete and token_chain_complete:
            for a in acc:acc[a]+=costs[a]
        else:token_chain_complete=False
        for a in lat:lat[a]+=pair[a]['metrics']['durationMs']
        info=pair['rsi'].get('evolution',{})
        curves.append({'task':pair['spec']['id'],'group':pair['spec']['group'],'position':pair['spec']['position'],
                       'baselineTokens':costs['baseline'] if pair['baseline']['metrics'].get('usageComplete') else None,
                       'rsiTokens':costs['rsi'] if pair['rsi']['metrics'].get('usageComplete') else None,
                       'baselineLatencyMs':pair['baseline']['metrics']['durationMs'],'rsiLatencyMs':pair['rsi']['metrics']['durationMs'],
                       'baselinePassed':pair['baseline'].get('status')=='completed' and pair['baseline'].get('evaluation',{}).get('status')=='passed',
                       'rsiPassed':pair['rsi'].get('status')=='completed' and pair['rsi'].get('evaluation',{}).get('status')=='passed',
                       'tokenSaving':1-costs['rsi']/costs['baseline'] if usage_complete and costs['baseline'] else None,
                       'latencySaving':1-pair['rsi']['metrics']['durationMs']/pair['baseline']['metrics']['durationMs'] if pair['baseline']['metrics']['durationMs'] else None,
                       'cumulativeTokenSaving':1-acc['rsi']/acc['baseline'] if token_chain_complete and acc['baseline'] else None,
                       'cumulativeLatencySaving':1-lat['rsi']/lat['baseline'] if lat['baseline'] else None,
                       'G':info.get('generation'),'M':info.get('matchVersion'),'generatedG':info.get('generatedVersionIds',[]),'generatedM':info.get('generatedMatchVersions',[])})
    fast_runs = [pair['rsi'] for pair in item['pairs'] if pair.get('rsi')]
    fast_hits = [run for run in fast_runs if (run.get('evolution') or {}).get('planningPath') == 'fast']
    fast_rate = len(fast_hits) / len(fast_runs) if fast_runs else None
    fast_minimum = (item.get('protocol') or {}).get('fastReuseMinimumRate')
    fast_gate = fast_minimum is None or (fast_rate is not None and fast_rate >= fast_minimum)
    gate=(item['status']=='completed' and len(item['pairs'])==len(item['manifest'])
          and all(a['passed']==len(item['manifest']) and a['usageComplete'] for a in arms.values())
          and fast_gate)
    return {'arms':arms,'curves':curves,'qualityGate':gate,'costConclusionAllowed':gate,
            'fastReuse': {'hits': len(fast_hits), 'attempts': len(fast_runs), 'rate': fast_rate,
                          'minimumRate': fast_minimum, 'met': fast_gate},
            'netTokenSaving':1-arms['rsi']['tokens']/arms['baseline']['tokens'] if arms['baseline']['tokens'] else None}


class TrajectoryExperiment:
    def __init__(self,root):
        self.root=Path(root);self.directory=self.root/'artifacts/trajectory-experiments';self.items={};self.tasks={}
    def restore(self):
        for path in self.directory.glob('*/experiment.json'):
            item=json.loads(path.read_text())
            if item['status']=='running':item['status']='interrupted'
            self.items[item['id']]=item
    def save(self,item):write_private(self.directory/item['id']/'experiment.json',item)
    def get(self,key):
        item=deepcopy(self.items[key]);item['summary']=summary(item);return item
    def dashboard(self,key):
        item=self.get(key)
        item['pairs']=[dict(p,**{a:{k:v for k,v in p[a].items() if k in ('id','status','metrics','evaluation','evolution','error','phaseMetrics')} for a in ('baseline','rsi') if p.get(a)}) for p in item['pairs']]
        for pair in item['pairs']:
            for arm in ('baseline','rsi'):
                if pair.get(arm):pair[arm].get('evolution',{}).pop('trajectoryCompilation',None)
        return item
    def run(self,key,arm,run_id):
        if key not in self.items or arm not in ('baseline','rsi'):raise KeyError(arm)
        try: UUID(run_id)
        except ValueError: raise KeyError(run_id)
        if not any(p.get(arm, {}).get('id') == run_id for p in self.items[key]['pairs']): raise KeyError(run_id)
        return json.loads((self.directory/key/arm/'runs'/(run_id+'.json')).read_text())
    def task(self,key,run):
        manager=WorkspaceManager(self.directory/key);manager.restore();return manager.task(run['taskId'])
    async def start(self,mode='precheck'):
        if mode not in ('smoke','precheck','full'):raise ValueError('unknown stage')
        if self.tasks:raise ValueError('已有轨迹实验在途')
        asset_path=self.root/'artifacts'/VERSION/'manifest.json'
        if not asset_path.exists():raise ValueError('先准备并冻结任务资产')
        assets=json.loads(asset_path.read_text());fp=fingerprint(self.root)
        predecessor=None
        if mode=='full':
            predecessor=next((i for i in reversed(list(self.items.values())) if i['mode']=='precheck' and summary(i)['qualityGate'] and i['fingerprint']==fp),None)
            if not predecessor:raise ValueError('当前runtime预检未通过，禁止扩大')
        candidates=[s for s in assets['tasks'] if s['split']=='train' and (mode=='full' or s.get('precheck'))]
        # One pair only: a diagnostic smoke never becomes release evidence and
        # always starts from a fresh isolated RSI library.
        manifest=candidates[:1] if mode=='smoke' else candidates
        key=str(uuid4());directory=self.directory/key
        item={'id':key,'mode':mode,'status':'running','createdAt':now(),'assetVersion':VERSION,'fingerprint':fp,'manifest':manifest,'pairs':[],
              'predecessorId':predecessor['id'] if predecessor else None,
              'protocol':{'limits':{'run':1,'model':1,'read':1},'model':config.MODEL,'planner':config.PLANNER_MODEL,'runtimeProtocol':trajectory.PROTOCOL,
                          'maxModelRequestsPerRun':config.MAX_STEPS,'runTimeoutSeconds':config.RUN_TIMEOUT,
                          'maxToolCallsPerRun':80,'judge':'not_run','qualityPolicy':'stop expansion on first failing pair; retain all attempts',
                          'learning':'RSI empty library; prior successful normal train only; labels excluded from matching',
                          'windowSize':4,'targetTokenSaving':0.30,
                          'fastReuseMinimumRate':None if mode=='smoke' else 0.50,
                          'size':('1 paired F01 diagnostic smoke; does not qualify for release, precheck, or full expansion'
                                  if mode=='smoke' else '48 train = three scenarios × two sequential business cohorts × eight requests; 6 validation + 6 test reserved'),
                          'precheckSize':'12 train = each scenario two fixed requests from each cohort',
                          'fastReusePolicy':('not assessed in one-pair smoke; actual Fast reuse is assessed only in precheck/full'
                                             if mode=='smoke' else 'actual RSI Fast reuse must be at least 50% of completed RSI runs; otherwise this candidate cannot pass its release gate')}}
        self.items[key]=item;self.save(item)
        for relative in fp['files']:write_private(directory/'sources'/relative,(self.root/relative).read_text())
        write_private(directory/'frozen-assets-manifest.json',assets)
        async def work():
            manager=WorkspaceManager(directory);bank=WorkspaceBank(manager)
            runners={a:TaskRunner(bank,run_limit=1,model_limit=1,read_limit=1,learning_enabled=a=='rsi',run_directory=directory/a/'runs',evolution_path=directory/a/'experience.json') for a in ('baseline','rsi')}
            try:
                for index,spec in enumerate(manifest):
                    if fingerprint(self.root)!=fp:raise ValueError('runtime changed after freeze')
                    w,task=install(manager,self.root,spec)
                    pair={'spec':spec,'workspaceId':w['id'],'taskId':task['id'],'status':'running'};item['pairs'].append(pair);self.save(item)
                    for arm in (('baseline','rsi') if index%2==0 else ('rsi','baseline')):
                        runner=runners[arm]
                        run=await runner.start(TaskRunRequest(taskId=task['id'],strategy='plan_react' if arm=='baseline' else 'graph_rsi'))
                        pair[arm]=run;self.save(item)
                        await runner.tasks[run['id']]
                        self.save(item)
                    pair['status']='completed';self.save(item)
                    if any(pair[a]['status']!='completed' or pair[a]['evaluation']['status']!='passed' or not pair[a]['metrics']['usageComplete'] or pair[a].get('evolution',{}).get('maintenanceError') for a in runners):
                        item['status']='quality_stopped';break
                else:item['status']='completed'
            except asyncio.CancelledError:item['status']='cancelled'
            except Exception as error:item.update(status='failed',error=str(error)[:1000])
            finally:
                for runner in runners.values():await runner.shutdown()
                item['finishedAt']=now();item['summary']=summary(item);self.save(item);self.tasks.pop(key,None)
        self.tasks[key]=asyncio.create_task(work())
        return self.dashboard(key)
    async def shutdown(self):
        for task in list(self.tasks.values()):task.cancel()
        await asyncio.gather(*list(self.tasks.values()),return_exceptions=True)
