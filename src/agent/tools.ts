import { tool } from "ai";
import { z } from "zod";
import { summariseActivity } from "../domain/activity-summary.js";
import { isRun } from "../domain/model.js";
import { buildPacingPlan } from "../domain/pacing.js";
import { predictRace } from "../domain/predictor.js";
import { addDays, formatPace, parseDuration, resolveDistanceM } from "../domain/time.js";
import { bestEfforts, describePerformance, fitnessSnapshot, trainingContext, weeklyVolume } from "../domain/training.js";
import type { ClockPort, TrainingDataPort } from "../ports/training-data.port.js";

/**
 * Agent tools = the application layer's use cases, exposed to the LLM.
 *
 * Design rules (they matter more than the prompt):
 *  - Each tool does ONE job a coach would recognise, with a description that
 *    says WHEN to use it — that's what drives tool selection.
 *  - Tools return small, pre-digested JSON (formatted times, paces) instead of
 *    raw API payloads: fewer tokens, less room for the model to mis-read data.
 *  - All arithmetic lives in the domain; the model only explains.
 *  - Errors are returned as { error } values, not thrown, so the model can
 *    recover ("I couldn't find a run today") instead of the loop crashing.
 */

const distanceSchema = z
  .union([z.enum(["5k", "10k", "half", "marathon"]), z.number().positive().describe("distance in km")])
  .describe('Race distance: "5k" | "10k" | "half" | "marathon" or a number of km');

const durationSchema = z
  .string()
  .regex(/^\d{1,2}(:\d{2}){1,2}$/)
  .describe('Duration as "h:mm:ss" or "mm:ss", e.g. "2:55:00"');

const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

