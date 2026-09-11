from backend.showcase import _timeline_event, audit_submission


def task():
    return {'scenario': 'finance', 'recordIds': ['a' * 32], 'recordCount': 1}


def run(summary='1 条订单，金额为 120 分。'):
    return {
        'submission': {
            'metrics': {'count': 1, 'paid_cents': 120},
            'selectedIds': ['a' * 32],
            'evidenceIds': ['finance:' + 'a' * 32],
            'summary': summary,
        },
        'events': [{'type': 'observation', 'detail': {'result': {
            'id': 'a' * 32, '_evidenceRef': 'finance:' + 'a' * 32, 'amount_cents': 120,
        }}}],
    }


def expected():
    return {'metrics': {'count': 1, 'paid_cents': 120}, 'selectedIds': ['a' * 32], 'ordered': False}


def test_strict_audit_keeps_structured_result_separate_from_summary_unit_quality():
    result = audit_submission(task(), expected(), run('1 条订单，金额为 120 BRL分。'))
    assert result['strictStructuredPass'] is True
    assert result['currencyNotationClear'] is False
    assert result['strictReportAuditPass'] is False
    assert 'ambiguous_currency_notation' in result['issues']


def test_strict_audit_rejects_unobserved_evidence_and_ungrounded_number():
    candidate = run('订单金额为 999 分。')
    candidate['submission']['evidenceIds'] = ['finance:' + 'b' * 32]
    result = audit_submission(task(), expected(), candidate)
    assert result['evidenceExact'] is False
    assert result['evidenceObserved'] is False
    assert result['summaryNumbersGrounded'] is False


def test_timeline_event_exposes_saved_cumulative_metrics_without_event_detail():
    event = {
        'type': 'action', 'title': 'finance_list_orders',
        'detail': {'arguments': '{"page": 1}', 'callId': 'opaque'},
        'metrics': {'modelRequests': 2, 'toolCalls': 1, 'inputTokens': 120, 'outputTokens': 30, 'durationMs': 500},
    }
    result = _timeline_event(event, 4)
    assert result == {
        'position': 4, 'kind': 'action', 'channel': 'control', 'title': '调用工具：finance_list_orders', 'executor': None, 'nodeId': None, 'elapsedMs': 500.0,
        'metrics': {'modelRequests': 2, 'toolCalls': 1, 'inputTokens': 120, 'outputTokens': 30, 'durationMs': 500, 'filteredOutDetailReads': 0, 'deterministicBindings': 0},
    }


def test_timeline_event_marks_graph_owned_tool_calls_as_structured_execution():
    event = {
        'type': 'action', 'title': 'finance_get_order_payments',
        'detail': {'executor': 'graph', 'nodeId': 'get_payments'},
        'metrics': {'modelRequests': 1, 'toolCalls': 3, 'durationMs': 700},
    }
    result = _timeline_event(event, 7)
    assert result['channel'] == 'structured'
    assert result['executor'] == 'graph'
    assert result['nodeId'] == 'get_payments'
