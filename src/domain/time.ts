import type { IsoDate } from "./model.js";

export const RACE_DISTANCES = {
  "5k": 5000,
  "10k": 10000,
  half: 21097.5,
  marathon: 42195,
} as const;

export type NamedDistance = keyof typeof RACE_DISTANCES;

export function resolveDistanceM(distance: NamedDistance | number): number {
  return typeof distance === "number" ? distance * 1000 : RACE_DISTANCES[distance];
}

/** "2:55:00" | "39:15" | "0:39:15" -> seconds */
export function parseDuration(text: string): number {
  const parts = text.trim().split(":").map(Number);
  if (parts.length < 2 || parts.length > 3 || parts.some((n) => !Number.isFinite(n) || n < 0)) {
    throw new Error(`Invalid duration "${text}" (expected h:mm:ss or mm:ss)`);
  }
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

export function formatDuration(totalSec: number): string {
  const s = Math.round(totalSec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(h > 0 ? 2 : 1, "0");
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function formatPace(secPerKm: number): string {
  return `${formatDuration(secPerKm)}/km`;
}

export const paceSecPerKm = (distanceM: number, timeSec: number): number =>
  timeSec / (distanceM / 1000);

/* ---------- calendar helpers (pure, UTC-based on date-only strings) ---------- */

export function addDays(date: IsoDate, days: number): IsoDate {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function daysBetween(from: IsoDate, to: IsoDate): number {
  const a = Date.parse(`${from}T00:00:00Z`);
  const b = Date.parse(`${to}T00:00:00Z`);
  return Math.round((b - a) / 86_400_000);
}

/** Monday of the ISO week containing `date` */
export function weekStart(date: IsoDate): IsoDate {
  const d = new Date(`${date}T00:00:00Z`);
  const dow = (d.getUTCDay() + 6) % 7; // 0 = Monday
  return addDays(date, -dow);
}
