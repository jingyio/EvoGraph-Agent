from copy import deepcopy
import json
import pytest
from backend.llm_judge import LLMJudge
from backend.autotool import digest
from backend.paired_evaluation import summarize


class Bank:
    manifest = {'source': 'test'}
    def __init__(self, root): self.root = root
    def task(self, key): return dict(id=key, scenario='tickets', task='Count open tickets', recordIds=['1'])
    def record(self, task, key): return dict(id=key, state='open')


def fixture(tmp_path):
    class Runner: pass
    class Paired: pass
    runner = Runner(); runner.bank = Bank(tmp_path); runner.tasks = {}
    runner.runs = {k: dict(status='completed', submission=dict(summary=summary, metrics={'count': 1}, selectedIds=['1'], evidenceIds=['tickets:1']),
                          metrics={'inputTokens': 100, 'durationMs': 1000}, models={'executor': 'SECRET_MODEL_NAME'}) for k, summary in [('r1', 'report-one'), ('r2', 'report-two')]}
    paired = Paired(); paired.runner = runner; paired.tasks = {}
    paired.items = {'experiment': dict(protocol=dict(corpusHash=digest(runner.bank.manifest), arms=['plan_react', 'graph_rsi'], executor='executor'),
                       pairs=[dict(index=0, taskId='sample', runIds=dict(plan_react='r1', graph_rsi='r2'))])}
    return paired


class Judge:
    model = 'judge'
    def __init__(self, always_a=False, invalid=False): self.inputs=[]; self.always_a=always_a; self.invalid=invalid
    async def complete(self, messages, tools):
        self.inputs.append(deepcopy(messages))
        data = json.loads(messages[1]['content'])
        winner = 'A' if self.always_a or data['reports']['A']['summary'] == 'report-one' else 'B'
        verdict = dict(A=dict(factuality=4, coverage=4, readability=4), B=dict(factuality=4, coverage=4, readability=3), winner=winner,
                       rationale='test', findings={label: dict(claim='style', reason='test', evidenceRef='invalid' if self.invalid else 'tickets:1') for label in ['A','B']})
        verdict.pop('winner')
        verdict[winner]['readability'] = 4
        verdict['B' if winner == 'A' else 'A']['readability'] = 3
        return dict(message=dict(role='assistant', content=None, tool_calls=[dict(id='x', type='function', function=dict(name='submit_verdict', arguments=json.dumps(verdict)))]),
                    finishReason='tool_calls', usage={'input': 50, 'output': 20})


async def test_judge_blinding_swap_separate_cost_and_no_agent_mutation(tmp_path):
    paired = fixture(tmp_path); provider = Judge(); judge = LLMJudge(paired, lambda: provider)
    before = deepcopy(paired.runner.runs)
    item = await judge.start('experiment',0); await judge.tasks[item['id']]
    assert item['status'] == 'completed' and item['result']['winner'] == 'plan_react'
    assert item['metrics']['modelRequests'] == 2 and item['metrics']['inputTokens'] == 100
    assert paired.runner.runs == before
    first, second = [json.loads(p[1]['content']) for p in provider.inputs]
    assert first['reports']['A'] == second['reports']['B'] and first['evidence'] == second['evidence']
    assert all(v not in json.dumps(provider.inputs) for v in ['SECRET_MODEL_NAME','plan_react','graph_rsi','durationMs','inputTokens'])
    again = await judge.start('experiment',0)
    assert again['id'] == item['id'] and len(provider.inputs) == 2
    restored=LLMJudge(paired);restored.restore();assert restored.items[item['id']]['result']==item['result']


async def test_position_bias_is_inconclusive_and_bad_refs_fail(tmp_path):
    paired=fixture(tmp_path);judge=LLMJudge(paired,lambda:Judge(always_a=True))
    item=await judge.start('experiment',0);await judge.tasks[item['id']]
    assert item['result']['winner']=='inconclusive'
    judge=LLMJudge(paired,lambda:Judge(invalid=True))
    item=await judge.start('experiment',0);await judge.tasks[item['id']]
    assert item['status']=='failed' and item['metrics']['modelRequests']==1
    assert item['metrics']['inputTokens']==50


async def test_corpus_change_and_active_runs_block_judging(tmp_path):
    paired=fixture(tmp_path);judge=LLMJudge(paired,lambda:Judge())
    paired.runner.tasks={'active':None}
    with pytest.raises(ValueError): await judge.start('experiment',0)
    paired.runner.tasks={};paired.runner.bank.manifest={'changed':True}
    with pytest.raises(ValueError,match='数据集'):await judge.start('experiment',0)


