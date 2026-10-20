import "dotenv/config";
import { serve } from "@hono/node-server";
import { createCoachAgent } from "../agent/coach-agent.js";
import { athleteClock, buildDataSource, coachModel } from "../config/composition.js";
import { initTelemetry, shutdownTelemetry } from "../observability/telemetry.js";
import { createApp } from "./app.js";
import { InMemorySessionStore } from "./session-store.js";

initTelemetry({ projectName: process.env.PHOENIX_PROJECT ?? "running-coach", withPhoenixProvider: true });

const clock = athleteClock();
const app = createApp({
  agent: createCoachAgent({ model: coachModel(), data: buildDataSource(clock), clock }),
  sessions: new InMemorySessionStore(),
  dataSource: process.env.DATA_SOURCE ?? "intervals",
});

const port = Number(process.env.PORT ?? 3000);
const server = serve({ fetch: app.fetch, port }, (info) => console.log(`🏃 coach server on :${info.port}`));

// `docker compose down` sends SIGTERM: stop accepting requests, flush spans, exit.
for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.on(signal, () => {
    server.close(async () => {
      await shutdownTelemetry();
      process.exit(0);
    });
  });
}