export function createCoachTools(deps: { data: TrainingDataPort; clock: ClockPort }) {
  const { data, clock } = deps;
  const rangeBack = (days: number) => ({ oldest: addDays(clock.today(), -days), newest: clock.today() });

  return {
    get_athlete_snapshot: tool({
      description:
        "Overview of the athlete right now: profile/thresholds, current fitness (CTL), fatigue (ATL), form (TSB) and the last 4 weeks of running volume. Call this first for broad questions like 'how is my training going?'.",
      inputSchema: z.object({}),
      execute: async () => {
        const [profile, wellness, activities] = await Promise.all([
          data.getAthleteProfile(),
          data.listWellness(rangeBack(7)),
          data.listActivities(rangeBack(35)),
        ]);
        const latest = [...wellness].reverse().find((w) => w.ctl !== undefined);
        return {
          today: clock.today(),
          profile: {
            ...profile,
            thresholdPace: profile.thresholdPaceSecPerKm ? formatPace(profile.thresholdPaceSecPerKm) : undefined,
          },
          fitness: latest ? fitnessSnapshot(latest) : null,
          last4Weeks: weeklyVolume(activities, clock.today(), 4),
        };
      },
    }),

    list_recent_activities: tool({
      description:
        "List recent activities (newest first) with distance, time, pace, HR and load. Use to find a specific run (e.g. 'today', 'last Sunday's long run') before fetching details.",
      inputSchema: z.object({
        days: z.number().int().min(1).max(90).default(14).describe("How many days back to look"),
        runsOnly: z.boolean().default(true),
      }),
      execute: async ({ days, runsOnly }) => {
        const list = await data.listActivities(rangeBack(days));
        return list
          .filter((a) => !runsOnly || isRun(a))
          .sort((a, b) => b.startDateLocal.localeCompare(a.startDateLocal))
          .map((a) => {
            const { workIntervals: _omit, ...rest } = summariseActivity(a);
            return rest;
          });
      },
    }),

    get_activity_details: tool({
      description:
        "Detailed analysis of ONE activity, including work intervals (paces and HR per rep). Pass either an activityId or a date (YYYY-MM-DD); with a date, the most recent run that day is used. Use for 'how was my run today?' or reviewing a workout.",
      inputSchema: z.object({
        activityId: z.string().optional(),
        date: isoDate.optional().describe("Local date of the run, e.g. today's date"),
      }),
      execute: async ({ activityId, date }) => {
        let id = activityId;
        if (!id) {
          const day = date ?? clock.today();
          const runs = (await data.listActivities({ oldest: day, newest: day })).filter(isRun);
          id = runs.sort((a, b) => b.startDateLocal.localeCompare(a.startDateLocal))[0]?.id;
          if (!id) return { error: `No run found on ${day}.` };
        }
        const activity = await data.getActivity(id);
        if (!activity) return { error: `Activity ${id} not found.` };
        const day = activity.startDateLocal.slice(0, 10);
        const wellness = await data.listWellness({ oldest: addDays(day, -1), newest: day });
        const morning = wellness.find((w) => w.date === day);
        return {
          activity: summariseActivity(activity),
          contextThatDay: morning
            ? { restingHr: morning.restingHr, hrv: morning.hrv, sleepHours: morning.sleepHours }
            : null,
        };
      },
    }),

    get_fitness_trend: tool({
      description:
        "Daily fitness (CTL), fatigue (ATL), form (TSB, % and zone), ramp rate, resting HR, HRV and sleep over a period. Use for freshness/recovery/readiness questions ('am I ready for a hard session?', 'am I overtraining?').",
      inputSchema: z.object({ days: z.number().int().min(3).max(120).default(28) }),
      execute: async ({ days }) => {
        const wellness = await data.listWellness(rangeBack(days));
        const series = wellness.map((w) => ({ ...fitnessSnapshot(w), restingHr: w.restingHr, hrv: w.hrv, sleepHours: w.sleepHours }));
        // Down-sample long windows to keep the payload small: daily for the last week, weekly before.
        const recent = series.slice(-7);
        const older = series.slice(0, -7).filter((_, i, arr) => (arr.length - 1 - i) % 7 === 0);
        return { olderWeekly: older, lastSevenDays: recent };
      },
    }),

    get_training_volume: tool({
      description: "Weekly running volume (km, number of runs, longest run, hours) for the last N weeks, current week last.",
      inputSchema: z.object({ weeks: z.number().int().min(1).max(26).default(8) }),
      execute: async ({ weeks }) => {
        const activities = await data.listActivities(rangeBack(weeks * 7 + 7));
        return {
          weeks: weeklyVolume(activities, clock.today(), weeks),
          note: "The last entry is the current, possibly incomplete, week.",
        };
      },
    }),

    get_best_efforts: tool({
      description: "Best recent whole-activity performances at 5k / 10k / half / marathon distances (races or race-like efforts).",
      inputSchema: z.object({ days: z.number().int().min(14).max(365).default(180) }),
      execute: async ({ days }) => {
        const efforts = bestEfforts(await data.listActivities(rangeBack(days)));
        return efforts.length
          ? efforts.map((p) => ({ ...p, summary: describePerformance(p) }))
          : { error: `No efforts at standard distances in the last ${days} days.` };
      },
    }),

    predict_race_time: tool({
      description:
        "Predict a race time from recent performances (VDOT, adjusted for training volume and long runs) and, if a target is given, rate its feasibility. ALWAYS use this for 'could I run X in Y?', 'what's my marathon potential?' questions — never estimate times yourself.",
      inputSchema: z.object({
        distance: distanceSchema,
        targetTime: durationSchema.optional(),
        raceDate: isoDate.optional(),
      }),
      execute: async ({ distance, targetTime, raceDate }) => {
        const activities = await data.listActivities(rangeBack(180));
        return predictRace({
          performances: bestEfforts(activities),
          targetDistanceM: resolveDistanceM(distance),
          context: trainingContext(activities, clock.today()),
          today: clock.today(),
          targetTimeSec: targetTime ? parseDuration(targetTime) : undefined,
          raceDate,
        });
      },
    }),

    build_pacing_plan: tool({
      description: "Build a race pacing plan (splits every N km) for a target time. Use when the athlete asks how to pace a race.",
      inputSchema: z.object({
        distance: distanceSchema,
        targetTime: durationSchema,
        strategy: z.enum(["even", "negative"]).default("even"),
        splitEveryKm: z.number().min(1).max(10).default(5),
      }),
      execute: async ({ distance, targetTime, strategy, splitEveryKm }) =>
        buildPacingPlan({ distanceM: resolveDistanceM(distance), targetSec: parseDuration(targetTime), strategy, splitEveryKm }),
    }),
  };
}

export type CoachTools = ReturnType<typeof createCoachTools>;
