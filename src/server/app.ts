import { randomUUID } from "node:crypto";
import { Hono } from "hono";
import { z } from "zod";
import { runTurn, type CoachAgent } from "../agent/coach-agent.js";
import type { SessionStore } from "./session-store.js";

const chatBody = z.object({
  message: z.string().trim().min(1).max(4000),
  sessionId: z.string().min(1).max(100).optional(),
});

/**
 * Driving (inbound) adapter: HTTP → agent. Same role as the CLI, different
 * transport. Built as a factory taking its dependencies so it can be tested
 * with `app.request()` and a mock model, no network needed.
 */
export function createApp(deps: { agent: CoachAgent; sessions: SessionStore; dataSource: string }) {
  const app = new Hono();

  app.get("/health", (c) => c.json({ status: "ok", dataSource: deps.dataSource }));

  app.post("/chat", async (c) => {
    const parsed = chatBody.safeParse(await c.req.json().catch(() => null));
    if (!parsed.success) return c.json({ error: "Body must be { message: string, sessionId?: string }" }, 400);

    const sessionId = parsed.data.sessionId ?? randomUUID();
    const history = await deps.sessions.get(sessionId);
    history.push({ role: "user", content: parsed.data.message });

    try {
      const turn = await runTurn(deps.agent, history, { sessionId, metadata: { surface: "http" } });
      history.push({ role: "assistant", content: turn.answer });
      await deps.sessions.save(sessionId, history);
      return c.json({
        sessionId,
        answer: turn.answer,
        tools: turn.toolCalls.map((t) => t.name),
        steps: turn.steps,
        usage: turn.usage,
      });
    } catch (err) {
      // History is not saved on failure, so the client can simply retry.
      console.error("[chat] turn failed:", err);
      return c.json({ sessionId, error: "The coach failed to answer. Check server logs / Phoenix trace." }, 502);
    }
  });

  app.delete("/sessions/:id", async (c) => {
    await deps.sessions.delete(c.req.param("id"));
    return c.body(null, 204);
  });

  return app;
}
