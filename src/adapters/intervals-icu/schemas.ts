import { z } from "zod";
import type { Activity, AthleteProfile, WellnessDay } from "../../domain/model.js";

/**
 * Lenient schemas for the intervals.icu payloads we use.
 * `.loose()` keeps unknown fields (the API returns ~100 per activity) and every
 * field is optional except ids, so an upstream addition never breaks parsing.
 * Field names verified against the official API docs / Swagger:
 *   https://intervals.icu/api/v1/docs/swagger-ui/index.html
 */

const num = z.number().nullish();

export const rawIntervalSchema = z
  .object({
    label: z.string().nullish(),
    type: z.string().nullish(),
    distance: num,
    moving_time: num,
    average_heartrate: num,
  })
  .loose();

export const rawActivitySchema = z
  .object({
    id: z.union([z.string(), z.number()]).transform(String),
    name: z.string().nullish(),
    type: z.string().nullish(),
    start_date_local: z.string(),
    distance: num,
    moving_time: num,
    average_heartrate: num,
    max_heartrate: num,
    total_elevation_gain: num,
    icu_training_load: num,
    race: z.boolean().nullish(),
    icu_intervals: z.array(rawIntervalSchema).nullish(),
  })
  .loose();

export const rawWellnessSchema = z
  .object({
    id: z.string(), // the date, YYYY-MM-DD
    ctl: num,
    atl: num,
    rampRate: num,
    restingHR: num,
    hrv: num,
    sleepSecs: num,
  })
  .loose();

export const rawAthleteSchema = z
  .object({
    id: z.union([z.string(), z.number()]).transform(String),
    name: z.string().nullish(),
    sportSettings: z
      .array(
        z
          .object({
            types: z.array(z.string()).nullish(),
            threshold_pace: num, // metres / second
            lthr: num,
            max_hr: num,
          })
          .loose(),
      )
      .nullish(),
  })
  .loose();

export type RawActivity = z.infer<typeof rawActivitySchema>;
export type RawWellness = z.infer<typeof rawWellnessSchema>;
export type RawAthlete = z.infer<typeof rawAthleteSchema>;

/* ------------------- anti-corruption layer: raw -> domain ------------------- */

const opt = (n: number | null | undefined): number | undefined => (n == null ? undefined : n);

export function toActivity(raw: RawActivity): Activity {
  return {
    id: raw.id,
    name: raw.name ?? "Untitled",
    type: raw.type ?? "Unknown",
    startDateLocal: raw.start_date_local,
    distanceM: raw.distance ?? 0,
    movingTimeSec: raw.moving_time ?? 0,
    avgHr: opt(raw.average_heartrate),
    maxHr: opt(raw.max_heartrate),
    elevationGainM: opt(raw.total_elevation_gain),
    trainingLoad: opt(raw.icu_training_load),
    isRace: raw.race ?? undefined,
    intervals: raw.icu_intervals?.map((i) => ({
      label: i.label ?? undefined,
      kind: i.type ?? undefined,
      distanceM: i.distance ?? 0,
      movingTimeSec: i.moving_time ?? 0,
      avgHr: opt(i.average_heartrate),
    })),
  };
}

export function toWellness(raw: RawWellness): WellnessDay {
  return {
    date: raw.id,
    ctl: opt(raw.ctl),
    atl: opt(raw.atl),
    rampRate: opt(raw.rampRate),
    restingHr: opt(raw.restingHR),
    hrv: opt(raw.hrv),
    sleepHours: raw.sleepSecs == null ? undefined : Math.round((raw.sleepSecs / 3600) * 10) / 10,
  };
}

export function toAthleteProfile(raw: RawAthlete): AthleteProfile {
  const run = raw.sportSettings?.find((s) => s.types?.includes("Run"));
  const pace = run?.threshold_pace;
  return {
    id: raw.id,
    name: raw.name ?? undefined,
    thresholdPaceSecPerKm: pace ? Math.round(1000 / pace) : undefined,
    lthr: opt(run?.lthr),
    maxHr: opt(run?.max_hr),
  };
}
