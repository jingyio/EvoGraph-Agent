import 'dotenv/config';
import { PRESETS, type PublicConfig } from '../shared/types.js';

function integer(name: string, fallback: number, min: number, max: number): number {
  const value = Number(process.env[name] || fallback);
  if (!Number.isInteger(value) || value < min || value > max) throw new Error(`${name} must be ${min}..${max}`);
  return value;
}
export const config = {
  port: integer('PORT', 4317, 1024, 65535),
  baseUrl: process.env.LLM_BASE_URL || process.env.OPENAI_BASE_URL || 'https://api.openai.com/v1',
  apiKey: process.env.LLM_API_KEY || process.env.OPENAI_API_KEY || '',
  model: process.env.LLM_MODEL || '',
  modelTimeoutMs: integer('LLM_TIMEOUT_MS', 60000, 100, 300000),
  maxSteps: integer('AGENT_MAX_STEPS', 24, 1, 100),
  maxToolCalls: integer('AGENT_MAX_TOOL_CALLS', 60, 1, 200),
  timeoutMs: integer('AGENT_TIMEOUT_MS', 180000, 1000, 900000),
};
export function publicConfig(): PublicConfig {
  return {
    modelConfigured: Boolean(config.apiKey && config.model), model: config.model || null, maxSteps: config.maxSteps,
    connectors: {
      erpnext: Boolean(process.env.ERPNEXT_BASE_URL && process.env.ERPNEXT_API_KEY && process.env.ERPNEXT_API_SECRET),
      zammad: Boolean(process.env.ZAMMAD_BASE_URL && process.env.ZAMMAD_API_TOKEN),
    }, presets: PRESETS,
  };
}
