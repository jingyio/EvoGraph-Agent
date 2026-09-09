import type { Tool } from './tools.js';

export interface ToolCall { id: string; type: 'function'; function: { name: string; arguments: string } }
export interface ChatMessage { role: 'system' | 'user' | 'assistant' | 'tool'; content: string | null; tool_calls?: ToolCall[]; tool_call_id?: string }
export interface Completion { message: ChatMessage; usage?: { input: number; output: number; reasoning?: number }; finishReason: string }
export interface Provider { kind: 'fixture' | 'live'; model: string | null; settings?: { enableThinking: boolean; reasoningEnabled?: boolean }; complete(messages: ChatMessage[], tools: Tool[], signal: AbortSignal): Promise<Completion> }
export interface ModelOptions { baseUrl: string; apiKey: string; model: string; timeoutMs: number }

