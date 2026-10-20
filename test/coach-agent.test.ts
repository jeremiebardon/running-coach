import { MockLanguageModelV4 } from "ai/test";
import { describe, expect, it } from "vitest";
import { FixtureTrainingDataAdapter } from "../src/adapters/fixtures/fixture.adapter.js";
import { createCoachAgent, runTurn } from "../src/agent/coach-agent.js";
import { createCoachTools } from "../src/agent/tools.js";
import { DEFAULT_FIXTURE } from "../src/config/composition.js";
import { fixedClock } from "../src/ports/training-data.port.js";

const clock = fixedClock("2026-10-17");
const data = new FixtureTrainingDataAdapter(DEFAULT_FIXTURE, clock);

const usage = {
  inputTokens: { total: 10, noCache: 10, cacheRead: 0, cacheWrite: 0 },
  outputTokens: { total: 5, text: 5, reasoning: 0 },
};

describe("coach agent loop (mock model, fixture data)", () => {
  it("calls predict_race_time, feeds the result back, then answers", async () => {
    const model = new MockLanguageModelV4({
      doGenerate: [
        {
          content: [
            {
              type: "tool-call",
              toolCallId: "call-1",
              toolName: "predict_race_time",
              input: JSON.stringify({ distance: "marathon", targetTime: "2:55:00" }),
            },
          ],
          finishReason: { unified: "tool-calls", raw: "tool_use" },
          usage,
          warnings: [],
        },
        {
          content: [{ type: "text", text: "Borderline: current fitness predicts about 2:58." }],
          finishReason: { unified: "stop", raw: "end_turn" },
          usage,
          warnings: [],
        },
      ],
    });

    const agent = createCoachAgent({ model, data, clock });
    const turn = await runTurn(agent, [{ role: "user", content: "Could I run a sub 2:55 marathon?" }], { sessionId: "test" });

    expect(turn.toolCalls.map((t) => t.name)).toEqual(["predict_race_time"]);
    const output = turn.toolCalls[0]?.output as { reference: { label: string }; target: { feasibility: string } };
    expect(output.reference.label).toBe("half");
    expect(output.target.feasibility).toBeDefined();
    expect(turn.answer).toContain("2:58");
    expect(turn.steps).toBe(2);
    // the system prompt carries today's date from the injected clock
    expect(JSON.stringify(model.doGenerateCalls[0]?.prompt)).toContain("2026-10-17");
  });
});

describe("tools on fixture data", () => {
  const tools = createCoachTools({ data, clock });
  const exec = async <T>(t: { execute?: (...args: any[]) => any }, input: unknown): Promise<T> =>
    (await t.execute!(input, { toolCallId: "x", messages: [] })) as T;

  it("finds today's run with its strides", async () => {
    const res = await exec<{ activity: { name: string; workIntervals?: { count: number } } }>(tools.get_activity_details, { date: "2026-10-17" });
    expect(res.activity.name).toBe("Easy run + strides");
    expect(res.activity.workIntervals?.count).toBe(6);
  });

  it("reports best efforts including the half", async () => {
    const res = await exec<Array<{ label: string; summary: string }>>(tools.get_best_efforts, { days: 180 });
    expect(res.find((e) => e.label === "half")?.summary).toMatch(/^half in 1:2\d:\d\d/);
  });

  it("returns an error value (not a throw) when there is no run on a date", async () => {
    const res = await exec<{ error?: string }>(tools.get_activity_details, { date: "2026-10-16" });
    expect(res.error).toMatch(/No run found/);
  });
});
