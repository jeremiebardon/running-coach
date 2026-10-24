import { describe, expect, it } from "vitest";
import { createSseParser } from "./parser";

const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

describe("SSE parser", () => {
  it("turns whole frames into typed events", () => {
    const parser = createSseParser();
    const events = parser.push(
      frame("session", { sessionId: "s1" }) +
        frame("tool_call", { name: "get_activity_details", input: { date: "2026-10-17" } }) +
        frame("token", { text: "Nice" }),
    );
    expect(events).toEqual([
      { type: "session", sessionId: "s1" },
      { type: "tool_call", name: "get_activity_details", input: { date: "2026-10-17" } },
      { type: "token", text: "Nice" },
    ]);
  });
});

describe("SSE parser across chunk boundaries", () => {
  it("assembles a frame split mid-line across chunks", () => {
    const parser = createSseParser();
    const wire = frame("token", { text: "Hello" });
    const cut = wire.indexOf("Hel") + 2;
    expect(parser.push(wire.slice(0, cut))).toEqual([]);
    expect(parser.push(wire.slice(cut))).toEqual([{ type: "token", text: "Hello" }]);
  });

  it("assembles a multi-byte character split across byte chunks", () => {
    const parser = createSseParser();
    const bytes = new TextEncoder().encode(frame("token", { text: "5 km ✓" }));
    const cut = bytes.length - 6; // lands inside the 3-byte "✓"
    expect(parser.push(bytes.slice(0, cut))).toEqual([]);
    expect(parser.push(bytes.slice(cut))).toEqual([{ type: "token", text: "5 km ✓" }]);
  });

  it("accepts CRLF line endings", () => {
    const parser = createSseParser();
    const wire = frame("token", { text: "hi" }).replaceAll("\n", "\r\n");
    expect(parser.push(wire)).toEqual([{ type: "token", text: "hi" }]);
  });
});
