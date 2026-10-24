import type { SseEvent } from "./events";

export type SseParser = {
  /** Feed the next chunk; returns the events completed by it. */
  push(chunk: string | Uint8Array): SseEvent[];
};

export function createSseParser(): SseParser {
  const decoder = new TextDecoder();
  let buffer = "";

  return {
    push(chunk) {
      buffer += typeof chunk === "string" ? chunk : decoder.decode(chunk, { stream: true });
      buffer = buffer.replaceAll("\r\n", "\n");
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      return frames.flatMap(parseFrame);
    },
  };
}

function parseFrame(frame: string): SseEvent[] {
  let name = "";
  const data: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!name) return [];
  const body = JSON.parse(data.join("\n"));
  switch (name) {
    case "session":
      return [{ type: "session", sessionId: body.sessionId }];
    case "tool_call":
      return [{ type: "tool_call", name: body.name, input: body.input }];
    case "tool_result":
      return [{ type: "tool_result", name: body.name, output: body.output }];
    case "token":
      return [{ type: "token", text: body.text }];
    case "done":
      return [{ type: "done", result: body }];
    case "error":
      return [{ type: "error", message: body.message }];
    default:
      return [];
  }
}
