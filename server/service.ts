import { mkdir, readFile, readdir, writeFile, rename } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { z } from 'zod';
import { PRESETS, type AgentRun, type RunRequest } from '../shared/types.js';
import { config, publicConfig } from './config.js';
import { platformTools } from './connectors.js';
import { ChatCompletionsProvider, FixtureProvider } from './provider.js';
import { reportMarkdown } from './reports.js';
import { createRun, executeRun } from './runtime.js';
import { sandboxTools } from './tools.js';
import { graphStore } from './graph-store.js';
import { errorMessage } from './runtime.js';

export const requestSchema = z.object({ scenario: z.enum(['finance', 'support']), mode: z.enum(['fixture', 'live']), source: z.enum(['sandbox', 'erpnext', 'zammad']), task: z.string().trim().min(1).max(6000), strategy: z.enum(['react', 'graph']).default('react'), snapshot: z.enum(['base', 'changed', 'exception']).default('base') }).strict().superRefine((request, context) => {
  if (request.mode === 'fixture' && (request.source !== 'sandbox' || request.task !== PRESETS[request.scenario])) context.addIssue({ code: 'custom', message: '离线示例只支持沙箱预设任务；自定义任务请使用真实模型模式。' });
  if ((request.scenario === 'finance' && request.source === 'zammad') || (request.scenario === 'support' && request.source === 'erpnext')) context.addIssue({ code: 'custom', message: '数据源与业务场景不匹配' });
  if (request.mode === 'fixture' && (request.strategy !== 'react' || request.snapshot !== 'base')) context.addIssue({ code: 'custom', message: '离线示例仅用于原始快照固定流程，不能作为 Graph RSI。' });
  if (request.source !== 'sandbox' && request.snapshot !== 'base') context.addIssue({ code: 'custom', message: '快照变体只用于内置业务沙箱。' });
});
export const artifactsDirectory = resolve('artifacts');
export const runs = new Map<string, AgentRun>();
const controllers = new Map<string, AbortController>();
export function isRunProcessing(id: string) { return controllers.has(id); }
export function publicRun(run: AgentRun): AgentRun { return controllers.has(run.id) ? { ...run, status: 'running' } : run; }
export async function persistRun(run: AgentRun) {
  const directory = join(artifactsDirectory, run.id);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  await writeFile(join(directory, 'run.json.tmp'), JSON.stringify(run, null, 2), { mode: 0o600 });
  await rename(join(directory, 'run.json.tmp'), join(directory, 'run.json'));
  await writeFile(join(directory, 'report.md'), reportMarkdown(run), { mode: 0o600 });
}
export async function restoreRuns() {
  await mkdir(artifactsDirectory, { recursive: true, mode: 0o700 });
  const directories = await readdir(artifactsDirectory, { withFileTypes: true });
  for (const item of directories.filter(item => item.isDirectory() && /^[\da-f-]{36}$/.test(item.name))) {
    try {
      const run = JSON.parse(await readFile(join(artifactsDirectory, item.name, 'run.json'), 'utf8')) as AgentRun;
      if (run.id === item.name && Array.isArray(run.events) && run.finishedAt) runs.set(run.id, run);
    } catch { /* A partial artifact cannot invalidate other completed runs. */ }
  }
}
export function toolsFor(request: Pick<RunRequest, 'source' | 'scenario'>) { return request.source === 'sandbox' ? sandboxTools(request.scenario) : platformTools(request.source); }
export async function startRun(raw: unknown): Promise<AgentRun> {
  const request = requestSchema.parse(raw);
  if (controllers.size >= 2) throw new Error('已有两个任务正在运行，请等待完成或取消后再试。');
  if (request.mode === 'live' && !publicConfig().modelConfigured) throw new Error('尚未配置真实模型。请填写 .env 中的 LLM_API_KEY 和 LLM_MODEL 后重启。');
  const provider = request.mode === 'fixture' ? new FixtureProvider(request.scenario) : new ChatCompletionsProvider({ ...config, timeoutMs: config.modelTimeoutMs });
  const tools = toolsFor(request);
  const run = createRun(request, provider.model), controller = new AbortController();
  const selection = request.strategy === 'graph' ? graphStore.select(request, tools) : undefined;
  if (selection) run.graph = { status: selection.graph ? 'hit' : 'miss', selection: selection.graph ? 'exact' : 'none', plannerRequests: 0, graphId: selection.graph?.id, version: selection.graph?.version, sourceRunId: selection.graph?.sourceRunId, reason: selection.reason, nodeStates: Object.fromEntries((selection.graph?.nodes || []).map(node => [node.id, 'pending'])), toolCalls: 0, completedNodes: 0 };
  runs.set(run.id, run); controllers.set(run.id, controller);
  void executeRun(run, provider, tools, config, controller.signal, undefined, { graph: selection?.graph, candidates: selection?.candidates }).then(async () => {
    if (run.status === 'completed' && run.graph && (run.graph.status !== 'hit' || run.graph.selection === 'adapted') && !controller.signal.aborted) {
      try {
        const graph = await graphStore.learn(run, tools, AbortSignal.any([controller.signal, AbortSignal.timeout(60000)]));
        run.graph.learnedGraphId = graph.id; run.graph.learning = graph.validation;
        run.events.push({ seq: run.events.length + 1, at: new Date().toISOString(), type: 'graph', title: `读取图 v${graph.version} 已通过影子验证并保存`, detail: { graphId: graph.id, learning: graph.validation } });
      } catch (error) { run.graph.learningError = errorMessage(error); }
    }
    try { await persistRun(run); }
    catch { run.error = `${run.error || ''} 运行结果未能写入磁盘，请立即从界面导出。`.trim(); }
    finally { controllers.delete(run.id); }
  });
  return run;
}
export function cancelRun(id: string) { const controller = controllers.get(id); if (!controller) return false; controller.abort(); return true; }
