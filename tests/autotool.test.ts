import test from 'node:test';
import assert from 'node:assert/strict';
import { acquireTools, type ApiSpec } from '../server/autotool.js';
import { createRun } from '../server/runtime.js';

function spec(): ApiSpec { return { openapi: '3.0.3', info: { title: 'New business API', version: '1' }, paths: { '/api/v1/items/{recordId}': { get: { operationId: 'read_item', summary: 'Read item', parameters: [{ name: 'recordId', in: 'path', required: true, schema: { type: 'string', maxLength: 100 } }, { name: 'status', in: 'query', required: true, schema: { type: 'string', enum: ['active', 'all'] } }], 'x-resource': 'items', 'x-data-path': ['data'] } } } }; }
const context = () => ({ run: createRun({ scenario: 'finance', mode: 'live', source: 'sandbox', task: 'test' }, 'test'), signal: new AbortController().signal, evidence: new Set<string>() });

test('AutoTool acquires a new operation from schema with parameter validation and encoded HTTP transport', async () => {
  const requests: unknown[] = [];
  const tools = acquireTools(spec(), async (path, query) => { requests.push({ path, query }); return { data: { id: 'current', amount: 19 } }; }, value => value);
  const result = await tools[0].execute({ recordId: '新/客户', status: 'active' }, context());
  assert.deepEqual(result, { id: 'current', amount: 19 }); assert.deepEqual(requests, [{ path: '/api/v1/items/%E6%96%B0%2F%E5%AE%A2%E6%88%B7', query: { status: 'active' } }]);
  assert.equal(tools[0].origin?.kind, 'autotool'); assert.ok(JSON.stringify(tools[0].parameters).includes('active'));
  await assert.rejects(tools[0].execute({ recordId: 'a', status: 'unknown' }, context()));
  await assert.rejects(tools[0].execute({ recordId: 'a', status: 'all', arbitrary: true }, context()));
  await assert.rejects(tools[0].execute({ recordId: '..', status: 'all' }, context()));
  assert.equal(requests.length, 1);
});
test('AutoTool refuses writes, missing bindings and mismatched responses', async () => {
  const write = spec() as any; write.paths['/api/v1/items/{recordId}'].post = write.paths['/api/v1/items/{recordId}'].get;
  assert.throws(() => acquireTools(write, async () => ({}), value => value), /GET/);
  const missing = spec(); missing.paths['/api/v1/items/{recordId}'].get.parameters = [];
  assert.throws(() => acquireTools(missing, async () => ({}), value => value), /placeholders/);
  const tool = acquireTools(spec(), async () => ({ wrong: [] }), value => value)[0];
  await assert.rejects(tool.execute({ recordId: 'a', status: 'all' }, context()), /data path/);
});
