import { describe, expect, it } from "vitest";
import { buildPacingPlan } from "../src/domain/pacing.js";
import { predictRace } from "../src/domain/predictor.js";
import { formatDuration, parseDuration, weekStart } from "../src/domain/time.js";
import { formZone } from "../src/domain/training.js";
import { predictTimeFromVdot, riegel, vdotFromPerformance } from "../src/domain/vdot.js";

describe("time helpers", () => {
  it("parses and formats durations", () => {
    expect(parseDuration("2:55:00")).toBe(10500);
    expect(parseDuration("39:15")).toBe(2355);
    expect(formatDuration(10500)).toBe("2:55:00");
    expect(formatDuration(2355)).toBe("39:15");
    expect(() => parseDuration("abc")).toThrow();
  });
  it("finds the Monday of a week", () => {
    expect(weekStart("2026-10-17")).toBe("2026-10-12"); // Saturday -> Monday
    expect(weekStart("2026-10-12")).toBe("2026-10-12");
  });
});

describe("VDOT & Riegel", () => {
  it("matches published VDOT tables within tolerance", () => {
    // Daniels' tables: VDOT 50 ≈ 19:57 5k / 3:10:49 marathon
    expect(vdotFromPerformance(5000, 19 * 60 + 57)).toBeCloseTo(50, 0);
    expect(predictTimeFromVdot(50, 42195) / 60).toBeCloseTo(190.8, -0.5);
  });
  it("round-trips performance -> vdot -> time", () => {
    const v = vdotFromPerformance(21097.5, 5040);
    expect(predictTimeFromVdot(v, 21097.5)).toBeCloseTo(5040, 0);
  });
  it("Riegel doubles a half into ~2.085x for a marathon", () => {
    expect(riegel(5040, 21097.5, 42195) / 5040).toBeCloseTo(2.085, 2);
  });
});

describe("predictRace", () => {
  const base = {
    today: "2026-10-17",
    performances: [
      { label: "half", distanceM: 21097.5, timeSec: 5040, date: "2026-10-11", activityId: "a" },
      { label: "10k", distanceM: 10000, timeSec: 2355, date: "2026-09-13", activityId: "b" },
    ],
    targetDistanceM: 42195,
  };

  it("uses the closest-distance reference and rates a sub-2:55 target", () => {
    const p = predictRace({ ...base, context: { avgWeeklyKm: 80, longestRunKm: 28, weeksConsidered: 8 }, targetTimeSec: 10500 });
    if ("error" in p) throw new Error(p.error);
    expect(p.reference.label).toBe("half");
    expect(p.adjustments.some((a) => a.includes("longest recent run"))).toBe(true);
    expect(["borderline", "stretch", "unlikely"]).toContain(p.target?.feasibility);
  });

  it("penalises low volume for the marathon", () => {
    const high = predictRace({ ...base, context: { avgWeeklyKm: 95, longestRunKm: 32, weeksConsidered: 8 } });
    const low = predictRace({ ...base, context: { avgWeeklyKm: 40, longestRunKm: 32, weeksConsidered: 8 } });
    if ("error" in high || "error" in low) throw new Error("unexpected");
    expect(low.predicted.centreSec).toBeGreaterThan(high.predicted.centreSec * 1.03);
  });

  it("returns an error when there is no recent performance", () => {
    const p = predictRace({ ...base, today: "2027-12-01", context: { avgWeeklyKm: 80, longestRunKm: 30, weeksConsidered: 8 } });
    expect("error" in p).toBe(true);
  });
});

describe("pacing plan", () => {
  it("even plan sums exactly to the target", () => {
    const plan = buildPacingPlan({ distanceM: 42195, targetSec: 10500, strategy: "even" });
    expect(plan.splits.at(-1)?.cumulative).toBe("2:55:00");
    expect(plan.averagePace).toBe("4:09/km");
    expect(plan.splits).toHaveLength(9); // 5,10,...,40 + finish
  });
  it("negative split runs the second half faster but keeps the total", () => {
    const plan = buildPacingPlan({ distanceM: 42195, targetSec: 10500, strategy: "negative" });
    expect(parseDuration(plan.firstHalfPace.replace("/km", ""))).toBeGreaterThan(parseDuration(plan.secondHalfPace.replace("/km", "")));
    expect(plan.splits.at(-1)?.cumulative).toBe("2:55:00");
  });
});

describe("form zones", () => {
  it.each([
    [25, "transition"],
    [10, "fresh"],
    [0, "grey-zone"],
    [-20, "optimal-training"],
    [-40, "high-risk"],
  ] as const)("%d%% -> %s", (pct, zone) => expect(formZone(pct)).toBe(zone));
});
