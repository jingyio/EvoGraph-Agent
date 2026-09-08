import test from 'node:test';
import assert from 'node:assert/strict';
import { PRESETS, type Scenario } from '../shared/types.js';
import { createRun } from '../server/runtime.js';
import { sandboxTools, type ToolContext } from '../server/tools.js';
import { invoiceBalance, paymentBalance } from '../server/reports.js';

function fixture(scenario: Scenario = 'finance') {
  const run = createRun({ scenario, mode: 'fixture', source: 'sandbox', task: PRESETS[scenario] }, null);
  const context: ToolContext = { run, signal: new AbortController().signal, evidence: new Set() };
  const tools = sandboxTools(scenario);
  return { run, call: (name: string, args: unknown = {}) => tools.find(tool => tool.name === name)!.execute(args, context) };
}

test('one payment can settle multiple invoices, conserves cents, and retries idempotently', async () => {
  const { run, call } = fixture();
  const args = { paymentId: 'PAY-003', allocations: [{ invoiceId: 'INV-003', amountCents: 2000000 }, { invoiceId: 'INV-006', amountCents: 500000 }] };
  await call('allocate_payment', args); await call('allocate_payment', args);
  assert.equal(run.state.allocations.length, 2);
  assert.equal(invoiceBalance(run.state, 'INV-003'), 0);
  assert.equal(invoiceBalance(run.state, 'INV-006'), 0);
  assert.equal(paymentBalance(run.state, 'PAY-003'), 0);
  assert.equal(run.initial.allocations.length, 0);
});
test('partial payment leaves exact outstanding amount and remains overdue', async () => {
  const { run, call } = fixture();
  await call('allocate_payment', { paymentId: 'PAY-002', allocations: [{ invoiceId: 'INV-002', amountCents: 500000 }] });
  assert.equal(invoiceBalance(run.state, 'INV-002'), 350000);
  assert.ok((await call('list_overdue_invoices') as any[]).some(item => item.id === 'INV-002'));
});
test('invalid second allocation rolls back whole batch', async () => {
  const { run, call } = fixture();
  await assert.rejects(call('allocate_payment', { paymentId: 'PAY-003', allocations: [{ invoiceId: 'INV-003', amountCents: 2000000 }, { invoiceId: 'INV-006', amountCents: 600000 }] }), /exceeds/);
  assert.equal(run.state.allocations.length, 0);
});
test('duplicate bank records are both held and cannot be matched', async () => {
  const { run, call } = fixture();
  for (const paymentId of ['PAY-004', 'PAY-005']) {
    const preview = await call('preview_payment_match', { paymentId }) as any;
    assert.equal(preview.reason, 'duplicate_bank_reference');
    await assert.rejects(call('allocate_payment', { paymentId, allocations: [{ invoiceId: 'INV-004', amountCents: 600000 }] }), /Duplicate bank/);
  }
  assert.equal(invoiceBalance(run.state, 'INV-004'), 600000);
});
test('rejects cross-customer, duplicate invoice entries and fractional cents', async () => {
  const { run, call } = fixture();
  await assert.rejects(call('allocate_payment', { paymentId: 'PAY-001', allocations: [{ invoiceId: 'INV-002', amountCents: 100 }] }), /mismatch/);
  await assert.rejects(call('allocate_payment', { paymentId: 'PAY-001', allocations: [{ invoiceId: 'INV-001', amountCents: 100 }, { invoiceId: 'INV-001', amountCents: 100 }] }), /Duplicate invoice/);
  await assert.rejects(call('allocate_payment', { paymentId: 'PAY-001', allocations: [{ invoiceId: 'INV-001', amountCents: 0.1 }] }));
  assert.equal(run.state.allocations.length, 0);
});
test('case creation requires actual supporting evidence and is idempotent', async () => {
  const { run, call } = fixture();
  await assert.rejects(call('create_finance_case', { kind: 'duplicate', entityId: 'PAY-001', summary: 'duplicate', evidenceIds: ['PAY-001'] }), /Duplicate case/);
  const args = { kind: 'duplicate', entityId: 'PAY-004', summary: '核查相同银行流水', evidenceIds: ['PAY-004', 'PAY-005'] };
  await call('create_finance_case', args); await call('create_finance_case', args);
  assert.equal(run.state.cases.length, 1);
});
test('support assignment rejects unavailable, unskilled, stale, full and closed cases', async () => {
  const { run, call } = fixture('support');
  await assert.rejects(call('assign_ticket', { ticketId: 'T-1002', agentId: 'A-04', expectedVersion: 1 }), /unavailable/);
  await assert.rejects(call('assign_ticket', { ticketId: 'T-1002', agentId: 'A-01', expectedVersion: 1 }), /skill/);
  await assert.rejects(call('assign_ticket', { ticketId: 'T-1002', agentId: 'A-02', expectedVersion: 2 }), /Version/);
  await assert.rejects(call('assign_ticket', { ticketId: 'T-1006', agentId: 'A-03', expectedVersion: 1 }), /Closed/);
  run.state.agents.find(item => item.id === 'A-02')!.capacity = 1;
  await assert.rejects(call('assign_ticket', { ticketId: 'T-1002', agentId: 'A-02', expectedVersion: 1 }), /capacity/);
  assert.equal(run.state.tickets.find(item => item.id === 'T-1002')!.ownerId, null);
});
test('assignment retry preserves version; draft does not send or close ticket', async () => {
  const { run, call } = fixture('support');
  const args = { ticketId: 'T-1002', agentId: 'A-02', expectedVersion: 1 };
  await call('assign_ticket', args); await call('assign_ticket', args);
  await call('save_reply_draft', { ticketId: 'T-1002', body: '请提供请求 ID，勿发送密钥。', articleIds: ['KB-03'] });
  assert.equal(run.state.tickets.find(item => item.id === 'T-1002')!.version, 2);
  assert.equal(run.state.tickets.find(item => item.id === 'T-1002')!.status, 'open');
  assert.equal(run.state.drafts[0].sent, false);
  await assert.rejects(call('save_reply_draft', { ticketId: 'T-1002', body: '不适用的文章', articleIds: ['KB-01'] }), /category mismatch/);
});
test('tool schema rejects unknown properties rather than silently dropping them', async () => {
  const { call } = fixture();
  await assert.rejects(call('list_invoices', { arbitrary_sql: 'DELETE' }));
});
