from scripts.run_online_e2e import TYPES, completed_status, judge_summary, result_report, rsi_source_pairs, selected_manifest, summary, task_manifest


class Bank:
    def task(self, task_id):
        scenario, family, suffix = task_id.rsplit('-', 2)
        return dict(id=task_id, split='train', scenario=scenario, family=family, task='read current records',
                    recordCount=2, recordIds=[suffix + '-a', suffix + '-b'], asOf='2026-09-10')


def run(task_id, status='completed', evaluation='passed', **extra):
    return dict(taskId=task_id, status=status, evaluation=dict(status=evaluation, issues=[]),
                metrics=dict(inputTokens=10, outputTokens=2, modelRequests=1, toolCalls=2, toolErrors=0,
                             durationMs=100, usageComplete=True, reportAttempts=1, failedReportAttempts=0,
                             reportRecoveryBlockedReads=0), **extra)


def test_online_manifest_has_fixed_distinct_train_instances():
    manifest = task_manifest(Bank())
    assert len(manifest) == 36
    assert len({row['taskId'] for row in manifest}) == 36
    assert [row['family'] for row in manifest[:6]] == [family for _, family in TYPES]
    assert [row['round'] for row in manifest[::6]] == [1, 2, 3, 4, 5, 6]
    assert [row['taskId'] for row in selected_manifest(Bank(), ['tickets-labels-02', 'finance-installments-01'])] == ['tickets-labels-02', 'finance-installments-01']


def test_online_summary_keeps_failures_and_local_maintenance():
    rows = [dict(round=1, taskId='finance-cancelled_payments-01', runs=dict(
        baseline=run('finance-cancelled_payments-01'),
        rsi=run('finance-cancelled_payments-01', status='failed', evaluation='failed', error='timeout',
                evolution=dict(planningPath='fast', lookupMs=1.2, maintenanceMs=3.4))))]
    report = summary(rows)
    assert report['arms']['rsi']['attempts'] == 1
    assert report['arms']['rsi']['passed'] == 0
    assert report['arms']['rsi']['failures'][0]['error'] == 'timeout'
    assert report['arms']['rsi']['diagnostics']['evolutionMaintenanceMs'] == 3.4
    assert report['arms']['rsi']['diagnostics']['reportAttempts'] == 1
    assert report['arms']['baseline']['p95LatencyMs'] == 100
    assert report['arms']['baseline']['maxTotalTokens'] == 12
    assert report['toolCallDelta'] == 0
    assert 'RSI' in result_report(dict(id='x', status='running', summary=report, rounds=[], evolutionChain=[]))


def test_judge_cost_stays_separate_from_agent_summary():
    rows = [dict(judge=dict(status='completed', sameAsExecutor=True,
                            metrics=dict(modelRequests=2, inputTokens=20, outputTokens=4, durationMs=30, usageComplete=True),
                            result=dict(winner='rsi', orderConsistent=True,
                                        reports=dict(baseline=dict(reward=.8), rsi=dict(reward=.9)))))]
    report = judge_summary(rows)
    assert report['totalTokens'] == 24 and report['modelRequests'] == 2
    assert report['rewards'] == dict(baseline=.8, rsi=.9)
    assert report['reportedTokenLowerBound'] == 24


def test_judge_summary_keeps_failure_reason_and_missing_usage_visible():
    report = judge_summary([dict(judge=dict(status='failed', error='provider_timeout'))])
    assert report['failed'] == 1
    assert report['usageComplete'] is False
    assert report['failureReasons'] == dict(provider_timeout=1)


def test_completed_rsi_only_run_does_not_remain_running_or_need_judge():
    assert completed_status(6, True) is True
    assert completed_status(5, True) is False
    assert completed_status(6, False) is False


def test_rsi_source_requires_matching_manifest_and_successful_isolated_runs():
    manifest = selected_manifest(Bank(), ['finance-cancelled_payments-01'])
    source = dict(schemaVersion=2, manifest=manifest,
                  protocol=dict(rsi='graph_rsi', rsiLearning=True, startFromEmpty=True),
                  pairs=[dict(taskId='finance-cancelled_payments-01', runs=dict(rsi=run('finance-cancelled_payments-01')))])
    selected = rsi_source_pairs(source, manifest)
    assert selected['finance-cancelled_payments-01']['runs']['rsi']['taskId'] == 'finance-cancelled_payments-01'
