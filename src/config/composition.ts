import { ollama } from 'ollama-ai-provider-v2';
import type { LanguageModel } from "ai";
import { fileURLToPath } from "node:url";
import { FixtureTrainingDataAdapter } from "../adapters/fixtures/fixture.adapter.js";
import { IntervalsIcuAdapter } from "../adapters/intervals-icu/intervals-icu.adapter.js";
import { systemClock, type ClockPort, type TrainingDataPort } from "../ports/training-data.port.js";

/**
 * Composition root — the ONE place that reads env vars and picks adapters.
 * Swapping the model provider (OpenAI, Bedrock, a local model) is a one-line
 * change here thanks to the AI SDK's provider abstraction.
 */
export const DEFAULT_FIXTURE = fileURLToPath(new URL("../../fixtures/athlete-sub3.json", import.meta.url));

export const coachModel = (): LanguageModel => ollama(process.env.COACH_MODEL ?? "claude-sonnet-5-5");
export const judgeModel = (): LanguageModel => ollama(process.env.JUDGE_MODEL ?? "claude-haiku-5-5");

export function buildDataSource(clock: ClockPort): TrainingDataPort {
  if (process.env.DATA_SOURCE === "fixtures") {
    return new FixtureTrainingDataAdapter(process.env.FIXTURE_PATH ?? DEFAULT_FIXTURE, clock);
  }
  const apiKey = process.env.INTERVALS_API_KEY;
  if (!apiKey) throw new Error("INTERVALS_API_KEY is missing (or set DATA_SOURCE=fixtures).");
  return new IntervalsIcuAdapter({ apiKey, athleteId: process.env.INTERVALS_ATHLETE_ID ?? "0" });
}

export const athleteClock = (): ClockPort => systemClock(process.env.ATHLETE_TIMEZONE ?? "America/Toronto");
