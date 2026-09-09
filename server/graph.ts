import { createHash } from 'node:crypto';
import { z } from 'zod';
import type { AgentRun, GraphBinding, GraphNode, JsonValue, TaskGraph } from '../shared/types.js';
import type { Tool } from './tools.js';

const safePart = z.string().min(1).max(100).refine(value => !['__proto__', 'constructor', 'prototype'].includes(value));
const pathSchema = z.array(safePart).max(8);
const literal = z.unknown().refine(value => JSON.stringify(value) !== undefined && JSON.stringify(value).length <= 8000);
const bindingSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('literal'), value: literal }).strict(),
  z.object({ kind: z.literal('item'), path: pathSchema }).strict(),
  z.object({ kind: z.literal('result'), nodeId: safePart, path: pathSchema }).strict(),
]);
const nodeSchema = z.object({ id: safePart, tool: safePart, arguments: z.record(safePart, bindingSchema), dependencies: z.array(safePart).max(40), foreach: z.object({ nodeId: safePart, collectionPath: pathSchema.nullable() }).strict().optional(), paginate: z.object({ maxPages: z.number().int().min(1).max(20) }).strict().optional(), sourceEventSeqs: z.array(z.number().int().positive()).min(1) }).strict();
export const graphSchema = z.object({
  id: z.string().uuid(), version: z.number().int().positive(), createdAt: z.string(), sourceRunId: z.string().uuid(), scenario: z.enum(['finance', 'support']), source: z.enum(['sandbox', 'erpnext', 'zammad']), task: z.string().max(6000), taskKey: z.string(), contractHash: z.string(), environmentHash: z.string(), nodes: z.array(nodeSchema).min(1).max(40), sourceModelRequests: z.number().int().positive(), sourceInputTokens: z.number().nullable(), sourceOutputTokens: z.number().nullable(), validation: z.object({ status: z.literal('passed'), toolCalls: z.number().int().nonnegative(), durationMs: z.number().nonnegative(), compileMs: z.number().nonnegative(), learningModelRequests: z.literal(0) }).strict(), scope: z.literal('read-prefix'), compilerVersion: z.literal(1),
}).strict();

export function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, entry]) => JSON.stringify(key) + ':' + canonical(entry)).join(',') + '}';
  return JSON.stringify(value);
}
export function digest(value: unknown) { return createHash('sha256').update(canonical(value)).digest('hex'); }
export function taskKey(task: string) {
  // Only the explicit inspection clock is abstracted. IDs, amounts, dates,
  // constraints and wording remain part of the match; no semantic guessing.
  return digest(task.replace(/以\s*\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\s*为本次巡检时刻/g, '以<inspection-clock>为本次巡检时刻').replace(/\s+/g, ' ').trim());
}
export function contractHash(tools: Tool[]) { return digest(tools.map(({ name, parameters, effect, description }) => ({ name, parameters, effect, description })).sort((a, b) => a.name.localeCompare(b.name))); }
export function pathValue(value: unknown, path: string[]): unknown {
  for (const key of path) {
    if (['__proto__', 'constructor', 'prototype'].includes(key) || !value || typeof value !== 'object' || !Object.hasOwn(value, key)) throw new Error(`图参数路径不存在：${path.join('.')}`);
    value = (value as Record<string, unknown>)[key];
  }
  return value;
}
type Sample = { node: GraphNode; observations: unknown[] };
type Candidate = { nodeId: string; collectionPath: string[] | null; fieldPath: string[]; score: number };

function candidates(samples: Sample[], toolName: string, parameter: string, value: unknown): Candidate[] {
  const result: Candidate[] = [];
  const entity = parameter.replace(/_?id$/i, '').toLowerCase();
  for (const sample of samples) {
    if (sample.node.tool === toolName) continue;
    for (const observation of sample.observations) {
      let rows: unknown[], collectionPath: string[] | null;
      if (Array.isArray(observation)) { rows = observation; collectionPath = []; }
      else if (observation && typeof observation === 'object' && Array.isArray((observation as any).records)) { rows = (observation as any).records; collectionPath = ['records']; }
      else { rows = [observation]; collectionPath = null; }
      for (const row of rows) {
        if (!row || typeof row !== 'object') continue;
        for (const [key, entry] of Object.entries(row)) {
          if (entry !== value || typeof entry === 'object' || ['__proto__', 'constructor', 'prototype'].includes(key)) continue;
          const semanticField = key.replace(/_?id$/i, '').toLowerCase();
          const identifierField = ['id', 'name'].includes(key);
          let score = semanticField === entity ? 90 : identifierField ? 35 : 0;
          if (identifierField && sample.node.tool.toLowerCase().includes(entity)) score += 80;
          if (parameter === 'customerId' && key === 'party') score += 75;
          if (parameter === 'query' && ['subject', 'title', 'body'].includes(key)) score += 70;
          if (collectionPath !== null) score += 10;
          if (score >= 70) result.push({ nodeId: sample.node.id, collectionPath, fieldPath: [key], score });
        }
      }
    }
  }
  return result.sort((a, b) => b.score - a.score);
}

