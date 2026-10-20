import type { Activity, AthleteProfile, DateRange, IsoDate, WellnessDay } from "../domain/model.js";

/**
 * Driven (outbound) port: where training data comes from.
 *
 * Implementations: IntervalsIcuAdapter (live HTTP) and FixtureTrainingDataAdapter
 * (recorded payloads for tests/evals). The agent tools only depend on this
 * interface, which is what makes evals deterministic.
 */
export interface TrainingDataPort {
  getAthleteProfile(): Promise<AthleteProfile>;
  listActivities(range: DateRange): Promise<Activity[]>;
  getActivity(id: string): Promise<Activity | null>;
  listWellness(range: DateRange): Promise<WellnessDay[]>;
}

/** "What day is it for the athlete?" — injected so evals can freeze time. */
export interface ClockPort {
  today(): IsoDate;
}

export const systemClock = (timeZone: string): ClockPort => ({
  today: () => new Intl.DateTimeFormat("en-CA", { timeZone }).format(new Date()),
});

export const fixedClock = (date: IsoDate): ClockPort => ({ today: () => date });
