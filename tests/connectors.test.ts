import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { JsonConnector, erpnextTools, zammadTools } from '../server/connectors.js';
import { createRun } from '../server/runtime.js';
import type { ToolContext } from '../server/tools.js';

const context = (source: 'erpnext' | 'zammad'): ToolContext => ({ run: createRun({ scenario: source === 'erpnext' ? 'finance' : 'support', mode: 'live', source, task: 'test' }, 'test'), signal: new AbortController().signal, evidence: new Set() });

test('ERPNext connector encodes IDs and pagination, keeps currencies, and sends auth only to configured host', async t => {
  const requests: URL[] = [];
  const server = createServer((req, res) => {
    assert.equal(req.method, 'GET'); assert.equal(req.headers.authorization, 'token test:secret');
    const url = new URL(req.url!, 'http://localhost'); requests.push(url);
    res.setHeader('Content-Type', 'application/json');
    const row = { name: 'INV/特殊-01', currency: 'USD', grand_total: 12.5 };
    res.end(JSON.stringify({ data: url.search ? [row] : row }));
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise<void>(resolve => server.close(() => resolve())));
  const baseUrl = `http://127.0.0.1:${(server.address() as any).port}`;
  const tools = erpnextTools(new JsonConnector({ baseUrl, headers: { Authorization: 'token test:secret' } }));
  const ctx = context('erpnext');
  const list = await tools.find(tool => tool.name === 'erpnext_list_invoices')!.execute({ status: 'outstanding', page: 2, pageSize: 1 }, ctx) as any;
  assert.equal(requests[0].searchParams.get('limit_start'), '1');
  assert.deepEqual(JSON.parse(requests[0].searchParams.get('filters')!), [['docstatus', '=', 1], ['outstanding_amount', '>', 0]]);
  assert.equal(list.records[0].currency, 'USD'); assert.equal(list.records[0].grand_total, 12.5); assert.equal(list.mayHaveMore, true);
  await tools.find(tool => tool.name === 'erpnext_get_invoice')!.execute({ invoiceId: 'INV/特殊-01' }, ctx);
  assert.ok(requests[1].pathname.includes('INV%2F')); assert.ok(ctx.evidence.has('Sales Invoice:INV/特殊-01'));
  await assert.rejects(tools.find(tool => tool.name === 'publish_report')!.execute({ title: 'Report', summary: 'Summary', findings: ['Finding'], evidenceIds: ['invented'] }, ctx), /not been observed/);
});
test('Zammad connector preserves native dictionaries and ticket IDs instead of assuming fixed states', async t => {
  const server = createServer((req, res) => {
    assert.equal(req.headers.authorization, 'Token token=test-token'); assert.equal(req.method, 'GET');
    const url = new URL(req.url!, 'http://localhost');
    res.setHeader('Content-Type', 'application/json');
    if (url.pathname === '/api/v1/tickets') { assert.equal(url.searchParams.get('page'), '3'); res.end(JSON.stringify([{ id: 501, state_id: 27, priority_id: 91, title: 'API issue', first_response_escalation_at: null }])); }
    else res.end(JSON.stringify([{ id: 27, name: 'custom_open_state' }]));
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise<void>(resolve => server.close(() => resolve())));
  const tools = zammadTools(new JsonConnector({ baseUrl: `http://127.0.0.1:${(server.address() as any).port}`, headers: { Authorization: 'Token token=test-token' } }));
  const ctx = context('zammad');
  const result = await tools.find(tool => tool.name === 'zammad_list_tickets')!.execute({ page: 3, pageSize: 10 }, ctx) as any;
  assert.equal(result.records[0].state_id, 27); assert.equal(result.records[0].first_response_escalation_at, null);
  const states = await tools.find(tool => tool.name === 'zammad_list_states')!.execute({}, ctx) as any[];
  assert.equal(states[0].name, 'custom_open_state'); assert.ok(ctx.evidence.has('tickets:501'));
  assert.ok(ctx.evidence.has('ticket_states:27'));
  assert.equal(result.records[0]._evidenceRef, 'tickets:501');
});
test('HTTP errors, HTML login pages and redirects are never accepted as platform success', async t => {
  const server = createServer((req, res) => {
    if (req.url === '/denied') { res.statusCode = 403; res.end('credential-sensitive body'); }
    else if (req.url === '/redirect') { res.statusCode = 302; res.setHeader('Location', '/html'); res.end(); }
    else res.end('<html>Login required</html>');
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise<void>(resolve => server.close(() => resolve())));
  const client = new JsonConnector({ baseUrl: `http://127.0.0.1:${(server.address() as any).port}`, headers: {} });
  const signal = new AbortController().signal;
  await assert.rejects(client.get('/denied', {}, signal), error => /403/.test((error as Error).message) && !(error as Error).message.includes('credential-sensitive'));
  await assert.rejects(client.get('/html', {}, signal), /non-JSON/);
  await assert.rejects(client.get('/redirect', {}, signal));
});
