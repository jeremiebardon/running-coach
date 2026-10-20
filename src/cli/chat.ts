import "dotenv/config";
import { randomUUID } from "node:crypto";
import { createInterface } from "node:readline/promises";
import type { ModelMessage } from "ai";
import { createCoachAgent, runTurn } from "../agent/coach-agent.js";
import { athleteClock, buildDataSource, coachModel } from "../config/composition.js";
import { initTelemetry, shutdownTelemetry } from "../observability/telemetry.js";

initTelemetry({ projectName: process.env.PHOENIX_PROJECT ?? "running-coach", withPhoenixProvider: true });

const clock = athleteClock();
const agent = createCoachAgent({ model: coachModel(), data: buildDataSource(clock), clock });
const sessionId = randomUUID();
const history: ModelMessage[] = [];
const rl = createInterface({ input: process.stdin, output: process.stdout });

console.log(`🏃 Running coach (${process.env.DATA_SOURCE ?? "intervals"} data) — session ${sessionId.slice(0, 8)}. Ctrl+C to quit.\n`);

rl.on("close", async () => {
  await shutdownTelemetry();
  process.exit(0);
});

for (;;) {
  const question = (await rl.question("you › ")).trim();
  if (!question) continue;
  history.push({ role: "user", content: question });
  try {
    const turn = await runTurn(agent, history, { sessionId, metadata: { surface: "cli" } });
    history.push({ role: "assistant", content: turn.answer });
    const tools = turn.toolCalls.map((t) => t.name).join(", ") || "none";
    console.log(`\ncoach › ${turn.answer}\n\x1b[2m[tools: ${tools} · steps: ${turn.steps}]\x1b[0m\n`);
  } catch (err) {
    history.pop();
    console.error(`\n⚠️  ${(err as Error).message}\n`);
  }
}
