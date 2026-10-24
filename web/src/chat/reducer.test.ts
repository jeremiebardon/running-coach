import { describe, expect, it } from "vitest";
import type { ChatAction, ChatState } from "./reducer";
import { initialChatState, reduceChat } from "./reducer";

const replay = (actions: ChatAction[], from: ChatState = initialChatState) => actions.reduce(reduceChat, from);

const done = (answer: string, sessionId = "s1") => ({
  type: "done" as const,
  result: { sessionId, answer, tools: [], steps: 1, usage: { input_tokens: 1, output_tokens: 1 } },
});

describe("chat reducer", () => {
  it("happy path: session, tool call, tool result, tokens, done", () => {
    const state = replay([
      { type: "send", text: "How was my run?" },
      { type: "session", sessionId: "s1" },
      { type: "tool_call", name: "get_activity_details", input: { date: "2026-10-17" } },
      { type: "tool_result", name: "get_activity_details", output: { distance_km: 10 } },
      { type: "token", text: "Nice " },
      { type: "token", text: "run." },
      done("Nice run."),
    ]);

    expect(state).toEqual({
      sessionId: "s1",
      messages: [
        { role: "user", text: "How was my run?" },
        {
          role: "assistant",
          text: "Nice run.",
          status: "done",
          tools: [
            {
              name: "get_activity_details",
              input: { date: "2026-10-17" },
              output: { distance_km: 10 },
              status: "done",
            },
          ],
        },
      ],
    });
  });

  it("mid-stream error keeps the partial text and marks the reply as failed", () => {
    const state = replay([
      { type: "send", text: "Plan my week" },
      { type: "session", sessionId: "s1" },
      { type: "token", text: "Monday: " },
      { type: "error", message: "boom" },
      { type: "token", text: "ignored late token" },
    ]);

    expect(state.sessionId).toBe("s1");
    expect(state.messages.at(-1)).toEqual({
      role: "assistant",
      text: "Monday: ",
      tools: [],
      status: "error",
      error: "boom",
    });
  });

  it("abort stops the reply but keeps what streamed so far", () => {
    const state = replay([
      { type: "send", text: "Plan my week" },
      { type: "token", text: "Monday: " },
      { type: "abort" },
      { type: "token", text: "late" },
    ]);

    expect(state.messages.at(-1)).toMatchObject({ text: "Monday: ", status: "done" });
  });

  it("retry after an error replaces the failed reply with a fresh streaming one, keeping the user message once", () => {
    const failed = replay([
      { type: "send", text: "Plan my week" },
      { type: "session", sessionId: "s1" },
      { type: "tool_call", name: "get_plan", input: {} },
      { type: "error", message: "boom" },
    ]);

    const state = replay(
      [{ type: "retry" }, { type: "token", text: "Monday: easy." }, done("Monday: easy.")],
      failed,
    );

    expect(state.sessionId).toBe("s1");
    expect(state.messages).toEqual([
      { role: "user", text: "Plan my week" },
      { role: "assistant", text: "Monday: easy.", tools: [], status: "done" },
    ]);
  });

  it("retry is a no-op unless the last reply failed", () => {
    const ok = replay([{ type: "send", text: "hi" }, done("hello")]);
    expect(reduceChat(ok, { type: "retry" })).toBe(ok);
  });

  it("tokens only: a reply with no tool activity", () => {
    const state = replay([
      { type: "send", text: "hi" },
      { type: "session", sessionId: "s1" },
      { type: "token", text: "Hel" },
      { type: "token", text: "lo" },
      done("Hello"),
    ]);

    expect(state.messages.at(-1)).toEqual({ role: "assistant", text: "Hello", tools: [], status: "done" });
  });

  it("multiple tool calls stay in order and pair results with their calls", () => {
    const state = replay([
      { type: "send", text: "compare" },
      { type: "tool_call", name: "get_activity_details", input: { date: "a" } },
      { type: "tool_call", name: "get_activity_details", input: { date: "b" } },
      { type: "tool_result", name: "get_activity_details", output: "A" },
      { type: "tool_result", name: "get_activity_details", output: "B" },
      { type: "tool_call", name: "predict_race_time", input: {} },
    ]);

    const reply = state.messages.at(-1);
    expect(reply).toMatchObject({
      status: "streaming",
      tools: [
        { name: "get_activity_details", input: { date: "a" }, output: "A", status: "done" },
        { name: "get_activity_details", input: { date: "b" }, output: "B", status: "done" },
        { name: "predict_race_time", input: {}, status: "running" },
      ],
    });
  });

  it("an unknown tool name is recorded like any other", () => {
    const state = replay([
      { type: "send", text: "hi" },
      { type: "tool_call", name: "some_future_tool", input: { x: 1 } },
      { type: "tool_result", name: "some_future_tool", output: null },
      done("ok"),
    ]);

    expect(state.messages.at(-1)).toMatchObject({
      status: "done",
      tools: [{ name: "some_future_tool", input: { x: 1 }, output: null, status: "done" }],
    });
  });
});