/** Infer a bounded dataflow DAG from observed, successful reads before any write.
 * No tool sequence is authored per scenario, and no observation/report is cached.
 */
export function compileReadGraph(run: AgentRun, tools: Tool[]): GraphNode[] {
  if (run.request.mode !== 'live' || run.status !== 'completed' || run.metrics.modelRequests < 1) throw new Error('仅从正常结束的真实模型运行学习；离线流程不可用作学习来源。');
  const samples: Sample[] = [];
  const known = new Map(tools.map(tool => [tool.name, tool]));
  for (let index = 0; index < run.events.length; index++) {
    const action = run.events[index];
    if (action.type !== 'action') continue;
    const tool = known.get(action.title);
    if (!tool || tool.effect !== 'read') break;
    const observation = run.events.slice(index + 1).find(event => event.type === 'observation' || event.type === 'action');
    if (observation?.type !== 'observation') continue;
    const payload = observation.detail as { ok: boolean; result: unknown };
    if (!payload?.ok) continue; // Failed calls are evidence of repair, not reusable nodes.
    let args: Record<string, JsonValue>;
    try { args = JSON.parse((action.detail as any).arguments); } catch { continue; }
    if (!args || Array.isArray(args) || typeof args !== 'object') continue;
    const bindings: Record<string, GraphBinding> = {};
    let iteration: GraphNode['foreach'];
    let canCompile = true;
    for (const [parameter, value] of Object.entries(args)) {
      const properties = tool.parameters.properties as Record<string, any> | undefined;
      const enumValue = properties?.[parameter]?.enum?.includes(value);
      const dynamic = /id$/i.test(parameter) || ['query', 'category'].includes(parameter);
      const found = dynamic ? candidates(samples, tool.name, parameter, value) : [];
      if (found.length) {
        const best = iteration ? found.find(item => item.nodeId === iteration!.nodeId && canonical(item.collectionPath) === canonical(iteration!.collectionPath)) : found[0];
        if (!best) { canCompile = false; break; }
        iteration = { nodeId: best.nodeId, collectionPath: best.collectionPath };
        bindings[parameter] = { kind: 'item', path: best.fieldPath };
      } else if (dynamic && !enumValue) { canCompile = false; break; }
      else if (enumValue || (['page', 'pageSize'].includes(parameter) && typeof value === 'number')) bindings[parameter] = { kind: 'literal', value };
      else { canCompile = false; break; } // Dates, amounts and free text need explicit binding, never frozen from a trace.
    }
    if (!canCompile) break; // Leave the rest to the model; never retain an old ID.
    const result = payload.result as any;
    let paginate: GraphNode['paginate'];
    if ('page' in args && 'pageSize' in args && Array.isArray(result?.records) && typeof result?.mayHaveMore === 'boolean') {
      const preceding = samples.find(sample => sample.node.tool === tool.name && sample.node.paginate && canonical({ ...sample.node.arguments, page: undefined }) === canonical({ ...bindings, page: undefined }));
      if (args.page === 1 || preceding) { bindings.page = { kind: 'literal', value: 1 }; paginate = { maxPages: 20 }; }
    }
    const equivalent = samples.find(sample => sample.node.tool === tool.name && canonical(sample.node.arguments) === canonical(bindings) && canonical(sample.node.foreach ?? null) === canonical(iteration ?? null) && Boolean(sample.node.paginate) === Boolean(paginate));
    if (equivalent) { equivalent.observations.push(structuredClone(payload.result)); equivalent.node.sourceEventSeqs.push(action.seq); continue; }
    if (samples.length >= 40) break;
    const node: GraphNode = { id: `n${samples.length + 1}`, tool: tool.name, arguments: bindings, dependencies: iteration ? [iteration.nodeId] : [], ...(iteration ? { foreach: iteration } : {}), ...(paginate ? { paginate } : {}), sourceEventSeqs: [action.seq] };
    samples.push({ node, observations: [structuredClone(payload.result)] });
  }
  if (!samples.length) throw new Error('轨迹没有可安全编译的读取前缀。');
  return samples.map(item => item.node);
}

