// Standalone types for Needle tool routing — no bside dependency.

export interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: {
    type: 'object';
    properties: Record<string, {
      type: string;
      enum?: string[];
      description?: string;
    }>;
    required?: string[];
  };
}

export interface ToolRoute {
  name: string | null;
  arguments: Record<string, unknown>;
}
