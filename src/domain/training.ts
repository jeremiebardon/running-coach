import { isRun, type Activity, type IsoDate, type Performance, type WellnessDay } from "./model.js";
import { RACE_DISTANCES, addDays, formatDuration, weekStart } from "./time.js";

export interface WeekVolume {
  weekStart: IsoDate;
  km: number;
  runs: number;
  longestRunKm: number;
  movingHours: number;
}

/** Weekly running volume for the `weeks` weeks ending with the week of `today`. */
export function weeklyVolume(activities: Activity[], today: IsoDate, weeks: number): WeekVolume[] {
  const firstWeek = addDays(weekStart(today), -7 * (weeks - 1));
  const buckets = new Map<IsoDate, WeekVolume>();
  for (let i = 0; i < weeks; i++) {
    const ws = addDays(firstWeek, 7 * i);
    buckets.set(ws, { weekStart: ws, km: 0, runs: 0, longestRunKm: 0, movingHours: 0 });
  }
  for (const a of activities.filter(isRun)) {
    const bucket = buckets.get(weekStart(a.startDateLocal.slice(0, 10)));
    if (!bucket) continue;
    const km = a.distanceM / 1000;
    bucket.km += km;
    bucket.runs += 1;
    bucket.longestRunKm = Math.max(bucket.longestRunKm, km);
    bucket.movingHours += a.movingTimeSec / 3600;
  }
  return [...buckets.values()].map((w) => ({
    ...w,
    km: round1(w.km),
    longestRunKm: round1(w.longestRunKm),
    movingHours: round1(w.movingHours),
  }));
}

export interface TrainingContext {
  /** average over COMPLETED weeks (the current partial week is excluded) */
  avgWeeklyKm: number;
  longestRunKm: number;
  weeksConsidered: number;
}

export function trainingContext(activities: Activity[], today: IsoDate, weeks = 8): TrainingContext {
  const all = weeklyVolume(activities, today, weeks + 1);
  const completed = all.slice(0, -1);
  const avg = completed.reduce((s, w) => s + w.km, 0) / Math.max(completed.length, 1);
  return {
    avgWeeklyKm: round1(avg),
    longestRunKm: Math.max(0, ...all.map((w) => w.longestRunKm)),
    weeksConsidered: completed.length,
  };
}

/* ---------------------------- fitness / form ---------------------------- */

export type FormZone = "transition" | "fresh" | "grey-zone" | "optimal-training" | "high-risk";

export interface FitnessSnapshot {
  date: IsoDate;
  ctl: number;
  atl: number;
  tsb: number;
  /** TSB as a % of CTL — the scale intervals.icu uses for its form zones */
  formPct: number;
  zone: FormZone;
  rampRate?: number;
}

/** Approximation of intervals.icu's form zones, expressed as TSB/CTL %. */
export function formZone(formPct: number): FormZone {
  if (formPct > 20) return "transition";
  if (formPct > 5) return "fresh";
  if (formPct > -10) return "grey-zone";
  if (formPct > -30) return "optimal-training";
  return "high-risk";
}

export function fitnessSnapshot(day: WellnessDay): FitnessSnapshot | null {
  if (day.ctl === undefined || day.atl === undefined) return null;
  const tsb = day.ctl - day.atl;
  const formPct = day.ctl > 0 ? (tsb / day.ctl) * 100 : 0;
  return {
    date: day.date,
    ctl: round1(day.ctl),
    atl: round1(day.atl),
    tsb: round1(tsb),
    formPct: Math.round(formPct),
    zone: formZone(formPct),
    rampRate: day.rampRate === undefined ? undefined : round1(day.rampRate),
  };
}

/* ----------------------------- best efforts ----------------------------- */

/**
 * Whole-activity best efforts at standard distances (±3%).
 *
 * POC simplification: intervals.icu exposes full pace curves (best 5k/10k
 * *inside* any run), which would be strictly better — swap this for the
 * pace-curve endpoint once you've confirmed its shape in the Swagger docs.
 */
export function bestEfforts(activities: Activity[]): Performance[] {
  const out: Performance[] = [];
  for (const [label, distanceM] of Object.entries(RACE_DISTANCES)) {
    const candidates = activities
      .filter(isRun)
      .filter((a) => Math.abs(a.distanceM - distanceM) / distanceM <= 0.03)
      // normalise to the exact distance at the run's average pace
      .map((a) => ({ a, normalisedSec: a.movingTimeSec * (distanceM / a.distanceM) }))
      .sort((x, y) => x.normalisedSec - y.normalisedSec);
    const best = candidates[0];
    if (best) {
      out.push({
        label,
        distanceM,
        timeSec: Math.round(best.normalisedSec),
        date: best.a.startDateLocal.slice(0, 10),
        activityId: best.a.id,
      });
    }
  }
  return out;
}

export const describePerformance = (p: Performance): string =>
  `${p.label} in ${formatDuration(p.timeSec)} on ${p.date}`;

export const round1 = (n: number): number => Math.round(n * 10) / 10;
