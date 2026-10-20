import { describe, expect, it } from "vitest";
import { numbersGrounded, toolSelection } from "../evals/evaluators.js";

// Evaluators are code too — test them, or a broken evaluator silently "passes" CI.
const run = (ev: typeof toolSelection, args: Record<string, unknown>) =>
  ev.evaluate({ input: {}, output: null, expected: {}, metadata: {}, ...args } as never);

describe("code evaluators", () => {
  it("tool_selection flags missing and forbidden tools", async () => {
    const ok = await run(toolSelection, {
      output: { toolNames: ["predict_race_time"] },
      expected: { requiredTools: ["predict_race_time"], forbiddenTools: ["build_pacing_plan"] },
    });
    const bad = await run(toolSelection, {
      output: { toolNames: ["build_pacing_plan"] },
      expected: { requiredTools: ["predict_race_time"], forbiddenTools: ["build_pacing_plan"] },
    });
    expect(ok.score).toBe(1);
    expect(bad.score).toBe(0);
  });

  it("numbers_grounded catches an invented time", async () => {
    const evidence = JSON.stringify([{ output: { predicted: { centre: "2:58:53", pace: "4:14/km" } } }]);
    const grounded = await run(numbersGrounded, {
      input: { question: "sub 2:55?" },
      output: { answer: "You'd run about 2:58:53 (4:14/km); 2:55 is a stretch.", toolEvidence: evidence },
    });
    const invented = await run(numbersGrounded, {
      input: { question: "sub 2:55?" },
      output: { answer: "You'd run about 2:51:10.", toolEvidence: evidence },
    });
    expect(grounded.score).toBe(1);
    expect(invented.score).toBe(0);
  });
});
