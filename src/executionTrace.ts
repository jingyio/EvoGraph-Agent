export type Strategy = 'react' | 'strong_react' | 'plan_react' | 'autotool' | 'graph_rsi';
export const strategyNames: Record<Strategy, string> = { react: 'ReAct', strong_react: 'Strong ReAct', plan_react: 'Plan + ReAct', autotool: 'Plan + AutoTool', graph_rsi: 'Graph RSI' };
export type Metrics = { modelRequests: number; toolCalls: number; inputTokens: number; outputTokens: number; toolErrors: number; usageComplete: boolean; durationMs: number; queueMs: number; elidedToolCalls?: number; recoveryToolCalls?: number };
export type Evaluation = { status: string; issues?: string[] };
export type TraceEvent = { seq: number; at: string; elapsedMs?: number; type: string; title: string; detail?: any; metrics?: Metrics };
export type GraphNode = { id: string; tool: string; dependencies: string[]; reuse?: { fields: string[] }; defer?: boolean };
export type TraceRun = { id: string; taskId: string; strategy: Strategy; status: string; phase: string; createdAt: string; startedAt?: string; finishedAt?: string; traceVersion?: number; models: { planner: string; executor: string }; modelSettings?: unknown; metrics: Metrics; events: TraceEvent[]; evaluation: Evaluation; graph?: { nodes: GraphNode[]; nodeStates: Record<string, string> }; submission?: any; evolution?: { usedVersionId?: string; generation?: number; maintenanceMs?: number; note?: string }; error?: string };
export type RunSummary = Omit<TraceRun, 'events'>;
export const activeRun = (run?: { status: string } | null) => !!run && ['running', 'queued'].includes(run.status);
export function eventTime(run: TraceRun, event: TraceEvent): number {
  if (typeof event.elapsedMs === 'number') return Math.max(0, event.elapsedMs);
  return Math.max(0, Date.parse(event.at) - Date.parse(run.startedAt || run.createdAt) - (run.startedAt ? 0 : run.metrics.queueMs || 0));
}
export function traceDuration(run: TraceRun): number {
  return Math.max(1, run.metrics.durationMs || 0, ...run.events.map(e => eventTime(run, e)));
}
export function traceAt(run: TraceRun, cursor: number) {
  const finished = !activeRun(run) && cursor >= traceDuration(run);
  const events = run.events.filter(e => eventTime(run, e) <= cursor);
  const snapshots = events.filter(e => e.metrics);
  const metrics: Metrics = finished ? run.metrics : snapshots.at(-1)?.metrics || {
    modelRequests: events.filter(e => e.type === 'model').length,
    toolCalls: events.filter(e => e.type === 'action').length,
    inputTokens: events.filter(e => e.type === 'model').reduce((n, e) => n + (e.detail?.usage?.input || 0), 0),
    outputTokens: events.filter(e => e.type === 'model').reduce((n, e) => n + (e.detail?.usage?.output || 0), 0),
    toolErrors: events.filter(e => e.type === 'observation' && e.detail?.ok === false).length,
    usageComplete: events.filter(e => e.type === 'model').every(e => !!e.detail?.usage), durationMs: Math.min(cursor, traceDuration(run)), queueMs: run.metrics.queueMs,
  };
  const created = events.find(e => e.type === 'graph_created');
  const legacyGraphVisible = !run.traceVersion && events.some(e => e.type === 'graph');
  const nodes: GraphNode[] = created?.detail?.nodes || (legacyGraphVisible ? run.graph?.nodes || [] : []);
  const states: Record<string, string> = Object.fromEntries(nodes.map(n => [n.id, 'pending']));
  for (const e of events) {
    if (e.type !== 'graph') continue;
    if (e.detail?.nodeId && e.detail?.state) states[e.detail.nodeId] = e.detail.state;
    else for (const n of nodes) {
      if (e.title.startsWith(n.id + ' ') && ['running', 'done', 'reused', 'failed', 'model-handoff'].includes(e.title.slice(n.id.length + 1))) states[n.id] = e.title.slice(n.id.length + 1);
    }
  }
  const observedEval = events.filter(e => e.type === 'evaluation' || (e.type === 'observation' && e.detail?.result?.evaluation)).at(-1);
  const evaluation: Evaluation = finished ? run.evaluation : observedEval ? (observedEval.type === 'evaluation' ? observedEval.detail : observedEval.detail.result.evaluation) : { status: 'pending', issues: [] };
  const submitted = events.filter(e => e.type === 'action' && e.title.endsWith('publish_report')).at(-1);
  let submission = finished ? run.submission : undefined;
  if (!finished && submitted) { try { submission = JSON.parse(submitted.detail?.arguments || '{}'); } catch { /* Raw event retains malformed arguments. */ } }
  return { events, metrics, nodes, states, evaluation, submission, finished };
}
export type Span = { key: string; label: string; kind: 'model' | 'graph' | 'tool'; start: number; end?: number; error: boolean };
export function spansAt(run: TraceRun, events: TraceEvent[]): Span[] {
  const spans: Span[] = [];
  const pending = new Map<string, Span>();
  for (const e of events) {
    const t = eventTime(run, e);
    if (e.type === 'model_start' || e.type === 'action') {
      const key = e.type === 'model_start' ? e.detail?.requestId : e.detail?.callId;
      const span: Span = { key: key || `event-${e.seq}`, label: e.title, kind: e.type === 'model_start' ? 'model' : e.detail?.executor === 'graph' ? 'graph' : 'tool', start: t, ...(!run.traceVersion ? { end: t } : {}), error: false };
      spans.push(span);
      if (key) pending.set(key, span);
    } else if (['model', 'model_error', 'observation'].includes(e.type)) {
      const key = e.type === 'observation' ? e.detail?.callId : e.detail?.requestId;
      const span = key && pending.get(key);
      if (span) { span.end = t; span.error = e.type === 'model_error' || e.detail?.ok === false; pending.delete(key); }
      else if (e.type === 'model') spans.push({ key: `event-${e.seq}`, label: e.title, kind: 'model', start: t, end: t, error: false });
      // Historical observations without IDs cannot be safely paired across concurrent calls.
    }
  }
  return spans;
}