export function orderedNodes(nodes: GraphNode[], tools: Tool[]): GraphNode[] {
  const ids = new Set(nodes.map(node => node.id));
  if (ids.size !== nodes.length) throw new Error('任务图存在重复节点 ID');
  const done = new Set<string>(), ordered: GraphNode[] = [];
  for (const node of nodes) {
    if (tools.find(tool => tool.name === node.tool)?.effect !== 'read') throw new Error(`任务图禁止执行非读取工具：${node.tool}`);
    const actual = new Set([...(node.foreach ? [node.foreach.nodeId] : []), ...Object.values(node.arguments).flatMap(binding => binding.kind === 'result' ? [binding.nodeId] : [])]);
    if (node.dependencies.some(id => !ids.has(id)) || [...actual].some(id => !node.dependencies.includes(id))) throw new Error('任务图缺少数据依赖');
    if (!node.foreach && Object.values(node.arguments).some(binding => binding.kind === 'item')) throw new Error('item 参数缺少 foreach 来源');
  }
  while (ordered.length < nodes.length) {
    const next = nodes.find(node => !done.has(node.id) && node.dependencies.every(id => done.has(id)));
    if (!next) throw new Error('任务图存在循环依赖');
    ordered.push(next); done.add(next.id);
  }
  return ordered;
}

export interface GraphRunnerHooks {
  invoke: (tool: string, args: Record<string, unknown>, nodeId: string) => Promise<unknown>;
  node: (nodeId: string, state: 'running' | 'done' | 'failed') => void;
}
export async function runReadGraph(nodes: GraphNode[], tools: Tool[], hooks: GraphRunnerHooks, signal: AbortSignal) {
  const outputs = new Map<string, unknown[]>();
  for (const node of orderedNodes(nodes, tools)) {
    signal.throwIfAborted(); hooks.node(node.id, 'running');
    try {
      let items: unknown[] = [null];
      if (node.foreach) {
        const values = outputs.get(node.foreach.nodeId);
        if (!values) throw new Error('读取图缺少上游输出');
        items = node.foreach.collectionPath === null ? values : values.flatMap(value => {
          const array = pathValue(value, node.foreach!.collectionPath!);
          if (!Array.isArray(array)) throw new Error('上游集合形状发生变化');
          return array;
        });
        if (items.length > 1000) throw new Error('上游记录超过读取图的 1000 条限制');
      }
      const values: unknown[] = [], seen = new Set<string>();
      for (const item of items) {
        const args: Record<string, unknown> = {};
        for (const [parameter, binding] of Object.entries(node.arguments)) {
          if (['__proto__', 'constructor', 'prototype'].includes(parameter)) throw new Error('无效参数键');
          if (binding.kind === 'literal') args[parameter] = structuredClone(binding.value);
          else if (binding.kind === 'item') args[parameter] = pathValue(item, binding.path);
          else {
            const source = outputs.get(binding.nodeId);
            if (!source || source.length !== 1) throw new Error('单值参数来源不唯一');
            args[parameter] = pathValue(source[0], binding.path);
          }
        }
        const signature = canonical(args);
        if (seen.has(signature)) continue;
        seen.add(signature);
        for (let page = 1; page <= (node.paginate?.maxPages ?? 1); page++) {
          signal.throwIfAborted();
          const result = await hooks.invoke(node.tool, node.paginate ? { ...args, page } : args, node.id);
          values.push(structuredClone(result));
          if (!node.paginate) break;
          const envelope = result as any;
          if (!Array.isArray(envelope?.records) || typeof envelope.mayHaveMore !== 'boolean') throw new Error('分页接口返回形状变化');
          if (!envelope.mayHaveMore) break;
          if (page === node.paginate.maxPages) throw new Error('达到任务图分页上限，交由模型处理未读取部分');
        }
      }
      outputs.set(node.id, values); hooks.node(node.id, 'done');
    } catch (error) { hooks.node(node.id, 'failed'); throw error; }
  }
  return outputs;
}

export function graphApplicable(graph: TaskGraph, request: AgentRun['request'], tools: Tool[], environmentHash: string) {
  if (graph.scenario !== request.scenario || graph.source !== request.source) return '场景或数据源不匹配';
  if (graph.taskKey !== taskKey(request.task)) return '任务要求发生变化，使用 ReAct 处理';
  if (graph.contractHash !== contractHash(tools)) return '工具契约发生变化';
  if (graph.environmentHash !== environmentHash) return '业务实例发生变化';
  return null;
}
