import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { PRESETS } from '../shared/types.js';
import { ChatCompletionsProvider, FixtureProvider, type ChatMessage, type Completion, type Provider, type ToolCall } from '../server/provider.js';
import { createRun, executeRun } from '../server/runtime.js';
import { sandboxTools } from '../server/tools.js';
import { requestSchema } from '../server/service.js';

const limits = { maxSteps: 24, maxToolCalls: 60, timeoutMs: 5000 };
const make = () => createRun({ scenario: 'finance', mode: 'live', source: 'sandbox', task: PRESETS.finance }, 'test-model');
const call = (name: string, args = '{}', id = 'call-1'): ToolCall => ({ id, type: 'function', function: { name, arguments: args } });
const completion = (calls: ToolCall[] = [], content = '完成'): Completion => ({ message: { role: 'assistant', content, ...(calls.length ? { tool_calls: calls } : {}) }, finishReason: calls.length ? 'tool_calls' : 'stop', usage: { input: 10, output: 5 } });
class ScriptedModel implements Provider {
  readonly kind = 'live' as const; readonly model = 'test-model'; index = 0; histories: ChatMessage[][] = [];
  constructor(private responses: Completion[]) {}
  async complete(messages: ChatMessage[]) { this.histories.push(structuredClone(messages)); return this.responses[Math.min(this.index++, this.responses.length - 1)]; }
}

