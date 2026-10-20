import type { Activity } from "./model.js";
import { formatDuration, formatPace, paceSecPerKm } from "./time.js";

export interface ActivitySummary {
  id: string;
  name: string;
  type: string;
  date: string;
  distanceKm: number;
  movingTime: string;
  avgPace: string;
  avgHr?: number;
  maxHr?: number;
  elevationGainM?: number;
  trainingLoad?: number;
  isRace?: boolean;
  workIntervals?: { count: number; avgPace: string; avgHr?: number; paces: string[] };
}

/** Token-cheap view of an activity — the agent never sees raw API payloads. */
export function summariseActivity(a: Activity): ActivitySummary {
  const summary: ActivitySummary = {
    id: a.id,
    name: a.name,
    type: a.type,
    date: a.startDateLocal.slice(0, 10),
    distanceKm: Math.round(a.distanceM / 10) / 100,
    movingTime: formatDuration(a.movingTimeSec),
    avgPace: a.distanceM > 0 ? formatPace(paceSecPerKm(a.distanceM, a.movingTimeSec)) : "n/a",
    avgHr: a.avgHr,
    maxHr: a.maxHr,
    elevationGainM: a.elevationGainM,
    trainingLoad: a.trainingLoad,
    isRace: a.isRace,
  };

  const work = (a.intervals ?? []).filter((i) => (i.kind ?? "").toUpperCase() === "WORK" && i.distanceM > 0);
  if (work.length > 0) {
    const dist = work.reduce((s, i) => s + i.distanceM, 0);
    const time = work.reduce((s, i) => s + i.movingTimeSec, 0);
    const hrs = work.map((i) => i.avgHr).filter((h): h is number => h !== undefined);
    summary.workIntervals = {
      count: work.length,
      avgPace: formatPace(paceSecPerKm(dist, time)),
      avgHr: hrs.length ? Math.round(hrs.reduce((s, h) => s + h, 0) / hrs.length) : undefined,
      paces: work.map((i) => formatPace(paceSecPerKm(i.distanceM, i.movingTimeSec))),
    };
  }
  return summary;
}
