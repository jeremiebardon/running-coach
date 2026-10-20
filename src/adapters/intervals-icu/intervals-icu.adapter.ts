import { z } from "zod";
import type { Activity, AthleteProfile, DateRange, WellnessDay } from "../../domain/model.js";
import type { TrainingDataPort } from "../../ports/training-data.port.js";
import {
  rawActivitySchema,
  rawAthleteSchema,
  rawWellnessSchema,
  toActivity,
  toAthleteProfile,
  toWellness,
} from "./schemas.js";

export interface IntervalsIcuConfig {
  apiKey: string;
  /** "0" = the owner of the API key */
  athleteId?: string;
  baseUrl?: string;
  timeoutMs?: number;
  maxRetries?: number;
  fetchImpl?: typeof fetch;
}

/**
 * Driven adapter for https://intervals.icu/api/v1
 * Auth: HTTP Basic, username "API_KEY", password = your key (Settings → Developer).
 *
 * Gotcha: activities imported from Strava are NOT returned by the API (Strava's
 * terms). Sync Garmin → intervals.icu directly.
 */
export class IntervalsIcuAdapter implements TrainingDataPort {
  private readonly baseUrl: string;
  private readonly athleteId: string;
  private readonly authHeader: string;
  private readonly fetchImpl: typeof fetch;

  constructor(private readonly config: IntervalsIcuConfig) {
    this.baseUrl = config.baseUrl ?? "https://intervals.icu/api/v1";
    this.athleteId = config.athleteId ?? "0";
    this.authHeader = `Basic ${Buffer.from(`API_KEY:${config.apiKey}`).toString("base64")}`;
    this.fetchImpl = config.fetchImpl ?? fetch;
  }

  async getAthleteProfile(): Promise<AthleteProfile> {
    const raw = await this.get(`/athlete/${this.athleteId}`, rawAthleteSchema);
    return toAthleteProfile(raw);
  }

  async listActivities(range: DateRange): Promise<Activity[]> {
    const raws = await this.get(
      `/athlete/${this.athleteId}/activities?oldest=${range.oldest}&newest=${range.newest}`,
      z.array(rawActivitySchema),
    );
    return raws.map(toActivity);
  }

  async getActivity(id: string): Promise<Activity | null> {
    try {
      const raw = await this.get(`/activity/${encodeURIComponent(id)}?intervals=true`, rawActivitySchema);
      return toActivity(raw);
    } catch (e) {
      if (e instanceof IntervalsIcuError && e.status === 404) return null;
      throw e;
    }
  }

  async listWellness(range: DateRange): Promise<WellnessDay[]> {
    const raws = await this.get(
      `/athlete/${this.athleteId}/wellness?oldest=${range.oldest}&newest=${range.newest}`,
      z.array(rawWellnessSchema),
    );
    return raws.map(toWellness);
  }

  /** GET + timeout + retry with exponential backoff on 429/5xx + schema validation */
  private async get<T extends z.ZodType>(path: string, schema: T): Promise<z.output<T>> {
    const maxRetries = this.config.maxRetries ?? 2;
    for (let attempt = 0; ; attempt++) {
      const res = await this.fetchImpl(`${this.baseUrl}${path}`, {
        headers: { Authorization: this.authHeader, Accept: "application/json" },
        signal: AbortSignal.timeout(this.config.timeoutMs ?? 15_000),
      });
      if (res.ok) return schema.parse(await res.json());
      const retryable = res.status === 429 || res.status >= 500;
      if (!retryable || attempt >= maxRetries) {
        throw new IntervalsIcuError(res.status, `intervals.icu ${res.status} on GET ${path}`);
      }
      await new Promise((r) => setTimeout(r, 500 * 2 ** attempt));
    }
  }
}

export class IntervalsIcuError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "IntervalsIcuError";
  }
}
