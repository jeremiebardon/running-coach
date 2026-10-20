import { OpenTelemetry } from "@ai-sdk/otel";
import { register, type NodeTracerProvider } from "@arizeai/phoenix-otel";
import { registerTelemetry } from "ai";

let provider: NodeTracerProvider | undefined;

/**
 * Wire AI SDK telemetry → OpenTelemetry → Phoenix.
 *
 * - `registerTelemetry(new OpenTelemetry())` makes every AI SDK call (agent,
 *   LLM step, tool execution) emit spans.
 * - `register()` from @arizeai/phoenix-otel installs a tracer provider whose
 *   OpenInference span processor converts those spans to the format Phoenix
 *   understands, then exports via OTLP.
 *
 * `withPhoenixProvider: false` is used by evals: runExperiment() mounts its own
 * provider so task traces land in the experiment's project.
 */
export function initTelemetry(opts: { projectName: string; withPhoenixProvider: boolean }): void {
  registerTelemetry(new OpenTelemetry({ headers: false })); // never put API keys on spans
  if (!opts.withPhoenixProvider) return;
  if (!process.env.PHOENIX_COLLECTOR_ENDPOINT) {
    console.warn("[telemetry] PHOENIX_COLLECTOR_ENDPOINT not set — traces disabled.");
    return;
  }
  provider = register({ projectName: opts.projectName, batch: true });
}

export async function shutdownTelemetry(): Promise<void> {
  await provider?.shutdown(); // flush batched spans before exit
}
