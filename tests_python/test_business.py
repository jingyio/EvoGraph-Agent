import copy
import pytest
from backend.domain import PRESETS, seed, invoice_balance, payment_balance
from backend.runtime import create_run, execute_run
from backend.tools import sandbox_tools, ToolContext
from backend.fixture_provider import FixtureProvider
from backend.evaluation import evaluate


def setup(scenario='finance', variant='base'):
    run = create_run({'scenario': scenario, 'mode': 'fixture', 'source': 'sandbox', 'task': PRESETS[scenario], 'snapshot': variant})
    tools = {t.name: t for t in sandbox_tools(scenario)}
    async def call(name, **args):
        return await tools[name].execute(args, ToolContext(run))
    return run, call


@pytest.mark.parametrize('scenario,calls', [('finance', 19), ('support', 21)])
async def test_offline_workflows_preserve_ts_baseline_results(scenario, calls):
    run, _ = setup(scenario)
    await execute_run(run, FixtureProvider(scenario), sandbox_tools(scenario), timeout=5)
    assert run['status'] == 'completed' and run['evaluation']['status'] == 'passed'
    assert run['metrics']['modelRequests'] == 0 and run['metrics']['toolCalls'] == calls
    assert run['initial'] == seed()
    if scenario == 'finance':
        assert sum(a['amountCents'] for a in run['state']['allocations']) == 4200000
        assert len(run['state']['cases']) == 5
    else:
        assert len(run['state']['drafts']) == 5 and len(run['state']['escalations']) == 2
        assert [t['status'] for t in run['state']['tickets']] == [t['status'] for t in run['initial']['tickets']]


async def test_multi_invoice_payment_and_idempotency():
    run, call = setup()
    args = {'paymentId': 'PAY-003', 'allocations': [{'invoiceId': 'INV-003', 'amountCents': 2000000}, {'invoiceId': 'INV-006', 'amountCents': 500000}]}
    await call('allocate_payment', **args)
    await call('allocate_payment', **args)
    assert len(run['state']['allocations']) == 2 and payment_balance(run['state'], 'PAY-003') == 0


async def test_partial_payment_keeps_overdue_balance():
    run, call = setup()
    await call('allocate_payment', paymentId='PAY-002', allocations=[{'invoiceId': 'INV-002', 'amountCents': 500000}])
    assert invoice_balance(run['state'], 'INV-002') == 350000
    assert any(i['id'] == 'INV-002' for i in await call('list_overdue_invoices'))


@pytest.mark.parametrize('payment,allocations', [
    ('PAY-004', [{'invoiceId': 'INV-004', 'amountCents': 600000}]),
    ('PAY-005', [{'invoiceId': 'INV-004', 'amountCents': 600000}]),
    ('PAY-001', [{'invoiceId': 'INV-002', 'amountCents': 100}]),
    ('PAY-001', [{'invoiceId': 'INV-001', 'amountCents': .1}]),
    ('PAY-003', [{'invoiceId': 'INV-003', 'amountCents': 2000000}, {'invoiceId': 'INV-006', 'amountCents': 600000}]),
    ('PAY-001', [{'invoiceId': 'INV-001', 'amountCents': 100}, {'invoiceId': 'INV-001', 'amountCents': 100}])])
async def test_invalid_allocations_are_atomic(payment, allocations):
    run, call = setup()
    with pytest.raises(ValueError):
        await call('allocate_payment', paymentId=payment, allocations=allocations)
    assert run['state']['allocations'] == []


async def test_cases_validate_evidence_and_are_idempotent():
    run, call = setup()
    with pytest.raises(ValueError):
        await call('create_finance_case', kind='duplicate', entityId='PAY-001', summary='false duplicate', evidenceIds=['PAY-001'])
    args = dict(kind='duplicate', entityId='PAY-004', summary='核查重复', evidenceIds=['PAY-004', 'PAY-005'])
    await call('create_finance_case', **args)
    await call('create_finance_case', **args)
    assert len(run['state']['cases']) == 1


@pytest.mark.parametrize('ticket,agent,version', [('T-1002', 'A-04', 1), ('T-1002', 'A-01', 1), ('T-1002', 'A-02', 2), ('T-1006', 'A-03', 1)])
async def test_assignment_guards(ticket, agent, version):
    run, call = setup('support')
    with pytest.raises(ValueError):
        await call('assign_ticket', ticketId=ticket, agentId=agent, expectedVersion=version)
    assert run['state'] == run['initial']


async def test_capacity_and_draft_guards():
    run, call = setup('support')
    run['state']['agents'][1]['capacity'] = 1
    with pytest.raises(ValueError):
        await call('assign_ticket', ticketId='T-1002', agentId='A-02', expectedVersion=1)
    await call('save_reply_draft', ticketId='T-1002', body='请提供去敏请求 ID', articleIds=['KB-03'])
    assert run['state']['drafts'][0]['sent'] is False
    with pytest.raises(ValueError):
        await call('save_reply_draft', ticketId='T-1002', body='wrong source', articleIds=['KB-01'])


async def test_evaluator_catches_missing_sla_escalations_even_after_assignment():
    run, _ = setup('support')
    await execute_run(run, FixtureProvider('support'), sandbox_tools('support'))
    run['state']['escalations'] = []
    result = evaluate(run, 'support_full')
    assert result['status'] == 'failed'
    assert {i['entityId'] for i in result['issues'] if i['code'] == 'missing_sla_escalation'} == {'T-1001', 'T-1003'}


def test_custom_read_task_does_not_gain_unrequested_write_requirements():
    run, _ = setup('support')
    run['request']['task'] = '只看一眼工单数量，不做任何修改'
    result = evaluate(run)
    assert result['scope'] == 'invariants' and result['status'] == 'passed'
