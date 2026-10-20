/**
 * Domain model — the coach's own vocabulary.
 *
 * Nothing here knows about intervals.icu, HTTP or LLMs. Adapters translate
 * external payloads INTO these types (anti-corruption layer), so if you later
 * add Garmin or Strava as a source, the domain and the agent tools don't move.
 */

export type IsoDate = string; // YYYY-MM-DD (athlete local date)

export interface DateRange {
  oldest: IsoDate;
  newest: IsoDate;
}

export interface AthleteProfile {
  id: string;
  name?: string;
  /** Running threshold pace in seconds per km, if configured in the source. */
  thresholdPaceSecPerKm?: number;
  lthr?: number;
  maxHr?: number;
}

export interface Interval {
  label?: string;
  /** e.g. WORK / RECOVERY as reported by the source */
  kind?: string;
  distanceM: number;
  movingTimeSec: number;
  avgHr?: number;
}

export interface Activity {
  id: string;
  name: string;
  /** Normalised sport type: "Run", "TrailRun", "VirtualRun", "Ride", ... */
  type: string;
  /** Local start timestamp, ISO 8601 without zone */
  startDateLocal: string;
  distanceM: number;
  movingTimeSec: number;
  avgHr?: number;
  maxHr?: number;
  elevationGainM?: number;
  /** Source training load (intervals.icu: icu_training_load) */
  trainingLoad?: number;
  /** True when the source flags the activity as a race */
  isRace?: boolean;
  intervals?: Interval[];
}

export interface WellnessDay {
  date: IsoDate;
  /** Chronic training load ("fitness") */
  ctl?: number;
  /** Acute training load ("fatigue") */
  atl?: number;
  rampRate?: number;
  restingHr?: number;
  hrv?: number;
  sleepHours?: number;
}

export interface Performance {
  distanceM: number;
  timeSec: number;
  date: IsoDate;
  activityId: string;
  label: string;
}

export const RUN_TYPES = new Set(["Run", "TrailRun", "VirtualRun"]);
export const isRun = (a: Activity): boolean => RUN_TYPES.has(a.type);
