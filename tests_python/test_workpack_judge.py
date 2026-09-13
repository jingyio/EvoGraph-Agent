import asyncio
import json

from backend.workpack_judge import WorkpackJudge


class Provider:
    model = 'judge-model'

    def __init__(self):
        self.calls = []

    async def complete(self, messages, tools):
        self.calls.append(messages)
        payload = json.loads(messages[1]['content'])
        reference = next(iter(payload['evidence']))
        verdict = {
            'A': {'factuality': 8, 'coverage': 8, 'readability': 8},
            'B': {'factuality': 8, 'coverage': 8, 'readability': 8},
            'rationale': 'same observed evidence',
            'findings': {
                'A': {'claim': 'none', 'reason': 'no material difference', 'evidenceRef': reference},
                'B': {'claim': 'none', 'reason': 'no material difference', 'evidenceRef': reference},
            },
        }
        return {'message': {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'verdict', 'type': 'function', 'function': {'name': 'submit_verdict', 'arguments': json.dumps(verdict)}}]},
            'finishReason': 'tool_calls', 'usage': {'input': 20, 'output': 10}}


class Manager:
    def __init__(self, reference):
        _, workspace_id, row_id = reference.split(':', 2)
        self.workspaces = {workspace_id: {'id': workspace_id, 'tables': {
            'rows': {'sheet': 'records', 'rows': [{'rowId': row_id, 'values': {'id': 'one', 'state': 'open'}}]},
        }}}


class Experiments:
    def __init__(self, root):
        self.root = root
        self.tasks = {}
        self.reference = 'workspace:ws:source:records:2'
        self.run = {
            'events': [{'type': 'report_evidence', 'detail': {'requiredEvidenceIds': [self.reference]}}],
            'submission': {'metrics': {'count': 1}, 'selectedIds': ['one'], 'evidenceIds': [self.reference], 'summary': 'report'},
        }
        compact = {'id': 'run', 'submission': self.run['submission'], 'models': {'executor': 'judge-model'}}
        self.item = {'id': 'experiment', 'status': 'completed', 'pairs': [
            {'index': 1, 'workpackId': 'finance-one', 'runs': {'baseline': compact, 'rsi': compact}},
            {'index': 2, 'workpackId': 'finance-missing', 'runs': {'baseline': compact, 'rsi': {'id': 'missing'}}},
        ]}

    def get(self, key):
        assert key == 'experiment'
        return self.item

    def run_with_task(self, key, arm, run_id):
        assert key == 'experiment'
        return self.run, {'scenario': 'finance', 'task': 'Count open records', 'privateValidation': {'secret': True}}


async def test_workpack_judge_keeps_missing_reports_unscored_and_cost_separate(tmp_path):
    experiments = Experiments(tmp_path)
    provider = Provider()
    judge = WorkpackJudge(experiments, tmp_path, lambda: provider)
    judge._manager = lambda *_args: Manager(experiments.reference)

    item = await judge.start('experiment')
    await judge.tasks[item['id']]
    saved = judge.get(item['id'])

    assert saved['status'] == 'completed'
    assert saved['metrics']['modelRequests'] == 2
    assert saved['metrics']['inputTokens'] == 40
    assert saved['summary']['completedPairs'] == 1
    assert saved['summary']['notScoredPairs'] == 1
    assert saved['pairs'][1]['status'] == 'not_scored_missing_report'
    prompt = json.dumps(provider.calls)
    assert 'privateValidation' not in prompt and 'secret' not in prompt
    assert 'plan_react' not in prompt and 'graph_rsi' not in prompt


def test_workpack_judge_protocol_discloses_normal_and_maximum_request_counts(tmp_path):
    experiment = Experiments(tmp_path)
    protocol = WorkpackJudge(experiment, tmp_path).protocol('experiment')
    assert protocol['eligiblePairs'] == 1
    assert protocol['normalModelRequests'] == 2
    assert protocol['maximumModelRequestsWithOneFormatRepairPerOrder'] == 4
