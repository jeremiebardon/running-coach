import "dotenv/config";
import { appendFileSync, readFileSync, writeFileSync } from "node:fs";
import { createDataset } from "@arizeai/phoenix-client/datasets";
import { runExperiment } from "@arizeai/phoenix-client/experiments";
import type { ExperimentTask } from "@arizeai/phoenix-client/types/experiments";
import { FixtureTrainingDataAdapter } from "../src/adapters/fixtures/fixture.adapter.js";
import { createCoachAgent, runTurn } from "../src/agent/coach-agent.js";
import { COACH_PROMPT_VERSION } from "../src/agent/instructions.js";
import { DEFAULT_FIXTURE, coachModel, judgeModel } from "../src/config/composition.js";
import { initTelemetry } from "../src/observability/telemetry.js";
import { fixedClock } from "../src/ports/training-data.port.js";
import { DATASET_NAME, examples } from "./dataset.js";
import { efficiency, llmJudges, mustMatch, numbersGrounded, toolSelection, type CoachTaskOutput } from "./evaluators.js";

/**
 * Offline evaluation = the agent's "test suite".
 *
 * - Data: fixtures + frozen clock → identical inputs on every run, so a score
 *   change means the AGENT changed (prompt, model, tools), not the data.
 * - Phoenix stores the dataset, each experiment, every task trace and every
 *   evaluator result → compare experiments side by side in the UI.
 * - Exit code is the CI gate (thresholds.json).
 *
 * Flags: --code-only (skip LLM judges, cheaper) · --repetitions=N (variance)
 */
const args = new Set(process.argv.slice(2));
const codeOnly = args.has("--code-only");
const repetitions = Number([...args].find((a) => a.startsWith("--repetitions="))?.split("=")[1] ?? 1);

initTelemetry({ projectName: "running-coach-evals", withPhoenixProvider: false });

const clock = fixedClock("2026-10-17");
const data = new FixtureTrainingDataAdapter(process.env.FIXTURE_PATH ?? DEFAULT_FIXTURE, clock);

const task: ExperimentTask = async (example) => {
  const question = String(example.input.question);
  const agent = createCoachAgent({ model: coachModel(), data, clock });
  const turn = await runTurn(agent, [{ role: "user", content: question }], {
    sessionId: `eval-${example.id}`,
    metadata: { surface: "eval", category: example.metadata?.category },
  });
  const output: CoachTaskOutput = {
    answer: turn.answer,
    toolNames: turn.toolCalls.map((t) => t.name),
    toolEvidence: JSON.stringify(turn.toolCalls.map(({ name, input, output }) => ({ name, input, output }))),
    steps: turn.steps,
  };
  return output as unknown as Record<string, unknown>;
};

const dataset = await createDataset({
  name: DATASET_NAME,
  description: "Golden questions for the running coach (fixture athlete, frozen clock)",
  examples,
});

const sha = process.env.GITHUB_SHA?.slice(0, 7) ?? "local";
const experiment = await runExperiment({
  experimentName: `${COACH_PROMPT_VERSION}-${process.env.COACH_MODEL ?? "claude-sonnet-5-5"}-${sha}`,
  experimentDescription: `prompt=${COACH_PROMPT_VERSION} model=${process.env.COACH_MODEL ?? "default"} sha=${sha}`,
  experimentMetadata: { promptVersion: COACH_PROMPT_VERSION, sha, branch: process.env.GITHUB_HEAD_REF ?? "local" },
  dataset,
  task,
  evaluators: [toolSelection, mustMatch, numbersGrounded, efficiency, ...(codeOnly ? [] : llmJudges(judgeModel()))],
  concurrency: 3,
  repetitions,
  setGlobalTracerProvider: true, // so our coach.turn root span + AI SDK spans join the task trace
});

/* ------------------------------ CI gate ------------------------------ */
const thresholds: Record<string, number> = JSON.parse(readFileSync(new URL("./thresholds.json", import.meta.url), "utf8"));
const byEvaluator = new Map<string, number[]>();
let evaluatorErrors = 0;
for (const run of experiment.evaluationRuns ?? []) {
  if (run.error || run.result?.score == null) {
    evaluatorErrors++;
    continue;
  }
  byEvaluator.set(run.name, [...(byEvaluator.get(run.name) ?? []), run.result.score]);
}
const taskErrors = Object.values(experiment.runs).filter((r) => r.error).length;

const rows = [...byEvaluator.entries()].map(([name, scores]) => {
  const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
  const min = thresholds[name];
  return { name, mean, min, pass: min === undefined || mean >= min, n: scores.length };
});
const passed = rows.every((r) => r.pass) && taskErrors === 0;

const report = [
  `## 🏃 Coach evals — ${passed ? "✅ passed" : "❌ failed"}`,
  `Experiment \`${experiment.id}\` · prompt \`${COACH_PROMPT_VERSION}\` · ${Object.keys(experiment.runs).length} runs · task errors: ${taskErrors} · evaluator errors: ${evaluatorErrors}`,
  "",
  "| evaluator | mean | threshold | n | |",
  "|---|---|---|---|---|",
  ...rows.map((r) => `| ${r.name} | ${r.mean.toFixed(2)} | ${r.min ?? "—"} | ${r.n} | ${r.pass ? "✅" : "❌"} |`),
].join("\n");

console.log(`\n${report}\n`);
writeFileSync("eval-report.md", report + "\n");
if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, report + "\n");
process.exit(passed ? 0 : 1);
