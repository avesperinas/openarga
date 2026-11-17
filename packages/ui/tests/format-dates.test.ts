import { describe, expect, it } from "vitest";

import { clock, longDay, money, shortDay, todayIso } from "../src/format";

describe("dates, times and money, in the person's locale and zone", () => {
  it("today is Madrid's day, not UTC's", () => {
    expect(todayIso(new Date("2025-12-31T23:30:00Z"))).toBe("2026-01-01");
  });

  it("a day without a time reads as is, without shifting day", () => {
    expect(shortDay("2026-09-20")).toBe("20 Sept");
  });

  it("an instant reads in Madrid time, capitalised", () => {
    expect(longDay("2026-09-22T23:30:00Z")).toBe("Wednesday 23 September");
    expect(clock("2026-09-22T07:05:00Z")).toBe("09:05");
  });

  it("money shows cents only when there are some", () => {
    expect(money(1234.5)).toBe("€1,234.50");
    expect(money(20)).toBe("€20");
    expect(money(Number.NaN)).toBe("—");
  });
});
