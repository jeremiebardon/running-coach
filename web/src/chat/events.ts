export type DoneBody = {
  sessionId: string;
  answer: string;
  tools: string[];
  steps: number;
  usage: { input_tokens: number; output_tokens: number };
};

export type SseEvent =
  | { type: "session"; sessionId: string }
  | { type: "tool_call"; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; name: string; output: unknown }
  | { type: "token"; text: string }
  | { type: "done"; result: DoneBody }
  | { type: "error"; message: string };
