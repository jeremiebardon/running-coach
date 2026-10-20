import { MockLanguageModelV4 } from "ai/test";
import { describe, expect, it } from "vitest";
import { FixtureTrainingDataAdapter } from "../src/adapters/fixtures/fixture.adapter.js";
import { createCoachAgent } from "../src/agent/coach-agent.js";
import { DEFAULT_FIXTURE } from "../src/config/composition.js";
import { fixedClock } from "../src/ports/training-data.port.js";
import { createApp } from "../src/server/app.js";
import { InMemorySessionStore } from "../src/server/session-store.js";

const usage = {
  inputTokens: { total: 10, noCache: 10, cacheRead: 0, cacheWrite: 0 },
  outputTokens: { total: 5, text: 5, reasoning: 0 },
};
const reply = (text: string) => ({
  content: [{ type: "text" as const, text }],
  finishReason: { unified: "stop" as const, raw: "end_turn" },
  usage,
  warnings: [],
});

function setup() {
  const clock = fixedClock("2026-10-17");
  const model = new MockLanguageModelV4({ doGenerate: [reply("First answer"), reply("Second answer")] });
  const sessions = new InMemorySessionStore();
  const app = createApp({
    agent: createCoachAgent({ model, data: new FixtureTrainingDataAdapter(DEFAULT_FIXTURE, clock), clock }),
    sessions,
    dataSource: "fixtures",
  });
  return { app, model, sessions };
}

const post = (app: ReturnType<typeof setup>["app"], body: unknown) =>
  app.request("/chat", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

describe("HTTP server", () => {
  it("GET /health", async () => {
    const res = await setup().app.request("/health");
    expect(await res.json()).toEqual({ status: "ok", dataSource: "fixtures" });
  });

  it("rejects an invalid body", async () => {
    expect((await post(setup().app, { nope: true })).status).toBe(400);
  });

  it("keeps conversation history per session", async () => {
    const { app, model } = setup();
    const first = (await (await post(app, { message: "Hi coach" })).json()) as { sessionId: string; answer: string };
    expect(first.answer).toBe("First answer");

    const second = (await (await post(app, { message: "And now?", sessionId: first.sessionId })).json()) as { answer: string };
    expect(second.answer).toBe("Second answer");

    // The 2nd model call received the whole conversation (user, assistant, user)
    const prompt = JSON.stringify(model.doGenerateCalls[1]?.prompt);
    expect(prompt).toContain("Hi coach");
    expect(prompt).toContain("First answer");
    expect(prompt).toContain("And now?");
  });
});
