import { formatDuration, formatPace } from "./time.js";

export type PacingStrategy = "even" | "negative";

export interface PacingSplit {
  atKm: number;
  splitTime: string;
  cumulative: string;
  pace: string;
}

export interface PacingPlan {
  strategy: PacingStrategy;
  target: string;
  averagePace: string;
  firstHalfPace: string;
  secondHalfPace: string;
  splits: PacingSplit[];
}

/**
 * Even or negative-split plan. For "negative", the first half is run
 * `swingPct`/2 slower and the second half `swingPct`/2 faster than average,
 * so the total still equals the target exactly.
 */
export function buildPacingPlan(params: {
  distanceM: number;
  targetSec: number;
  strategy: PacingStrategy;
  splitEveryKm?: number;
  swingPct?: number;
}): PacingPlan {
  const { distanceM, targetSec, strategy } = params;
  const every = params.splitEveryKm ?? 5;
  const swing = strategy === "negative" ? (params.swingPct ?? 2) / 100 : 0;
  const totalKm = distanceM / 1000;
  const half = totalKm / 2;
  const avg = targetSec / totalKm;
  const p1 = avg * (1 + swing / 2);
  const p2 = avg * (1 - swing / 2);

  const timeAt = (km: number) => (km <= half ? km * p1 : half * p1 + (km - half) * p2);

  const marks: number[] = [];
  for (let km = every; km < totalKm - 1e-9; km += every) marks.push(km);
  marks.push(totalKm);

  const splits: PacingSplit[] = [];
  let prevKm = 0;
  for (const km of marks) {
    const split = timeAt(km) - timeAt(prevKm);
    splits.push({
      atKm: Math.round(km * 1000) / 1000,
      splitTime: formatDuration(split),
      cumulative: formatDuration(timeAt(km)),
      pace: formatPace(split / (km - prevKm)),
    });
    prevKm = km;
  }

  return {
    strategy,
    target: formatDuration(targetSec),
    averagePace: formatPace(avg),
    firstHalfPace: formatPace(p1),
    secondHalfPace: formatPace(p2),
    splits,
  };
}
