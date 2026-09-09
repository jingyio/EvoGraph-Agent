import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { z } from 'zod';
import { PRESETS, type AgentRun, type GraphNode, type TaskGraph } from '../shared/types.js';
import { compileReadGraph, contractHash, graphApplicable, orderedNodes, pathValue, runReadGraph, taskKey } from '../server/graph.js';
import { GraphStore, environmentHash } from '../server/graph-store.js';
import { dependencyClosure, retrieveWorkflows, selectWorkflow } from '../server/gagent.js';
import { createRun, executeRun } from '../server/runtime.js';
import { defineTool, sandboxTools, type Tool } from '../server/tools.js';
import type { ChatMessage, Completion, Provider } from '../server/provider.js';

const limits = { maxSteps: 24, maxToolCalls: 60, timeoutMs: 5000 };
async function trace(tools: Tool[], operations: { name: string; args: object }[], task = PRESETS.finance): Promise<AgentRun> {
  const run = createRun({ scenario: 'finance', mode: 'live', source: 'sandbox', task }, 'protocol-test');
  const context = { run, signal: new AbortController().signal, evidence: new Set<string>() };
  for (const operation of operations) {
    run.events.push({ seq: run.events.length + 1, at: new Date().toISOString(), type: 'action', title: operation.name, detail: { arguments: JSON.stringify(operation.args) } });
    try {
      const result = await tools.find(tool => tool.name === operation.name)!.execute(operation.args, context);
      run.events.push({ seq: run.events.length + 1, at: new Date().toISOString(), type: 'observation', title: operation.name, detail: { ok: true, result: structuredClone(result) } });
    } catch { run.events.push({ seq: run.events.length + 1, at: new Date().toISOString(), type: 'observation', title: operation.name, detail: { ok: false, error: 'invalid' } }); }
  }
  run.metrics.modelRequests = 3; run.metrics.inputTokens = 150; run.metrics.outputTokens = 40; run.status = 'completed';
  return run;
}
const financeOps = [{ name: 'list_invoices', args: {} }, { name: 'list_payments', args: {} }, ...['PAY-001', 'PAY-002', 'PAY-003'].map(paymentId => ({ name: 'preview_payment_match', args: { paymentId } }))];
function wrapGraph(sourceRun: AgentRun, tools: Tool[], nodes: GraphNode[]): TaskGraph {
  return { id: randomUUID(), sourceRunId: sourceRun.id, version: 1, createdAt: new Date().toISOString(), scenario: sourceRun.request.scenario, source: sourceRun.request.source, task: sourceRun.request.task, taskKey: taskKey(sourceRun.request.task), contractHash: contractHash(tools), environmentHash: environmentHash(sourceRun.request.source), nodes, sourceModelRequests: 3, sourceInputTokens: 150, sourceOutputTokens: 40, validation: { status: 'passed', toolCalls: 6, durationMs: 1, compileMs: 1, learningModelRequests: 0 }, scope: 'read-prefix', compilerVersion: 1 };
}
class FinalModel implements Provider {
  kind = 'live' as const; model = 'test'; messages: ChatMessage[] = [];
  async complete(messages: ChatMessage[]): Promise<Completion> { this.messages = structuredClone(messages); return { message: { role: 'assistant', content: '读取完成，业务判断仍需后续验证。' }, finishReason: 'stop', usage: { input: 20, output: 10 } }; }
}

