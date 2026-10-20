import { ToolLoopAgent, stepCountIs, type LanguageModel, type ModelMessage } from "ai";
import {
  OpenInferenceSpanKind,
  SemanticConventions,
  SpanStatusCode,
  context,
  setSession,
  trace,
} from "@arizeai/phoenix-otel";
import type { ClockPort, TrainingDataPort } from "../ports/training-data.port.js";
import { COACH_PROMPT_VERSION, coachInstructions } from "./instructions.js";
import { createCoachTools } from "./tools.js";

export interface CoachDeps {
  model: LanguageModel;
  data: TrainingDataPort;
  clock: ClockPort;
  maxSteps?: number;
}

/**
 * Composition root for the agent: a single ToolLoopAgent (model ↔ tools loop
 * until the model answers or `maxSteps` is hit). Everything external is
 * injected, which is what lets tests use a mock model and evals use fixtures.
 */
export function createCoachAgent(deps: CoachDeps) {
  return new ToolLoopAgent({
    id: "running-coach",
    model: deps.model,
    instructions: coachInstructions(deps.clock.today()),
    tools: createCoachTools({ data: deps.data, clock: deps.clock }),
    stopWhen: stepCountIs(deps.maxSteps ?? 8),
    telemetry: { functionId: "running-coach" },
  });
}

export type CoachAgent = ReturnType<typeof createCoachAgent>;

export interface ToolCallRecord {
  name: string;
  input: unknown;
  output: unknown;
}

export interface TurnResult {
  answer: string;
  toolCalls: ToolCallRecord[];
  steps: number;
  usage: { inputTokens?: number; outputTokens?: number };
}

/**
 * One conversational turn, wrapped in a root AGENT span carrying the session id.
 * Phoenix groups traces by `session.id` → you get a "Sessions" view of whole
 * conversations, and every AI SDK span (LLM steps, tool calls) nests under it.
 */
export async function runTurn(
  agent: CoachAgent,
  messages: ModelMessage[],
  opts: { sessionId: string; metadata?: Record<string, unknown> },
): Promise<TurnResult> {
  const tracer = trace.getTracer("running-coach");
  const lastUser = [...messages].reverse().find((m) => m.role === "user");
  const ctx = setSession(context.active(), { sessionId: opts.sessionId });

  return context.with(ctx, () =>
    tracer.startActiveSpan("coach.turn", async (span) => {
      span.setAttributes({
        [SemanticConventions.OPENINFERENCE_SPAN_KIND]: OpenInferenceSpanKind.AGENT,
        [SemanticConventions.SESSION_ID]: opts.sessionId,
        [SemanticConventions.INPUT_VALUE]: typeof lastUser?.content === "string" ? lastUser.content : JSON.stringify(lastUser?.content ?? ""),
        [SemanticConventions.METADATA]: JSON.stringify({ promptVersion: COACH_PROMPT_VERSION, ...opts.metadata }),
      });
      try {
        const result = await agent.generate({ messages });
        const toolCalls: ToolCallRecord[] = result.steps.flatMap((step) =>
          step.toolCalls.map((call) => ({
            name: call.toolName,
            input: call.input,
            output: step.toolResults.find((r) => r.toolCallId === call.toolCallId)?.output,
          })),
        );
        span.setAttribute(SemanticConventions.OUTPUT_VALUE, result.text);
        span.setStatus({ code: SpanStatusCode.OK });
        return {
          answer: result.text,
          toolCalls,
          steps: result.steps.length,
          usage: { inputTokens: result.totalUsage.inputTokens, outputTokens: result.totalUsage.outputTokens },
        };
      } catch (err) {
        span.recordException(err as Error);
        span.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
        throw err;
      } finally {
        span.end();
      }
    }),
  );
}
