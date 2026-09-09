import express from 'express';
import { resolve } from 'node:path';
import { z } from 'zod';
import { config, publicConfig } from './config.js';
import { checkPlatforms } from './platform-check.js';
import { reportMarkdown } from './reports.js';
import { errorMessage } from './runtime.js';
import { seedVariant } from './seed.js';
import { cancelRun, isRunProcessing, publicRun, restoreRuns, runs, startRun, toolsFor } from './service.js';
import { graphStore } from './graph-store.js';

const app = express();
app.disable('x-powered-by');
app.use('/api', (req, res, next) => {
  const origin = req.get('origin');
  const allowed = new Set([`http://127.0.0.1:${config.port}`, `http://localhost:${config.port}`]);
  if (origin && !allowed.has(origin)) { res.status(403).json({ error: 'Origin not allowed' }); return; }
  if (!['GET', 'HEAD'].includes(req.method) && !req.is('application/json')) { res.status(415).json({ error: 'Use application/json' }); return; }
  res.setHeader('Cache-Control', 'no-store'); next();
});
app.use(express.json({ limit: '32kb' }));
app.get('/api/config', (_req, res) => res.json(publicConfig()));
app.get('/api/snapshot', (req, res) => res.json(seedVariant(z.enum(['base', 'changed', 'exception']).default('base').parse(req.query.variant))));
app.get('/api/tools', (req, res) => {
  const query = z.object({ scenario: z.enum(['finance', 'support']), source: z.enum(['sandbox', 'erpnext', 'zammad']).default('sandbox') }).parse(req.query);
  res.json(toolsFor(query).map(({ execute: _execute, ...tool }) => tool));
});
app.get('/api/runs', (_req, res) => res.json([...runs.values()].sort((a, b) => b.startedAt.localeCompare(a.startedAt)).slice(0, 30).map(publicRun).map(run => ({ id: run.id, request: run.request, status: run.status, startedAt: run.startedAt, metrics: run.metrics }))));
app.post('/api/runs', async (req, res) => { const run = await startRun(req.body); res.status(202).json({ id: run.id }); });
app.get('/api/runs/:id', (req, res) => { const run = runs.get(req.params.id); if (!run) { res.status(404).json({ error: 'Run not found' }); return; } res.json(publicRun(run)); });
app.get('/api/graphs', (req, res) => {
  const query = z.object({ scenario: z.enum(['finance', 'support']).optional(), source: z.enum(['sandbox', 'erpnext', 'zammad']).optional() }).parse(req.query);
  res.json(graphStore.list(query.scenario, query.source));
});
app.get('/api/graphs/:id/export', (req, res) => {
  const graph = graphStore.get(req.params.id);
  if (!graph) { res.status(404).json({ error: 'Graph not found' }); return; }
  res.type('json').attachment(`graph-${graph.id}.json`).send(JSON.stringify(graph, null, 2));
});
app.post('/api/runs/:id/learn', async (req, res) => {
  const run = runs.get(req.params.id);
  if (!run) { res.status(404).json({ error: 'Run not found' }); return; }
  if (isRunProcessing(run.id)) { res.status(409).json({ error: '请等待运行和结果保存完成' }); return; }
  const graph = await graphStore.learn(run, toolsFor(run.request));
  res.json(graph);
});
app.post('/api/runs/:id/cancel', (req, res) => { if (!runs.has(req.params.id)) { res.status(404).json({ error: 'Run not found' }); return; } res.json({ cancelled: cancelRun(req.params.id) }); });
app.get('/api/runs/:id/export/:format', (req, res) => {
  const run = runs.get(req.params.id);
  if (!run) { res.status(404).json({ error: 'Run not found' }); return; }
  if (req.params.format === 'json') res.type('json').attachment(`run-${run.id}.json`).send(JSON.stringify(run, null, 2));
  else if (req.params.format === 'md') res.type('text/markdown').attachment(`report-${run.id}.md`).send(reportMarkdown(run));
  else res.status(400).json({ error: 'Supported formats: json, md' });
});
app.post('/api/platforms/check', async (_req, res) => res.json(await checkPlatforms()));
app.use('/api', (_req, res) => res.status(404).json({ error: 'Unknown API route' }));
app.use((error: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => res.status(error instanceof z.ZodError || error instanceof SyntaxError ? 400 : 422).json({ error: errorMessage(error) }));

if (process.env.NODE_ENV === 'production') {
  app.use(express.static(resolve('dist')));
  app.get('/{*path}', (_req, res) => res.sendFile(resolve('dist/index.html')));
} else {
  const { createServer } = await import('vite');
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'spa' });
  app.use(vite.middlewares);
}
await restoreRuns();
await graphStore.restore();
app.listen(config.port, '127.0.0.1', () => console.log(`ReAct Lab ready: http://127.0.0.1:${config.port} · ${publicConfig().modelConfigured ? 'model configured' : 'offline fixtures available; model not configured'}`));