test('compiler infers foreach dependency from observations, deduplicates repeated reads and stops before writes', async () => {
  const tools = sandboxTools('finance');
  const source = await trace(tools, [...financeOps, { name: 'allocate_payment', args: { paymentId: 'PAY-001', allocations: [{ invoiceId: 'INV-001', amountCents: 1200000 }] } }, { name: 'get_invoice', args: { invoiceId: 'INV-001' } }]);
  const nodes = compileReadGraph(source, tools);
  assert.equal(nodes.length, 3); assert.equal(nodes[2].tool, 'preview_payment_match');
  assert.deepEqual(nodes[2].foreach, { nodeId: 'n2', collectionPath: [] });
  assert.deepEqual(nodes[2].arguments.paymentId, { kind: 'item', path: ['id'] });
  assert.equal(nodes[2].sourceEventSeqs.length, 3);
  assert.ok(!JSON.stringify(nodes).includes('PAY-001')); assert.ok(!nodes.some(node => node.tool === 'allocate_payment'));
});
test('graph executes new IDs, changed amounts and added records instead of replaying source results', async () => {
  const tools = sandboxTools('finance'), source = await trace(tools, financeOps);
  const graph = wrapGraph(source, tools, compileReadGraph(source, tools));
  const run = createRun({ ...source.request, strategy: 'graph', snapshot: 'changed' }, 'test');
  run.graph = { status: 'hit', graphId: graph.id, nodeStates: {}, toolCalls: 0, completedNodes: 0 };
  const model = new FinalModel();
  await executeRun(run, model, tools, limits, undefined, undefined, { graph });
  assert.equal(run.status, 'completed'); assert.equal(run.metrics.modelRequests, 1); assert.equal(run.graph.completedNodes, 3);
  const calls = run.events.filter(event => event.type === 'action' && event.title === 'preview_payment_match').map(event => JSON.parse((event.detail as any).arguments).paymentId);
  assert.deepEqual(new Set(calls), new Set(run.state.payments.map(payment => payment.id))); assert.equal(calls.length, 7);
  const firstPreview = model.messages.filter(message => message.role === 'tool').map(message => JSON.parse(message.content!)).find(value => value.result?.eligible);
  assert.equal(firstPreview.result.allocations[0].amountCents, 1440000);
  assert.equal(run.state.allocations.length, 0, 'Read graph must not perform finance writes');
});
test('new ownership conflict remains visible to the model', async () => {
  const tools = sandboxTools('finance'), source = await trace(tools, financeOps);
  const graph = wrapGraph(source, tools, compileReadGraph(source, tools));
  const run = createRun({ ...source.request, strategy: 'graph', snapshot: 'exception' }, 'test');
  run.graph = { status: 'hit', nodeStates: {}, toolCalls: 0, completedNodes: 0 };
  const model = new FinalModel(); await executeRun(run, model, tools, limits, undefined, undefined, { graph });
  assert.ok(model.messages.some(message => message.role === 'tool' && message.content?.includes('customer_currency_or_reference_mismatch')));
});
test('changed response shape falls back to model with actual error observations; no stale report', async () => {
  const tools = sandboxTools('finance'), source = await trace(tools, financeOps), graph = wrapGraph(source, tools, compileReadGraph(source, tools));
  const broken = tools.map(tool => tool.name === 'list_payments' ? { ...tool, execute: async () => ({ unexpected: [] }) } : tool);
  const run = createRun({ ...source.request, strategy: 'graph' }, 'test');
  run.graph = { status: 'hit', nodeStates: {}, toolCalls: 0, completedNodes: 0 };
  const model = new FinalModel(); await executeRun(run, model, broken, limits, undefined, undefined, { graph });
  assert.equal(run.graph.status, 'fallback'); assert.match(run.graph.reason!, /集合形状/);
  assert.equal(run.metrics.modelRequests, 1); assert.equal(run.report, undefined); assert.equal(run.state.allocations.length, 0);
});
test('learned pagination advances using current mayHaveMore and does not freeze original page count', async () => {
  let records = [{ id: 1 }, { id: 2 }];
  const tools = [defineTool('list_records', 'read', 'read', { page: z.number().int().positive(), pageSize: z.number().int().positive() }, ({ page, pageSize }) => ({ records: records.slice((page - 1) * pageSize, page * pageSize), mayHaveMore: page * pageSize < records.length })), defineTool('get_record', 'read', 'read', { recordId: z.number().int() }, ({ recordId }) => ({ id: recordId }))];
  const source = await trace(tools, [{ name: 'list_records', args: { page: 1, pageSize: 2 } }, { name: 'get_record', args: { recordId: 1 } }]);
  const nodes = compileReadGraph(source, tools); assert.ok(nodes[0].paginate);
  records = [{ id: 11 }, { id: 12 }, { id: 13 }, { id: 14 }, { id: 15 }];
  const observed: number[] = [], pages: number[] = [];
  const context = { run: createRun(source.request, 'test'), signal: new AbortController().signal, evidence: new Set<string>() };
  await runReadGraph(nodes, tools, { invoke: async (name, args) => { if (name === 'get_record') observed.push(args.recordId as number); else pages.push(args.page as number); return tools.find(tool => tool.name === name)!.execute(args, context); }, node: () => {} }, context.signal);
  assert.deepEqual(pages, [1, 2, 3]); assert.deepEqual(observed, [11, 12, 13, 14, 15]);
});
test('compiler refuses to freeze unknown record identifiers and refuses fixture or failed sources', async () => {
  const tools = sandboxTools('finance'), source = await trace(tools, [{ name: 'get_invoice', args: { invoiceId: 'INV-001' } }]);
  assert.throws(() => compileReadGraph(source, tools), /没有可安全/);
  source.request.mode = 'fixture'; assert.throws(() => compileReadGraph(source, tools), /离线/);
  source.request.mode = 'live'; source.status = 'failed'; assert.throws(() => compileReadGraph(source, tools));
});
test('compiler does not freeze task-specific dates or thresholds from a historical read', async () => {
  const tool = defineTool('search_by_date', 'query', 'read', { since: z.string(), minimumAmount: z.number() }, args => args);
  const source = await trace([tool], [{ name: tool.name, args: { since: '2026-09-01', minimumAmount: 100 } }]);
  assert.throws(() => compileReadGraph(source, [tool]), /没有可安全/);
});
test('graph rejects cycles, missing dependencies, write nodes and prototype paths', () => {
  const tools = sandboxTools('finance');
  const n: GraphNode = { id: 'a', tool: 'list_invoices', arguments: {}, dependencies: ['b'], sourceEventSeqs: [1] };
  assert.throws(() => orderedNodes([n], tools), /缺少/);
  assert.throws(() => orderedNodes([n, { ...n, id: 'b', dependencies: ['a'] }], tools), /循环/);
  assert.throws(() => orderedNodes([{ ...n, dependencies: [], tool: 'allocate_payment' }], tools), /非读取/);
  assert.throws(() => pathValue({}, ['constructor']), /不存在/);
});
test('exact guard retains task constraints and only abstracts the explicit inspection clock', async () => {
  assert.equal(taskKey('以 2026-09-09T01:00:00Z 为本次巡检时刻，读工单'), taskKey('以 2026-09-10T01:00:00Z 为本次巡检时刻，读工单'));
  assert.notEqual(taskKey('截止 2026-09-09T01:00:00Z 的工单'), taskKey('截止 2026-09-10T01:00:00Z 的工单'));
  const tools = sandboxTools('finance'), source = await trace(tools, financeOps), graph = wrapGraph(source, tools, compileReadGraph(source, tools));
  assert.equal(graphApplicable(graph, source.request, tools, graph.environmentHash), null);
  assert.match(graphApplicable(graph, { ...source.request, task: '只读取客户 C-01' }, tools, graph.environmentHash)!, /任务/);
  assert.match(graphApplicable(graph, source.request, tools, 'new-instance')!, /实例/);
  assert.match(graphApplicable(graph, source.request, tools.slice(1), graph.environmentHash)!, /契约/);
});
test('shadow validation persists a versioned graph without model calls or cached outputs', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'rsi-graph-test-')); t.after(() => rm(directory, { recursive: true, force: true }));
  const store = new GraphStore(directory), tools = sandboxTools('finance'), source = await trace(tools, financeOps);
  const graph = await store.learn(source, tools); assert.equal(graph.validation.learningModelRequests, 0); assert.equal(graph.validation.toolCalls, 8);
  const same = await store.learn(source, tools); assert.equal(same.id, graph.id);
  const reloaded = new GraphStore(directory); await reloaded.restore(); assert.equal(reloaded.list().length, 1);
  assert.equal(reloaded.select(source.request, tools).graph?.id, graph.id);
  assert.ok(!JSON.stringify(graph.nodes).includes('1200000'));
  const another = await trace(tools, financeOps); const v2 = await store.learn(another, tools); assert.equal(v2.version, 2);
});
test('shadow validation refuses a mislabeled read tool that mutates sandbox state', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'rsi-graph-test-')); t.after(() => rm(directory, { recursive: true, force: true }));
  const tool = defineTool('bad_read', 'read', 'read', {}, (_, context) => { context.run.state.cases.push({ id: 'bad', kind: 'unmatched', entityId: 'PAY-006', summary: 'bad', evidenceIds: [] }); return {}; });
  const source = await trace([tool], [{ name: 'bad_read', args: {} }]);
  await assert.rejects(new GraphStore(directory).learn(source, [tool]), /修改了业务状态/);
});
test('G-Agent selects only supplied graph nodes, closes dependencies and counts planning usage', async () => {
  const tools = sandboxTools('finance'), source = await trace(tools, financeOps), graph = wrapGraph(source, tools, compileReadGraph(source, tools));
  assert.deepEqual(dependencyClosure(graph.nodes, ['n3']).map(node => node.id), ['n2', 'n3']);
  const request = { ...source.request, strategy: 'graph' as const, task: '核对当前快照的应收和回款，登记异常，输出对账简报。' };
  assert.equal(retrieveWorkflows([graph], request, tools, graph.environmentHash).length, 1);
  let calls = 0;
  const provider: Provider = { kind: 'live', model: 'test', complete: async () => ++calls === 1 ? { message: { role: 'assistant', content: null, tool_calls: [{ id: 'plan1', type: 'function', function: { name: 'select_workflow', arguments: JSON.stringify({ graphId: graph.id, nodeIds: ['n3'], reason: '先核查回款匹配依据' }) } }] }, finishReason: 'tool_calls', usage: { input: 30, output: 5 } } : { message: { role: 'assistant', content: '执行完成' }, finishReason: 'stop', usage: { input: 20, output: 10 } } };
  const run = createRun(request, 'test'); run.graph = { status: 'miss', nodeStates: {}, toolCalls: 0, completedNodes: 0 };
  await executeRun(run, provider, tools, limits, undefined, undefined, { candidates: [graph] });
  assert.equal(run.graph.selection, 'adapted'); assert.equal(run.graph.plannerRequests, 1); assert.equal(run.metrics.modelRequests, 2);
  assert.equal(run.metrics.inputTokens, 50); assert.deepEqual(run.graph.selectedNodeIds, ['n2', 'n3']);
  await assert.rejects(selectWorkflow(request, [graph], tools, async () => ({ message: { role: 'assistant', content: null, tool_calls: [{ id: 'p', type: 'function', function: { name: 'select_workflow', arguments: JSON.stringify({ graphId: graph.id, nodeIds: ['not-real'], reason: 'invalid' }) } }] }, finishReason: 'tool_calls' })), /不存在/);
});
test('planner failure recovers through ReAct and marks usage incomplete', async () => {
  const tools = sandboxTools('finance'), source = await trace(tools, financeOps), graph = wrapGraph(source, tools, compileReadGraph(source, tools));
  let calls = 0;
  const provider: Provider = { kind: 'live', model: 'test', complete: async () => { if (++calls === 1) throw new Error('planner network failure'); return { message: { role: 'assistant', content: '继续普通执行' }, finishReason: 'stop', usage: { input: 20, output: 10 } }; } };
  const run = createRun({ ...source.request, strategy: 'graph' }, 'test'); run.graph = { status: 'miss', nodeStates: {}, toolCalls: 0, completedNodes: 0 };
  await executeRun(run, provider, tools, limits, undefined, undefined, { candidates: [graph] });
  assert.equal(run.status, 'completed'); assert.equal(run.metrics.modelRequests, 2); assert.equal(run.metrics.usageComplete, false); assert.equal(run.graph.toolCalls, 0);
});
