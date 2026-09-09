import '../server/config.js';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { platformTools } from '../server/connectors.js';
import { createRun } from '../server/runtime.js';
import type { ToolContext } from '../server/tools.js';

/** Tests only the explicit RSI deployment seed; never points at arbitrary production data. */
async function verify(platform: 'erpnext' | 'zammad') {
  const baseUrl = process.env[platform.toUpperCase() + '_BASE_URL'];
  assert.equal(baseUrl, `http://127.0.0.1:${platform === 'erpnext' ? 18080 : 18081}`, 'Expected the local experiment tunnel');
  const tools = platformTools(platform);
  const context: ToolContext = { run: createRun({ scenario: platform === 'erpnext' ? 'finance' : 'support', source: platform, mode: 'live', task: 'Deployment validation' }, null), signal: AbortSignal.timeout(60000), evidence: new Set() };
  async function call(name: string, args: unknown = {}) { return await tools.find(tool => tool.name === name)!.execute(args, context) as any; }
  const records: any[] = [];
  for (let page = 1; page <= 5; page++) {
    const response = await call(platform === 'erpnext' ? 'erpnext_list_invoices' : 'zammad_list_tickets', { ...(platform === 'erpnext' ? { status: 'all' } : {}), page, pageSize: 2 });
    records.push(...response.records);
    if (!response.mayHaveMore) break;
  }
  assert.equal(records.length, 6);
  assert.equal(new Set(records.map(item => item.name ?? item.id)).size, 6, 'Pagination must not duplicate records');
  let details: Record<string, unknown>;
  let writeStatus: number;
  if (platform === 'erpnext') {
    assert.ok(records.every(row => row.name.startsWith('RSI-INV-') && row.currency === 'CNY'));
    assert.equal(records.reduce((sum, row) => sum + row.grand_total, 0), 66500);
    assert.equal(records.reduce((sum, row) => sum + row.outstanding_amount, 0), 24500);
    const payments = (await call('erpnext_list_payments', { page: 1, pageSize: 50 })).records;
    assert.equal(payments.length, 6);
    assert.equal(payments.filter((row: any) => row.reference_no === 'RSI-BANK-1004').length, 2);
    const partial = await call('erpnext_get_payment', { paymentId: 'RSI-PAY-002' });
    assert.equal(partial.references[0].reference_name, 'RSI-INV-002');
    assert.equal(partial.references[0].allocated_amount, 5000);
    const invoice = await call('erpnext_get_invoice', { invoiceId: 'RSI-INV-002' });
    assert.equal(invoice.outstanding_amount, 3500);
    const customer = await call('erpnext_get_customer', { customerId: invoice.customer });
    assert.equal(customer.name, 'RSI-CUST-02');
    const headers = { Authorization: `token ${process.env.ERPNEXT_API_KEY}:${process.env.ERPNEXT_API_SECRET}`, 'Content-Type': 'application/json' };
    // A same-value update can have no business effect even if unexpectedly permitted.
    const response = await fetch(`${baseUrl}/api/resource/Customer/${customer.name}`, { method: 'PUT', headers, body: JSON.stringify({ customer_name: customer.customer_name }), signal: context.signal });
    writeStatus = response.status;
    details = { invoices: 6, payments: 6, totalCny: 66500, outstandingCny: 24500, duplicateBankReferenceCount: 2, partialPaymentReferencesVerified: true };
  } else {
    assert.ok(records.every(row => row.title.startsWith('[RSI-')));
    const states = await call('zammad_list_states');
    const priorities = await call('zammad_list_priorities');
    const closedId = states.find((row: any) => row.name === 'closed')?.id;
    assert.equal(records.filter(row => row.state_id !== closedId).length, 5);
    assert.ok(priorities.some((row: any) => row.name === '3 high'));
    const overdue = records.find(row => row.title.startsWith('[RSI-1001]'));
    assert.ok(overdue.first_response_escalation_at, 'Seed SLA must calculate an actual deadline');
    const ticket = await call('zammad_get_ticket', { ticketId: overdue.id });
    const articles = await call('zammad_get_ticket_articles', { ticketId: overdue.id });
    assert.ok(articles.length > 0); assert.equal(ticket.id, overdue.id);
    const headers = { Authorization: `Token token=${process.env.ZAMMAD_API_TOKEN}`, 'Content-Type': 'application/json' };
    const response = await fetch(`${baseUrl}/api/v1/tickets/${ticket.id}`, { method: 'PUT', headers, body: JSON.stringify({ title: ticket.title }), signal: context.signal });
    writeStatus = response.status;
    const hidden = await fetch(`${baseUrl}/api/v1/tickets/1`, { headers, signal: context.signal });
    assert.equal(hidden.status, 403, 'Default example group must remain invisible to the RSI reader');
    details = { tickets: 6, activeTickets: 5, articleReadVerified: true, slaDeadlineVerified: true, defaultGroupAccess: 'denied' };
  }
  assert.equal(writeStatus, 403, 'Platform must reject writes from the reader credentials');
  return { platform, status: 'passed', paginationPageSize: 2, writeStatus, evidenceReferences: context.evidence.size, ...details };
}

const results = await Promise.all([verify('erpnext'), verify('zammad')]);
const report = { verifiedAt: new Date().toISOString(), results };
await mkdir('artifacts/platform-deployment', { recursive: true, mode: 0o700 });
await writeFile('artifacts/platform-deployment/verification.json', JSON.stringify(report, null, 2), { mode: 0o600 });
console.log(JSON.stringify(report, null, 2));
