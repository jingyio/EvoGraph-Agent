import { PRESETS, type Scenario } from '../shared/types.js';
import { config } from './config.js';
import { ChatCompletionsProvider, FixtureProvider } from './provider.js';
import { createRun, executeRun } from './runtime.js';
import { persistRun } from './service.js';
import { sandboxTools } from './tools.js';

const scenario = (process.argv[2] || 'finance') as Scenario;
if (!['finance', 'support'].includes(scenario)) throw new Error('Usage: npm run demo -- finance|support [--live]');
const live = process.argv.includes('--live');
const provider = live ? new ChatCompletionsProvider({ ...config, timeoutMs: config.modelTimeoutMs }) : new FixtureProvider(scenario);
const run = createRun({ scenario, mode: live ? 'live' : 'fixture', source: 'sandbox', task: PRESETS[scenario] }, provider.model);
await executeRun(run, provider, sandboxTools(scenario), config, undefined, event => { if (['start', 'action', 'finish', 'error'].includes(event.type)) console.log(`[${event.seq}] ${event.title}`); });
await persistRun(run);
console.log(JSON.stringify({ id: run.id, status: run.status, metrics: run.metrics, reportMetrics: run.report?.metrics, artifact: `artifacts/${run.id}/report.md` }, null, 2));
if (run.status !== 'completed') process.exitCode = 1;
