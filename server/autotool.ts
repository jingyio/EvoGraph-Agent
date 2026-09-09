import { z } from 'zod';
import { defineTool, type Tool, type ToolContext } from './tools.js';
import { digest } from './graph.js';

type Schema = { type: 'string' | 'integer' | 'number' | 'boolean'; enum?: (string | number)[]; minimum?: number; maximum?: number; minLength?: number; maxLength?: number; description?: string };
export interface ApiSpec {
  openapi: '3.0.3'; info: { title: string; version: string };
  paths: Record<string, { get: { operationId: string; summary: string; parameters: { name: string; in: 'path' | 'query'; required: true; schema: Schema }[]; 'x-resource': string; 'x-data-path'?: string[] } }>;
}
export type ApiTransport = (path: string, query: Record<string, string>, signal: AbortSignal) => Promise<unknown>;

/** Restricted OpenAPI compiler: generates actual typed HTTP tools, never evals code.
 * Specs are curated local API contracts; server URLs/credentials are never taken from specs.
 */
export function acquireTools(spec: ApiSpec, transport: ApiTransport, observe: (value: unknown, resource: string, context: ToolContext) => unknown): Tool[] {
  if (spec.openapi !== '3.0.3' || !spec.info?.title) throw new Error('Unsupported OpenAPI specification');
  const names = new Set<string>();
  return Object.entries(spec.paths).map(([path, methods]) => {
    if (!path.startsWith('/api/') || path.includes('..') || path.includes('?') || Object.keys(methods).some(key => key !== 'get')) throw new Error('AutoTool only permits configured GET API paths');
    const operation = methods.get;
    if (!/^[a-z][a-z0-9_]{0,63}$/.test(operation.operationId) || names.has(operation.operationId)) throw new Error('Duplicate or invalid operation ID');
    names.add(operation.operationId);
    const shape: z.ZodRawShape = {};
    for (const parameter of operation.parameters) {
      if (!/^[a-zA-Z][a-zA-Z0-9_]{0,63}$/.test(parameter.name) || ['constructor', 'prototype', '__proto__'].includes(parameter.name) || Object.hasOwn(shape, parameter.name) || !['path', 'query'].includes(parameter.in) || parameter.required !== true) throw new Error('Unsupported or unsafe OpenAPI parameter');
      const schema = parameter.schema;
      let validator: z.ZodTypeAny;
      if (schema.type === 'string') validator = z.string().min(schema.minLength ?? 1).max(schema.maxLength ?? 500);
      else if (schema.type === 'integer') validator = z.number().int().min(schema.minimum ?? 0).max(schema.maximum ?? Number.MAX_SAFE_INTEGER);
      else if (schema.type === 'number') validator = z.number().finite().min(schema.minimum ?? -Number.MAX_SAFE_INTEGER).max(schema.maximum ?? Number.MAX_SAFE_INTEGER);
      else if (schema.type === 'boolean') validator = z.boolean();
      else throw new Error('Unsupported OpenAPI parameter type');
      if (schema.enum) {
        if (!schema.enum.length) throw new Error('OpenAPI enum cannot be empty');
        const literals = schema.enum.map(value => z.literal(value));
        validator = validator.and(literals.length === 1 ? literals[0] : z.union(literals as [z.ZodLiteral<any>, z.ZodLiteral<any>, ...z.ZodLiteral<any>[]]));
      }
      shape[parameter.name] = schema.description ? validator.describe(schema.description) : validator;
    }
    const placeholders = [...path.matchAll(/\{([^}]+)\}/g)].map(match => match[1]);
    if (placeholders.some(name => !operation.parameters.some(parameter => parameter.in === 'path' && parameter.name === name)) || operation.parameters.some(parameter => parameter.in === 'path' && !placeholders.includes(parameter.name))) throw new Error('OpenAPI path parameters do not match placeholders');
    const tool = defineTool(operation.operationId, operation.summary, 'read', shape, async (args, context) => {
      let resolved = path;
      const query: Record<string, string> = {};
      for (const parameter of operation.parameters) {
        if (parameter.in === 'path') {
          const value = String(args[parameter.name]);
          if (value === '.' || value === '..') throw new Error('Dot segments are not valid record identifiers');
          resolved = resolved.replaceAll('{' + parameter.name + '}', encodeURIComponent(value));
        } else query[parameter.name] = String(args[parameter.name]);
      }
      let value = await transport(resolved, query, context.signal);
      for (const key of operation['x-data-path'] || []) {
        if (['__proto__', 'constructor', 'prototype'].includes(key) || !value || typeof value !== 'object' || !Object.hasOwn(value, key)) throw new Error('API response does not match the acquired data path');
        value = (value as Record<string, unknown>)[key];
      }
      return observe(value, operation['x-resource'], context);
    });
    tool.origin = { kind: 'autotool', spec: spec.info.title, operationId: operation.operationId, digest: digest(spec) };
    return tool;
  });
}
