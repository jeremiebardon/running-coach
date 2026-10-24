import type { SseEvent } from "./events";

export type ToolActivity = {
  name: string;
  input: Record<string, unknown>;
  output?: unknown;
  status: "running" | "done";
};

export type Message =
  | { role: "user"; text: string }
  | {
      role: "assistant";
      text: string;
      tools: ToolActivity[];
      status: "streaming" | "done" | "error";
      error?: string;
    };

export type ChatState = {
  sessionId: string | null;
  messages: Message[];
};

/** Stream events, plus the three things the user (or the network) can do to a turn. */
export type ChatAction = SseEvent | { type: "send"; text: string } | { type: "abort" } | { type: "retry" };

export const initialChatState: ChatState = { sessionId: null, messages: [] };

const streamingAssistant = (): Message => ({ role: "assistant", text: "", tools: [], status: "streaming" });

export function reduceChat(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "send":
      return {
        ...state,
        messages: [...state.messages, { role: "user", text: action.text }, streamingAssistant()],
      };
    case "session":
      return { ...state, sessionId: action.sessionId };
    case "tool_call":
      return updateStreaming(state, (m) => ({
        ...m,
        tools: [...m.tools, { name: action.name, input: action.input, status: "running" }],
      }));
    case "tool_result":
      return updateStreaming(state, (m) => {
        const i = m.tools.findIndex((t) => t.name === action.name && t.status === "running");
        if (i === -1) return m;
        const tools = m.tools.map((t, j): ToolActivity => (j === i ? { ...t, output: action.output, status: "done" } : t));
        return { ...m, tools };
      });
    case "token":
      return updateStreaming(state, (m) => ({ ...m, text: m.text + action.text }));
    case "done":
      return updateStreaming(state, (m) => ({ ...m, text: m.text || action.result.answer, status: "done" }));
    case "error":
      return updateStreaming(state, (m) => ({ ...m, status: "error", error: action.message }));
    case "abort":
      return updateStreaming(state, (m) => ({ ...m, status: "done" }));
    case "retry": {
      const last = state.messages.at(-1);
      if (last?.role !== "assistant" || last.status !== "error") return state;
      return { ...state, messages: [...state.messages.slice(0, -1), streamingAssistant()] };
    }
    default:
      return assertNever(action);
  }
}

type AssistantMessage = Extract<Message, { role: "assistant" }>;

function updateStreaming(state: ChatState, update: (m: AssistantMessage) => AssistantMessage): ChatState {
  const last = state.messages.at(-1);
  if (last?.role !== "assistant" || last.status !== "streaming") return state;
  return { ...state, messages: [...state.messages.slice(0, -1), update(last)] };
}

function assertNever(x: never): never {
  throw new Error(`Unhandled chat action: ${JSON.stringify(x)}`);
}
