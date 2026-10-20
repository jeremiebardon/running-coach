import { readFileSync } from "node:fs";
import { z } from "zod";
import type { Activity, AthleteProfile, DateRange, WellnessDay } from "../../domain/model.js";
import { addDays } from "../../domain/time.js";
import type { ClockPort, TrainingDataPort } from "../../ports/training-data.port.js";
import {
  rawActivitySchema,
  rawAthleteSchema,
  rawWellnessSchema,
  toActivity,
  toAthleteProfile,
  toWellness,
} from "../intervals-icu/schemas.js";

/**
 * Fixtures are stored in the RAW intervals.icu shape, with dates expressed as
 * offsets from "today" (`_dayOffset`). Two benefits:
 *  1. they go through the exact same mapper as live data (the ACL is tested too);
 *  2. they never go stale — "how was my run today?" always has a run today.
 */
const fixtureFileSchema = z.object({
  athlete: z.unknown(),
  activities: z.array(z.object({ _dayOffset: z.number().int(), _time: z.string() }).loose()),
  wellness: z.array(z.object({ _dayOffset: z.number().int() }).loose()),
});

export class FixtureTrainingDataAdapter implements TrainingDataPort {
  private readonly activities: Activity[];
  private readonly wellness: WellnessDay[];
  private readonly athlete: AthleteProfile;

  constructor(path: string, clock: ClockPort) {
    const file = fixtureFileSchema.parse(JSON.parse(readFileSync(path, "utf8")));
    const today = clock.today();
    this.athlete = toAthleteProfile(rawAthleteSchema.parse(file.athlete));
    this.activities = file.activities.map(({ _dayOffset, _time, ...raw }) =>
      toActivity(rawActivitySchema.parse({ ...raw, start_date_local: `${addDays(today, _dayOffset)}T${_time}` })),
    );
    this.wellness = file.wellness.map(({ _dayOffset, ...raw }) =>
      toWellness(rawWellnessSchema.parse({ ...raw, id: addDays(today, _dayOffset) })),
    );
  }

  async getAthleteProfile(): Promise<AthleteProfile> {
    return this.athlete;
  }

  async listActivities(range: DateRange): Promise<Activity[]> {
    return this.activities.filter((a) => inRange(a.startDateLocal.slice(0, 10), range));
  }

  async getActivity(id: string): Promise<Activity | null> {
    return this.activities.find((a) => a.id === id) ?? null;
  }

  async listWellness(range: DateRange): Promise<WellnessDay[]> {
    return this.wellness.filter((w) => inRange(w.date, range));
  }
}

const inRange = (d: string, r: DateRange) => d >= r.oldest && d <= r.newest;