test('both offline scenarios execute actual tools and preserve isolated snapshots', async () => {
  const finance = createRun({ scenario: 'finance', mode: 'fixture', source: 'sandbox', task: PRESETS.finance }, null);
  const support = createRun({ scenario: 'support', mode: 'fixture', source: 'sandbox', task: PRESETS.support }, null);
  await Promise.all([executeRun(finance, new FixtureProvider('finance'), sandboxTools('finance'), limits), executeRun(support, new FixtureProvider('support'), sandboxTools('support'), limits)]);
  assert.equal(finance.status, 'completed'); assert.equal(support.status, 'completed');
  assert.equal(finance.state.allocations.reduce((sum, item) => sum + item.amountCents, 0), 4200000);
  assert.equal(finance.state.cases.length, 5); assert.equal(finance.initial.cases.length, 0);
  assert.equal(support.state.tickets.filter(item => item.status !== 'closed' && item.ownerId).length, 5);
  assert.equal(support.state.drafts.length, 5); assert.equal(support.state.escalations.length, 2);
  assert.equal(support.state.tickets.filter(item => item.status === 'closed').length, 1);
  for (const run of [finance, support]) { assert.ok(run.report); assert.equal(run.metrics.modelRequests, 0); assert.equal(run.metrics.inputTokens, 0); assert.equal(run.metrics.toolErrors, 0); }
  assert.equal(support.initial.tickets.filter(item => item.status !== 'closed' && item.ownerId).length, 1);
});
test('model observes validated tool results, recovers from malformed arguments, and accounts for requests', async () => {
  const model = new ScriptedModel([completion([call('get_invoice', '{invalid')]), completion([call('get_invoice', '{"invoiceId":"INV-001"}', 'call-2')]), completion()]);
  const run = await executeRun(make(), model, sandboxTools('finance'), limits);
  assert.equal(run.status, 'completed'); assert.equal(run.metrics.toolErrors, 1);
  const errorObservation = model.histories[1].at(-1)!;
  assert.equal(errorObservation.tool_call_id, 'call-1'); assert.equal(JSON.parse(errorObservation.content!).ok, false);
  const successObservation = model.histories[2].at(-1)!;
  assert.equal(JSON.parse(successObservation.content!).result.id, 'INV-001');
  assert.equal(run.metrics.modelRequests, 3); assert.equal(run.metrics.inputTokens, 30); assert.equal(run.metrics.outputTokens, 15);
});
test('unknown tool is returned as an observation without executing arbitrary code', async () => {
  const model = new ScriptedModel([completion([call('send_email')]), completion()]);
  const run = await executeRun(make(), model, sandboxTools('finance'), limits);
  assert.equal(run.metrics.toolErrors, 1); assert.match(model.histories[1].at(-1)!.content!, /Unknown tool/);
});
test('batch tool calls preserve one observation per call ID and sequential state', async () => {
  const model = new ScriptedModel([completion([call('list_payments', '{}', 'p'), call('list_invoices', '{}', 'i')]), completion()]);
  const run = await executeRun(make(), model, sandboxTools('finance'), limits);
  assert.equal(run.metrics.toolCalls, 2); assert.deepEqual(model.histories[1].slice(-2).map(item => item.tool_call_id), ['p', 'i']);
});
test('repeated calls, step limit and tool budget stop runaway loops', async () => {
  const repeat = await executeRun(make(), new ScriptedModel([completion([call('list_payments')])]), sandboxTools('finance'), limits);
  assert.equal(repeat.status, 'limited'); assert.equal(repeat.metrics.toolCalls, 4);
  const stepLimited = await executeRun(make(), new ScriptedModel([completion([call('list_payments')])]), sandboxTools('finance'), { ...limits, maxSteps: 1 });
  assert.equal(stepLimited.status, 'limited'); assert.equal(stepLimited.metrics.modelRequests, 1);
  const toolLimited = await executeRun(make(), new ScriptedModel([completion([call('list_payments'), call('list_invoices', '{}', 'i')])]), sandboxTools('finance'), { ...limits, maxToolCalls: 1 });
  assert.equal(toolLimited.status, 'limited'); assert.equal(toolLimited.metrics.toolCalls, 1);
});
test('missing provider usage is unknown rather than fabricated zero', async () => {
  const response = completion(); delete response.usage;
  const run = await executeRun(make(), new ScriptedModel([response]), sandboxTools('finance'), limits);
  assert.equal(run.metrics.inputTokens, null); assert.equal(run.metrics.usageComplete, false);
});
test('truncated final response is not reported as successful completion', async () => {
  const response = completion(); response.finishReason = 'length';
  const run = await executeRun(make(), new ScriptedModel([response]), sandboxTools('finance'), limits);
  assert.equal(run.status, 'failed'); assert.equal(run.finalText, undefined);
});
test('cancellation aborts pending provider and prevents subsequent tool mutations', async () => {
  const controller = new AbortController();
  const model: Provider = { kind: 'live', model: 'test', complete: async (_messages, _tools, signal) => {
    controller.abort(); signal.throwIfAborted(); return completion([call('allocate_payment')]);
  } };
  const run = await executeRun(make(), model, sandboxTools('finance'), limits, controller.signal);
  assert.equal(run.status, 'cancelled'); assert.equal(run.metrics.toolCalls, 0);
});
test('offline mode cannot silently ignore custom prompts or use live platforms', () => {
  assert.throws(() => requestSchema.parse({ scenario: 'finance', source: 'sandbox', mode: 'fixture', task: 'custom task' }));
  assert.throws(() => requestSchema.parse({ scenario: 'finance', source: 'erpnext', mode: 'fixture', task: PRESETS.finance }));
});
test('external platform runs contain no synthetic financial or support data', () => {
  const run = createRun({ scenario: 'finance', source: 'erpnext', mode: 'live', task: 'read' }, 'model');
  assert.deepEqual(run.state.invoices, []); assert.deepEqual(run.state.tickets, []);
});
test('HTTP model adapter executes real request/observation loop against a protocol test server', async t => {
  const requests: any[] = [];
  const server = createServer(async (req, res) => {
    assert.equal(req.url, '/v1/chat/completions'); assert.equal(req.headers.authorization, 'Bearer test-only');
    let body = ''; for await (const part of req) body += part;
    const payload = JSON.parse(body); requests.push(payload);
    const response = requests.length === 1 ? completion([call('get_invoice', '{"invoiceId":"INV-001"}')]) : completion([], '已读取真实工具返回的 INV-001。');
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ choices: [{ message: { ...response.message, reasoning_content: 'must not be exposed' }, finish_reason: response.finishReason }], usage: { prompt_tokens: 42, completion_tokens: 7 } }));
  });
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise<void>(resolve => server.close(() => resolve())));
  const address = server.address() as { port: number };
  const provider = new ChatCompletionsProvider({ baseUrl: `http://127.0.0.1:${address.port}/v1`, apiKey: 'test-only', model: 'protocol-test', timeoutMs: 1000 });
  const run = await executeRun(make(), provider, sandboxTools('finance'), limits);
  assert.equal(run.status, 'completed'); assert.equal(requests.length, 2);
  assert.equal(requests[0].tools[0].type, 'function'); assert.equal(requests[0].parallel_tool_calls, false);
  assert.equal(JSON.parse(requests[1].messages.at(-1).content).result.id, 'INV-001');
  assert.equal(run.metrics.inputTokens, 84); assert.equal(run.metrics.outputTokens, 14);
  assert.ok(!JSON.stringify(run).includes('must not be exposed')); assert.ok(!JSON.stringify(run).includes('test-only'));
});
