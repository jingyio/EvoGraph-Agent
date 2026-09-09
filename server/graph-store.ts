import { randomUUID } from 'node:crypto';
import { mkdir, readFile, readdir, rename, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import type { AgentRun, RunRequest, TaskGraph } from '../shared/types.js';
import { compileReadGraph, contractHash, digest, graphApplicable, graphSchema, orderedNodes, runReadGraph, taskKey } from './graph.js';
import { createRun } from './runtime.js';
import type { Tool } from './tools.js';
import { retrieveWorkflows } from './gagent.js';

export class GraphStore {
  private graphs = new Map<string, TaskGraph>();
  private queue: Promise<unknown> = Promise.resolve();
  constructor(private directory = resolve('artifacts/graphs')) {}
  async restore() {
    await mkdir(this.directory, { recursive: true, mode: 0o700 });
    for (const file of await readdir(this.directory)) {
      if (!/^[a-f\d-]{36}\.json$/.test(file)) continue;
      try {
        const graph = graphSchema.parse(JSON.parse(await readFile(join(this.directory, file), 'utf8'))) as TaskGraph;
        if (graph.id + '.json' === file) this.graphs.set(graph.id, graph);
      } catch { /* Invalid artifacts are never promoted into executable graphs. */ }
    }
  }
  list(scenario?: RunRequest['scenario'], source?: RunRequest['source']) {
    return [...this.graphs.values()].filter(graph => (!scenario || graph.scenario === scenario) && (!source || graph.source === source)).sort((a, b) => b.version - a.version || b.createdAt.localeCompare(a.createdAt));
  }
  get(id: string) { return this.graphs.get(id); }
  select(request: RunRequest, tools: Tool[]) {
    const candidates = this.list(request.scenario, request.source);
    const environment = environmentHash(request.source);
    for (const graph of candidates) if (!graphApplicable(graph, request, tools, environment)) return { graph, candidates: [], reason: undefined };
    return { graph: undefined, candidates: retrieveWorkflows(candidates, request, tools, environment), reason: candidates.length ? graphApplicable(candidates[0], request, tools, environment) || undefined : '尚无经过校验的历史读取图' };
  }
  async learn(run: AgentRun, tools: Tool[], signal: AbortSignal = AbortSignal.timeout(60000)): Promise<TaskGraph> {
    // Serialize learning so concurrent completions cannot assign duplicate versions.
    const operation = this.queue.then(async () => {
      const existing = this.list().find(graph => graph.sourceRunId === run.id && graph.contractHash === contractHash(tools) && graph.environmentHash === environmentHash(run.request.source));
      if (existing) return existing;
      signal.throwIfAborted();
      const begin = Date.now();
      const nodes = compileReadGraph(run, tools);
      orderedNodes(nodes, tools);
      const compileMs = Date.now() - begin;
      const probe = createRun({ ...run.request, strategy: 'react' }, null);
      probe.initial = structuredClone(run.initial); probe.state = structuredClone(run.initial);
      const context = { run: probe, signal, evidence: new Set<string>() };
      let calls = 0;
      const validationStart = Date.now();
      await runReadGraph(nodes, tools, {
        invoke: async (name, args) => {
          signal.throwIfAborted();
          if (++calls > 60) throw new Error('影子验证超过 60 次读取，拒绝发布任务图');
          const tool = tools.find(tool => tool.name === name)!;
          return tool.execute(args, context);
        }, node: () => {},
      }, signal);
      if (digest(probe.state) !== digest(probe.initial)) throw new Error('读取工具修改了业务状态，拒绝学习');
      const key = taskKey(run.request.task);
      const preceding = this.list(run.request.scenario, run.request.source).filter(graph => graph.taskKey === key);
      const graph: TaskGraph = {
        id: randomUUID(), version: Math.max(0, ...preceding.map(graph => graph.version)) + 1,
        createdAt: new Date().toISOString(), sourceRunId: run.id, scenario: run.request.scenario, source: run.request.source,
        task: run.request.task, taskKey: key, contractHash: contractHash(tools), environmentHash: environmentHash(run.request.source), nodes,
        sourceModelRequests: run.metrics.modelRequests, sourceInputTokens: run.metrics.inputTokens, sourceOutputTokens: run.metrics.outputTokens,
        validation: { status: 'passed', toolCalls: calls, durationMs: Date.now() - validationStart, compileMs, learningModelRequests: 0 },
        scope: 'read-prefix', compilerVersion: 1,
      };
      graphSchema.parse(graph);
      await mkdir(this.directory, { recursive: true, mode: 0o700 });
      const path = join(this.directory, graph.id + '.json');
      await writeFile(path + '.tmp', JSON.stringify(graph, null, 2), { mode: 0o600 });
      await rename(path + '.tmp', path);
      this.graphs.set(graph.id, graph);
      return graph;
    });
    this.queue = operation.catch(() => {});
    return operation;
  }
}

export function environmentHash(source: RunRequest['source']) {
  // Instance URL participates in the guard; secrets never enter the graph file.
  const url = source === 'sandbox' ? 'synthetic-v1' : process.env[source.toUpperCase() + '_BASE_URL'] || 'unconfigured';
  return digest({ source, url });
}
export const graphStore = new GraphStore();
