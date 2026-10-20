import type { IsoDate, Performance } from "./model.js";
import { daysBetween, formatDuration, formatPace, paceSecPerKm } from "./time.js";
import type { TrainingContext } from "./training.js";
import { predictTimeFromVdot, riegel, vdotFromPerformance } from "./vdot.js";

export type Feasibility = "likely" | "borderline" | "stretch" | "unlikely";

export interface RacePrediction {
  targetDistanceKm: number;
  reference: { label: string; time: string; date: IsoDate; vdot: number; ageDays: number };
  predicted: {
    centre: string;
    fastEnd: string;
    slowEnd: string;
    centreSec: number;
    pace: string;
  };
  riegel: string;
  adjustments: string[];
  target?: {
    time: string;
    requiredPace: string;
    gapPct: number;
    feasibility: Feasibility;
  };
  weeksUntilRace?: number;
  assumptions: string[];
}

export interface PredictRaceInput {
  performances: Performance[];
  targetDistanceM: number;
  context: TrainingContext;
  today: IsoDate;
  targetTimeSec?: number;
  raceDate?: IsoDate;
  /** only performances newer than this count as "current fitness" */
  maxReferenceAgeDays?: number;
}

/**
 * Deterministic race prediction. The LLM never does this arithmetic — it calls
 * this through a tool and *explains* the result. That split is the single most
 * important design choice for groundedness.
 */
export function predictRace(input: PredictRaceInput): RacePrediction | { error: string } {
  const maxAge = input.maxReferenceAgeDays ?? 120;
  const recent = input.performances
    .map((p) => ({ p, ageDays: daysBetween(p.date, input.today), vdot: vdotFromPerformance(p.distanceM, p.timeSec) }))
    .filter((x) => x.ageDays >= 0 && x.ageDays <= maxAge)
    .sort((a, b) => b.vdot - a.vdot)
    .slice(0, 3);

  if (recent.length === 0) {
    return { error: `No race-like performance in the last ${maxAge} days to base a prediction on.` };
  }

  // Of the top-3 VDOT efforts, prefer the one whose distance is closest
  // (log-scale) to the target: the most specific evidence wins.
  const logGap = (d: number) => Math.abs(Math.log(input.targetDistanceM / d));
  const ref = [...recent].sort((a, b) => logGap(a.p.distanceM) - logGap(b.p.distanceM))[0]!;

  let centre = predictTimeFromVdot(ref.vdot, input.targetDistanceM);
  const adjustments: string[] = [];

  // Durability heuristics — VDOT assumes you are trained for the distance.
  const isLong = input.targetDistanceM >= 21000;
  if (isLong) {
    const marathon = input.targetDistanceM >= 40000;
    const vol = input.context.avgWeeklyKm;
    const volPenalty = marathon
      ? vol < 50 ? 0.04 : vol < 70 ? 0.02 : vol < 90 ? 0.005 : 0
      : vol < 35 ? 0.02 : vol < 50 ? 0.01 : 0;
    if (volPenalty > 0) {
      centre *= 1 + volPenalty;
      adjustments.push(`+${(volPenalty * 100).toFixed(1)}% for ${vol} km/week average volume`);
    }
    const longNeeded = marathon ? 30 : 18;
    if (input.context.longestRunKm < longNeeded) {
      centre *= 1.015;
      adjustments.push(`+1.5% because longest recent run is ${input.context.longestRunKm} km (< ${longNeeded} km)`);
    }
  }

  const fastEnd = centre * 0.985;
  const slowEnd = centre * 1.025; // asymmetric: more ways to go slower than faster

  const prediction: RacePrediction = {
    targetDistanceKm: input.targetDistanceM / 1000,
    reference: {
      label: ref.p.label,
      time: formatDuration(ref.p.timeSec),
      date: ref.p.date,
      vdot: Math.round(ref.vdot * 10) / 10,
      ageDays: ref.ageDays,
    },
    predicted: {
      centre: formatDuration(centre),
      fastEnd: formatDuration(fastEnd),
      slowEnd: formatDuration(slowEnd),
      centreSec: Math.round(centre),
      pace: formatPace(paceSecPerKm(input.targetDistanceM, centre)),
    },
    riegel: formatDuration(riegel(ref.p.timeSec, ref.p.distanceM, input.targetDistanceM)),
    adjustments,
    assumptions: [
      "Prediction reflects CURRENT fitness, not fitness after a future training block.",
      "Assumes a flat course, good weather and an even pacing strategy.",
      "Volume/long-run adjustments are coaching heuristics, not validated science.",
    ],
  };

  if (input.targetTimeSec !== undefined) {
    const gapPct = ((input.targetTimeSec - centre) / centre) * 100;
    prediction.target = {
      time: formatDuration(input.targetTimeSec),
      requiredPace: formatPace(paceSecPerKm(input.targetDistanceM, input.targetTimeSec)),
      gapPct: Math.round(gapPct * 10) / 10,
      feasibility: gapPct >= 1 ? "likely" : gapPct >= -1 ? "borderline" : gapPct >= -3 ? "stretch" : "unlikely",
    };
  }
  if (input.raceDate) {
    prediction.weeksUntilRace = Math.round((daysBetween(input.today, input.raceDate) / 7) * 10) / 10;
  }
  return prediction;
}
