export interface ToolCard {
  name: string;
  description: string;
  effect: 'read' | 'artifact';
  parameters: Record<string, unknown>;
  outputs?: string[];
  origin?: { kind: 'autotool'; spec: string; operationId: string; digest: string };
}
