from copy import deepcopy
import asyncio
from backend.evolution import EvolutionService, EvolutionRequest, acceptable
from backend.service import RunService
from backend.fixture_provider import FixtureProvider
from backend.runtime import execute_run


def test_promotion_requires_quality_and_cost():
    parent = {'status': 'completed', 'evaluation': {'status': 'passed'}, 'metrics': dict(usageComplete=True, modelRequests=8, toolErrors=0, inputTokens=100, outputTokens=10)}
    child = deepcopy(parent)
    child['metrics']['modelRequests'] = 7
    assert acceptable(parent, child)
    child['evaluation']['status'] = 'failed'
    assert not acceptable(parent, child)
    child['evaluation']['status'] = 'passed'
    child['metrics']['inputTokens'] = 200
    assert not acceptable(parent, child)


async def test_recursive_parent_lineage_and_stagnation(tmp_path, monkeypatch):
    class LiveFixture(FixtureProvider):
        kind, model = 'live', 'test-only'

    async def controlled(run, provider, tools, **kwargs):
        await execute_run(run, provider, tools, max_steps=100)
        run['metrics'].update(modelRequests=8 if kwargs.get('graph') is None else 6, inputTokens=100, outputTokens=10, usageComplete=True)
        return run

    monkeypatch.setattr('backend.evolution.execute_run', controlled)
    runs = RunService(tmp_path, lambda: LiveFixture('finance'))
    evolution = EvolutionService(runs)
    item = await evolution.start(EvolutionRequest(scenario='finance', rounds=3))
    await evolution.tasks[item['id']]
    assert item['status'] == 'completed'
    assert [r['status'] for r in item['rounds']] == ['promoted', 'stagnated']
    assert item['rounds'][1]['parentGraphId'] == item['rounds'][0]['candidate']['id']
    assert not runs.graphs.graphs
    restored = EvolutionService(runs)
    restored.restore()
    assert restored.items[item['id']]['activeGraph']['id'] == item['activeGraph']['id']


async def test_cancel_and_restart_record(tmp_path):
    runs = RunService(tmp_path, lambda: None)
    evolution = EvolutionService(runs)
    item = await evolution.start(EvolutionRequest())
    await evolution.shutdown()
    restored = EvolutionService(runs)
    restored.restore()
    assert restored.items[item['id']]['status'] in ['cancelled', 'interrupted']
