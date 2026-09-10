from scripts.run_online_e2e import TYPES, result_report, summary, task_manifest


class Bank:
    def task(self, task_id):
        scenario, family, suffix = task_id.rsplit('-', 2)
        return dict(id=task_id, split='train', scenario=scenario, family=family, task='read current records',
                    recordCount=2, recordIds=[suffix + '-a', suffix + '-b'], asOf='2026-09-10')


def run(task_id, status='completed', evaluation='passed', **extra):
    return dict(taskId=task_id, status=status, evaluation=dict(status=evaluation, issues=[]),
                metrics=dict(inputTokens=10, outputTokens=2, modelRequests=1, toolCalls=2, toolErrors=0,
                             durationMs=100, usageComplete=True, inertiaAttempts=0, inertiaAccepted=0,
                             inertiaCalls=0, inertiaErrors=0, inertiaRejected=0, inertiaQueryMs=0), **extra)


def test_online_manifest_has_fixed_distinct_train_instances():
    manifest = task_manifest(Bank())
    assert len(manifest) == 36
    assert len({row['taskId'] for row in manifest}) == 36
    assert [row['family'] for row in manifest[:6]] == [family for _, family in TYPES]
    assert [row['round'] for row in manifest[::6]] == [1, 2, 3, 4, 5, 6]


def test_online_summary_keeps_failures_and_local_maintenance():
    rows = [dict(round=1, taskId='finance-cancelled_payments-01', runs=dict(
        baseline=run('finance-cancelled_payments-01'),
        rsi=run('finance-cancelled_payments-01', status='failed', evaluation='failed', error='timeout',
                evolution=dict(planningPath='fast', lookupMs=1.2, maintenanceMs=3.4),
                toolInertiaMaintenance=dict(updatedPaths=1, updatedParameterEdges=1, updateMs=.2, persistMs=.3))))]
    report = summary(rows)
    assert report['arms']['rsi']['attempts'] == 1
    assert report['arms']['rsi']['passed'] == 0
    assert report['arms']['rsi']['failures'][0]['error'] == 'timeout'
    assert report['arms']['rsi']['diagnostics']['evolutionMaintenanceMs'] == 3.4
    assert report['arms']['rsi']['diagnostics']['inertiaUpdates'] == 1
    assert 'RSI' in result_report(dict(id='x', status='running', summary=report, rounds=[], evolutionChain=[]))
