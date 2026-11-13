import { describe, expect, test } from "vitest";

import { statusLine } from "./Subscribe";

const NOW = new Date("2026-09-28T12:00:00Z").getTime();
const state = (over: Record<string, unknown>) => ({
  subscription: { provider: "ical", updated_at: null, failing: false, detail: null, paused: false, ...over },
});

describe("how a subscription is doing", () => {
  test("until the first pass, it waits", () => {
    expect(statusLine({ subscription: null }, NOW)).toBe("Waiting for the first pass");
    expect(statusLine(state({}), NOW)).toBe("Waiting for the first pass");
  });

  test("the age of what is shown", () => {
    expect(statusLine(state({ updated_at: "2026-09-28T11:59:40Z" }), NOW)).toBe("Updated just now");
    expect(statusLine(state({ updated_at: "2026-09-28T11:35:00Z" }), NOW)).toBe("Updated 25 min ago");
    expect(statusLine(state({ updated_at: "2026-09-28T09:00:00Z" }), NOW)).toBe("Updated 3 h ago");
    expect(statusLine(state({ updated_at: "2026-09-24T12:00:00Z" }), NOW)).toBe("Updated 4 days ago");
  });

  test("failing, in the source's words; paused, it says so", () => {
    expect(statusLine(state({ updated_at: "2026-09-28T09:00:00Z", failing: true, detail: "not answering" }), NOW)).toBe(
      "Failing: not answering",
    );
    expect(statusLine(state({ paused: true }), NOW)).toBe("Paused in Hub");
  });
});
