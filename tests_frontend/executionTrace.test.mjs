import test from 'node:test';
import assert from 'node:assert/strict';
import { traceAt, spansAt } from '../src/executionTrace.ts';
const metrics = { modelRequests: 2, toolCalls: 1, inputTokens: 100, outputTokens: 20, toolErrors: 0, usageComplete: true, durationMs: 5000, queueMs: 0 };
const run = { id: 'x', taskId: 'task', strategy: 'graph_rsi', traceVersion: 2, status: 'completed', phase: 'done', createdAt: '2026-09-10T00:00:00Z', models: { planner: 'test', executor: 'test' }, metrics,
  evaluation: { status: 'passed', issues: [] }, submission: { summary: 'final report' }, graph: { nodes: [{ id: 'a', tool: 'read', dependencies: [] }], nodeStates: { a: 'done' } },
  events: [
    { seq: 1, elapsedMs: 100, type: 'model_start', title: 'plan', detail: { requestId: 'm1' }, metrics: { ...metrics, modelRequests: 1, toolCalls: 0, inputTokens: 0, outputTokens: 0 } },
    { seq: 2, elapsedMs: 1500, type: 'model', title: 'plan', detail: { requestId: 'm1', usage: { input: 60, output: 10 } }, metrics: { ...metrics, modelRequests: 1, toolCalls: 0, inputTokens: 60, outputTokens: 10 } },
    { seq: 3, elapsedMs: 1600, type: 'graph_created', title: 'graph', detail: { nodes: [{ id: 'a', tool: 'read', dependencies: [] }] } },
    { seq: 4, elapsedMs: 1700, type: 'graph', title: 'a running', detail: { nodeId: 'a', state: 'running' } },
    { seq: 5, elapsedMs: 1800, type: 'action', title: 'read', detail: { callId: 't1', executor: 'graph' } },
    { seq: 6, elapsedMs: 1900, type: 'observation', title: 'read', detail: { callId: 't1', ok: true, result: {} } },
    { seq: 7, elapsedMs: 2000, type: 'graph', title: 'a done', detail: { nodeId: 'a', state: 'done' } },
    { seq: 8, elapsedMs: 5000, type: 'finished', title: 'done', metrics },
  ] };

test('scrubbing history does not reveal future graph, report, score or metrics', () => {
  const initial = traceAt(run, 0);
  assert.equal(initial.events.length, 0);
  assert.equal(initial.metrics.modelRequests, 0);
  assert.equal(initial.nodes.length, 0);
  assert.equal(initial.evaluation.status, 'pending');
  assert.equal(initial.submission, undefined);
  const midway = traceAt(run, 1800);
  assert.equal(midway.metrics.inputTokens, 60);
  assert.equal(midway.metrics.modelRequests, 1);
  assert.equal(midway.states.a, 'running');
  assert.equal(midway.submission, undefined);
  assert.equal(traceAt(run, 5000).evaluation.status, 'passed');
  assert.equal(traceAt(run, 5000).submission.summary, 'final report');
  assert.equal(traceAt(run, 5000).metrics.inputTokens, 100);
});
test('concurrent same-name tool calls pair by call ID even when results arrive out of order', () => {
  const events = [
    { seq: 1, elapsedMs: 10, type: 'action', title: 'read', detail: { callId: 'a' } },
    { seq: 2, elapsedMs: 11, type: 'action', title: 'read', detail: { callId: 'b' } },
    { seq: 3, elapsedMs: 20, type: 'observation', title: 'read', detail: { callId: 'b', ok: false } },
    { seq: 4, elapsedMs: 30, type: 'observation', title: 'read', detail: { callId: 'a', ok: true } },
  ];
  const spans = spansAt(run, events);
  assert.equal(spans[0].end, 30);
  assert.equal(spans[1].end, 20);
  assert.equal(spans[0].error, false);
  assert.equal(spans[1].error, true);
});
test('live model request is pending until its corresponding response', () => {
  const before = spansAt(run, traceAt(run, 1000).events);
  assert.equal(before[0].end, undefined);
  assert.equal(spansAt(run, traceAt(run, 1550).events)[0].end, 1500);
});
test('legacy traces show invocation timestamps without inventing durations', () => {
  const legacy = { ...run, traceVersion: undefined };
  const spans = spansAt(legacy, [{ seq: 1, at: '2026-09-10T00:00:01Z', type: 'action', title: 'read', detail: { callId: 'old' } }]);
  assert.equal(spans[0].start, 1000);
  assert.equal(spans[0].end, 1000);
});
