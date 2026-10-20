/**
 * Generates fixtures/athlete-sub3.json — a synthetic ~16-week block for a
 * runner around 70 km/week, with a 1:24 half 6 days ago and two recent 10ks.
 * Output is in the raw intervals.icu shape (see fixture.adapter.ts).
 *
 * Deterministic (seeded PRNG) so the committed file is reproducible.
 * Later: replace with a `record-fixture` script that pulls YOUR real data and
 * anonymises it — that's how you grow a realistic golden dataset.
 */
import { writeFileSync } from "node:fs";

const ANCHOR = new Date("2026-10-17T00:00:00Z"); // a Saturday; offsets are relative to it
const DAYS = 16 * 7;

let seed = 42;
const rand = () => ((seed = (seed * 1664525 + 1013904223) % 2 ** 32) / 2 ** 32);
const jitter = (n: number, pct: number) => n * (1 + (rand() * 2 - 1) * pct);

type Raw = Record<string, unknown> & { _dayOffset: number; _time: string };
const activities: Raw[] = [];
const loadByOffset = new Map<number, number>();
let nextId = 1_000_000;

function run(o: number, name: string, km: number, paceSec: number, hr: number, intensity: number, extra: Record<string, unknown> = {}) {
  const moving = Math.round(km * paceSec);
  const load = Math.round((moving / 3600) * intensity * intensity * 100);
  loadByOffset.set(o, (loadByOffset.get(o) ?? 0) + load);
  activities.push({
    _dayOffset: o,
    _time: "07:15:00",
    id: `i${nextId++}`,
    name,
    type: "Run",
    distance: Math.round(km * 1000),
    moving_time: moving,
    elapsed_time: moving + 60,
    average_heartrate: Math.round(hr),
    max_heartrate: Math.round(hr + 12),
    total_elevation_gain: Math.round(jitter(km * 4, 0.4)),
    icu_training_load: load,
    ...extra,
  });
}

function reps(n: number, repM: number, repPace: number, recM: number, recPace: number, hr: number) {
  const out: Record<string, unknown>[] = [];
  for (let i = 0; i < n; i++) {
    out.push({ label: `Rep ${i + 1}`, type: "WORK", distance: repM, moving_time: Math.round(jitter((repM / 1000) * repPace, 0.012)), average_heartrate: Math.round(jitter(hr, 0.01)) });
    if (i < n - 1) out.push({ type: "RECOVERY", distance: recM, moving_time: Math.round((recM / 1000) * recPace), average_heartrate: Math.round(hr - 25) });
  }
  return out;
}

for (let o = -DAYS + 1; o <= 0; o++) {
  const date = new Date(ANCHOR.getTime() + o * 86_400_000);
  const dow = date.getUTCDay(); // 0 Sun .. 6 Sat

  // ---- special days (races, taper, recovery) ----
  if (o === -39) { run(o, "10K race", 10.02, 239, 178, 1.02, { race: true }); continue; }
  if (o === -34) { run(o, "10K race - PB", 10.0, 235.5, 180, 1.03, { race: true }); continue; }
  if (o === -6) { run(o, "Half marathon race", 21.1, 238.9, 176, 1.0, { race: true }); continue; }
  if (o > -6) {
    if (o === -4) run(o, "Recovery jog", 7.0, 320, 132, 0.68);
    if (o === -2) run(o, "Easy run", 9.0, 310, 136, 0.7);
    if (o === 0) run(o, "Easy run + strides", 10.2, 305, 139, 0.72, {
      icu_intervals: reps(6, 100, 200, 100, 330, 160),
    });
    continue;
  }
  const taper = o > -13; // week before the half
  const scale = taper ? 0.6 : 1;

  switch (dow) {
    case 1: break; // Monday rest
    case 2: { // VMA
      const n = taper ? 4 : 6;
      run(o, `VMA ${n}x1000m`, 12 * scale + 2, 290, 152, 0.9, { icu_intervals: reps(n, 1000, jitter(216, 0.01), 400, 360, 172) });
      break;
    }
    case 3: run(o, "Easy run", jitter(11 * scale, 0.1), jitter(305, 0.02), jitter(140, 0.02), 0.72); break;
    case 4: { // threshold
      const n = taper ? 2 : 3;
      run(o, `Threshold ${n}x3km`, n * 3 + 5, 268, 158, 0.88, { icu_intervals: reps(n, 3000, jitter(238, 0.008), 600, 340, 167) });
      break;
    }
    case 5: run(o, "Easy run", jitter(8 * scale, 0.1), jitter(310, 0.02), jitter(138, 0.02), 0.7); break;
    case 6: run(o, "Progression run", jitter(12 * scale, 0.05), jitter(280, 0.02), 148, 0.8); break;
    case 0: { // long run, building 20 -> 28 km
      const km = taper ? 14 : Math.min(28, 20 + Math.floor((o + DAYS) / 14));
      run(o, "Long run", km, jitter(292, 0.015), 145, 0.76);
      break;
    }
  }
}

// ---- wellness: CTL/ATL as 42/7-day exponentially weighted load ----
const wellness: Record<string, unknown>[] = [];
let ctl = 48;
let atl = 52;
const ctlHistory: number[] = [];
for (let o = -DAYS + 1; o <= 0; o++) {
  const load = loadByOffset.get(o) ?? 0;
  ctl += (load - ctl) / 42;
  atl += (load - atl) / 7;
  ctlHistory.push(ctl);
  const weekAgo = ctlHistory[ctlHistory.length - 8] ?? ctlHistory[0]!;
  wellness.push({
    _dayOffset: o,
    ctl: Math.round(ctl * 10) / 10,
    atl: Math.round(atl * 10) / 10,
    rampRate: Math.round((ctl - weekAgo) * 10) / 10, // CTL change over 7 days
    restingHR: Math.round(jitter(46, 0.04)),
    hrv: Math.round(jitter(72, 0.1)),
    sleepSecs: Math.round(jitter(7.4 * 3600, 0.08)),
  });
}

const fixture = {
  athlete: {
    id: "i000000",
    name: "Demo Athlete",
    sportSettings: [{ types: ["Run", "TrailRun", "VirtualRun"], threshold_pace: 1000 / 240, lthr: 171, max_hr: 192 }],
  },
  activities,
  wellness,
};

writeFileSync(new URL("../fixtures/athlete-sub3.json", import.meta.url), JSON.stringify(fixture, null, 1) + "\n");
console.log(`wrote ${activities.length} activities, ${wellness.length} wellness days`);
