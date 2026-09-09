import test from 'node:test';
import assert from 'node:assert/strict';
import { buildModelRequest } from '../server/model-client.js';
import { sandboxTools } from '../server/tools.js';

test('single model boundary disables Qwen thinking and OpenRouter reasoning for executor and planner tools', () => {
  const options = { baseUrl: 'https://openrouter.ai/api/v1', apiKey: 'test-secret', model: 'qwen/qwen3.5-27b', timeoutMs: 1000 };
  for (const tools of [sandboxTools('finance'), []]) {
    const body = buildModelRequest(options, [{ role: 'user', content: 'test' }], tools);
    assert.equal(body.enable_thinking, false); assert.deepEqual(body.reasoning, { enabled: false });
    assert.equal(body.model, options.model); assert.ok(!JSON.stringify(body).includes(options.apiKey));
  }
});
test('direct compatible service receives enable_thinking without OpenRouter-specific reasoning object', () => {
  const body = buildModelRequest({ baseUrl: 'http://localhost:8000/v1', apiKey: 'test', model: 'qwen', timeoutMs: 1000 }, [], []);
  assert.equal(body.enable_thinking, false); assert.equal(body.reasoning, undefined);
});
