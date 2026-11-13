import { missingKeys } from "@openarga/ui";
import { afterEach, describe, expect, it } from "vitest";

import { nearDefault } from "./EventScreen";
import { CATALOGS, dayIn, setLocale } from "./lang";
import { freshSince, freshTitle, kindOf } from "./words";

describe("what is new in Explore", () => {
  it("the notice says from which day; without it, the last week", () => {
    expect(freshSince("2026-11-05", "2026-11-06")).toEqual({ since: "2026-11-05", fromNotice: true });
    expect(freshSince(null, "2026-11-06")).toEqual({ since: "2026-10-31", fromNotice: false });
    expect(freshSince("tomorrow", "2026-11-06").fromNotice).toBe(false);
    expect(freshSince("2026-12-01", "2026-11-06").fromNotice).toBe(false);
  });

  it("its title says when it is from", () => {
    expect(freshTitle("2026-11-06", true, "2026-11-06")).toBe("New today");
    expect(freshTitle("2026-11-05", true, "2026-11-06")).toBe("New since Thursday 5");
    expect(freshTitle("2026-10-31", false, "2026-11-06")).toBe("New this week");
  });
});

describe("wishes near an event", () => {
  const near = (kind: "eat" | "plan" | "getaway", n: number) =>
    Array.from({ length: n }, (_, i) => ({ id: `${kind}${i}`, name: `${kind} ${i}`, kind, km: 1 }));

  it("opens the first kind that is not eat, and with only restaurants, none", () => {
    expect(nearDefault([...near("eat", 17), ...near("plan", 2)])).toBe("plan");
    expect(nearDefault([...near("eat", 3), ...near("getaway", 1)])).toBe("getaway");
    expect(nearDefault(near("eat", 17))).toBeNull();
  });
});

describe("the language", () => {
  afterEach(() => setLocale("en"));

  it("both catalogs have the same keys", () => {
    expect(missingKeys(CATALOGS)).toEqual([]);
  });

  it("follows the person's locale", () => {
    setLocale("es");
    expect(freshTitle("2026-11-06", true, "2026-11-06")).toBe(CATALOGS.es!["fresh.today"]);
    expect(kindOf("trip").label).toBe(CATALOGS.es!["kind.trip"]);
    setLocale("en");
    expect(kindOf("trip").label).toBe("Trip");
  });
});

describe("today", () => {
  it("is the day in the person's time zone", () => {
    const late = new Date("2026-11-13T02:30:00Z");
    expect(dayIn(late, "Europe/Madrid")).toBe("2026-11-13");
    expect(dayIn(late, "America/New_York")).toBe("2026-11-12");
  });
});