def test_plan_baseline_aggregation_uses_actual_arm():
    def r(n):return dict(status='completed',evaluation={'status':'passed'},metrics=dict(inputTokens=n,outputTokens=1,usageComplete=True,durationMs=10,modelRequests=1,toolCalls=2,toolErrors=0))
    out=summarize([{'runs':dict(plan_react=r(100),graph_rsi=r(50))}],baseline='plan_react')
    assert out['arms']['plan_react']['attempts']==1 and out['bothPassedTokenDifference']==50


async def test_only_format_is_repaired_once_and_all_cost_is_recorded(tmp_path):
    class Malformed(Judge):
        async def complete(self, messages, tools):
            result = await super().complete(messages, tools)
            if len(self.inputs) == 1:
                args = json.loads(result['message']['tool_calls'][0]['function']['arguments'])
                args['findings'] = json.dumps(args['findings'])
                result['message']['tool_calls'][0]['function']['arguments'] = json.dumps(args)
            return result
    paired=fixture(tmp_path);provider=Malformed();judge=LLMJudge(paired,lambda:provider)
    item=await judge.start('experiment',0);await judge.tasks[item['id']]
    assert item['status']=='completed' and item['metrics']['modelRequests']==3
    assert item['metrics']['inputTokens']==150
    assert len(item['passes'][0]['attempts'])==2
    assert 'formatError' in item['passes'][0]['attempts'][0]
    # Second order never receives the first order's votes or repair context.
    assert len(provider.inputs[-1])==2


async def test_cancelled_judge_marks_unknown_usage_and_retains_attempt(tmp_path):
    import asyncio
    entered=asyncio.Event()
    class Waiting(Judge):
        async def complete(self,messages,tools):
            entered.set()
            await asyncio.Event().wait()
    judge=LLMJudge(fixture(tmp_path),lambda:Waiting())
    item=await judge.start('experiment',0);await entered.wait();await judge.shutdown()
    assert item['status']=='cancelled' and not item['metrics']['usageComplete']
    assert item['metrics']['modelRequests']==1 and not judge.tasks


def test_reward_scale_weights_and_order_average():
    from backend.llm_judge import report_reward, aggregate_verdicts
    assert report_reward(dict(factuality=0, coverage=0, readability=0)) == 0
    assert report_reward(dict(factuality=10, coverage=10, readability=10)) == 1
    assert report_reward(dict(factuality=8, coverage=9, readability=10)) == .87
    scores = {'left': dict(factuality=8, coverage=8, readability=8), 'right': dict(factuality=9, coverage=9, readability=9)}
    passes = [dict(scores=scores, rewards={k: report_reward(v) for k,v in scores.items()}, winner='right'),
              dict(scores=scores, rewards={k: report_reward(v) for k,v in scores.items()}, winner='left')]
    out = aggregate_verdicts(passes)
    assert out['reports']['right']['reward'] == .9
    assert out['winner'] == 'inconclusive'


async def test_judge_http_endpoints_return_rewards_without_changing_facts(tmp_path, monkeypatch):
    import httpx
    from backend.app import create_app
    from backend.service import RunService
    paired = fixture(tmp_path)
    bank = paired.runner.bank
    bank.load = lambda: None
    monkeypatch.setattr('backend.app.TaskBank', lambda: bank)
    app = create_app(RunService(tmp_path / 'legacy'))
    async with app.router.lifespan_context(app):
        app.state.task_runner.runs = paired.runner.runs
        app.state.paired.items = paired.items
        app.state.judge.factory = lambda: Judge()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            r = await client.post('/api/evaluations/experiment/judgements', json={'pairIndex': 0})
            assert r.status_code == 202
            key = r.json()['id']
            if key in app.state.judge.tasks:
                await app.state.judge.tasks[key]
            data = (await client.get('/api/evaluations/experiment/judgements')).json()
            item = next(j for j in data['items'] if j['id'] == key)
            assert item['scoreScale'] == [0, 10]
            assert 0 <= item['result']['reports']['plan_react']['reward'] <= 1
            assert (await client.post('/api/evaluations/experiment/judgements', json={'pairIndex': 10})).status_code == 422
            assert (await client.get('/api/evaluations/missing/judgements')).status_code == 404
