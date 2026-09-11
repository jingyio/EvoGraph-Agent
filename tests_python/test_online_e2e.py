import re

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


def test_all_train_manifest_is_interleaved_by_family_instance():
    bank = Bank()
    bank.tasks = {
        f'{scenario}-{family}-{index:02d}': bank.task(f'{scenario}-{family}-{index:02d}')
        for scenario, family in [('finance', 'alpha'), ('support', 'beta')]
        for index in range(1, 7)
    }
    manifest = task_manifest(bank, 'all_train')
    assert len(manifest) == 12
    assert [row['round'] for row in manifest[:4]] == [1, 1, 2, 2]
    assert [row['taskId'] for row in manifest[:2]] == ['finance-alpha-01', 'support-beta-01']


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
    assert report['arms']['rsi']['runtimeOverheadMs'] == 0
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


def test_family_chart_uses_shared_axis_and_keeps_saving_polygon_in_viewbox():
    rows = []
    for index, (baseline_tokens, rsi_tokens) in enumerate([(20, 15), (25, 10)]):
        task_id = f'finance-cancelled_payments-0{index + 1}'
        rows.append(dict(index=index, round=index + 1, taskId=task_id, scenario='finance', family='cancelled_payments',
                         recordCount=1, runs=dict(
                             baseline=run(task_id, inputTokens=baseline_tokens, outputTokens=0),
                             rsi=run(task_id, inputTokens=rsi_tokens, outputTokens=0,
                                     evolution=dict(planningPath='fast')))))
    page = result_report(dict(id='chart', status='completed', protocol={}, pairs=rows, summary=summary(rows),
                              rounds=[], evolutionChain=[], judgeSummary={}))
    assert 'Cumulative token (absolute shared axis)' in page
    polygon = re.search(r'<polygon points="([^"]+)" class="saving-area"', page).group(1)
    x_values = [float(point.split(',')[0]) for point in polygon.split()]
    assert all(56 <= value <= 548 for value in x_values)


def test_report_separates_rsi_learning_health_from_baseline_reliability():
    task_id = 'finance-cancelled_payments-01'
    rows = [dict(index=0, round=1, taskId=task_id, scenario='finance', family='cancelled_payments', recordCount=1,
                 runs=dict(
                     baseline=run(task_id, reportAttempts=2, failedReportAttempts=1),
                     rsi=run(task_id, reportAttempts=1, failedReportAttempts=0, evolution=dict(
                         planningPath='fast', usedVersionId='workflow-1', generatedVersionIds=['workflow-1'],
                         tinyEdgeMaintenance=dict(workflowStatus='recorded', miningStatus='ok')))))]
    report = summary(rows)
    diagnostics = report['arms']['rsi']['diagnostics']
    assert diagnostics['fastSucceeded'] == 1
    assert diagnostics['initialWorkflowVersions'] == 1
    assert diagnostics['maintenanceRecorded'] == diagnostics['maintenanceMiningOk'] == 1
    page = result_report(dict(id='health', status='completed', protocol={}, pairs=rows, summary=report,
                              rounds=[], evolutionChain=[], judgeSummary={}))
    assert 'RSI 在线学习链路健康' in page
    assert '不是只统计首次失败' in page
    assert '不能据此声称长期零错误' in page
