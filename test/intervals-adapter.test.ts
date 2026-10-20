import { describe, expect, it, vi } from "vitest";
import { IntervalsIcuAdapter, IntervalsIcuError } from "../src/adapters/intervals-icu/intervals-icu.adapter.js";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("IntervalsIcuAdapter", () => {
  it("uses Basic auth with the API_KEY username and maps activities to the domain", async () => {
    const fetchImpl = vi.fn(async () =>
      json([
        {
          id: "i123",
          name: "Long run",
          type: "Run",
          start_date_local: "2026-10-11T08:00:00",
          distance: 28000,
          moving_time: 8200,
          average_heartrate: 145,
          icu_training_load: 160,
          some_unknown_field: { ignored: true },
        },
      ]),
    );
    const adapter = new IntervalsIcuAdapter({ apiKey: "secret", fetchImpl: fetchImpl as unknown as typeof fetch });
    const [a] = await adapter.listActivities({ oldest: "2026-10-01", newest: "2026-10-17" });

    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://intervals.icu/api/v1/athlete/0/activities?oldest=2026-10-01&newest=2026-10-17");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      `Basic ${Buffer.from("API_KEY:secret").toString("base64")}`,
    );
    expect(a).toMatchObject({ id: "i123", distanceM: 28000, movingTimeSec: 8200, avgHr: 145, trainingLoad: 160 });
  });

  it("retries on 429 then succeeds", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(json({}, 429))
      .mockResolvedValueOnce(json([{ id: "2026-10-17", ctl: 55, atl: 40, sleepSecs: 27000 }]));
    const adapter = new IntervalsIcuAdapter({ apiKey: "k", fetchImpl, maxRetries: 1 });
    const [w] = await adapter.listWellness({ oldest: "2026-10-17", newest: "2026-10-17" });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(w).toEqual({ date: "2026-10-17", ctl: 55, atl: 40, sleepHours: 7.5, rampRate: undefined, restingHr: undefined, hrv: undefined });
  });

  it("returns null for a missing activity and throws on auth errors", async () => {
    const notFound = new IntervalsIcuAdapter({ apiKey: "k", fetchImpl: vi.fn(async () => json({}, 404)) });
    expect(await notFound.getActivity("nope")).toBeNull();
    const unauthorized = new IntervalsIcuAdapter({ apiKey: "k", fetchImpl: vi.fn(async () => json({}, 401)) });
    await expect(unauthorized.getActivity("x")).rejects.toBeInstanceOf(IntervalsIcuError);
  });
});
