import { describe, expect, it } from "vitest";

import { addDays, categoryOf, dateRange, daysBetween, daysRange, euros, flag, mapsLink, monthsLabel, nights } from "./words";
import { route, pathOf } from "./App";
import { nightsByMonth } from "./Stats";

describe("how things are said", () => {
  it("a trip's dates, without repeating what they share", () => {
    expect(dateRange("2025-03-07", "2025-03-09")).toBe("7–9 Mar 2025");
    expect(dateRange("2025-02-28", "2025-03-03")).toBe("28 Feb – 3 Mar 2025");
    expect(dateRange("2024-12-30", "2025-01-02")).toBe("30 Dec 2024 – 2 Jan 2025");
  });

  it("nights, singular and plural", () => {
    expect(nights(1)).toBe("1 night");
    expect(nights(3)).toBe("3 nights");
  });

  it("the flag comes from the code and an odd code draws nothing", () => {
    expect(flag("BE")).toBe("🇧🇪");
    expect(flag(null)).toBe("");
    expect(flag("be")).toBe("");
  });

  it("euros without cents and days between dates", () => {
    expect(euros(1234.4)).toMatch(/1,234|1\.234/);
    expect(daysBetween("2025-03-07", "2025-03-09")).toBe(2);
    expect(addDays("2025-02-28", 1)).toBe("2025-03-01");
  });
});

describe("the addresses", () => {
  const ID = "3f0c2a5e-9a6b-4d51-9c3e-0d9a1b2c3d4e";

  it("each screen has its own and comes back the same", () => {
    for (const to of [
      { screen: "map" },
      { screen: "trips" },
      { screen: "journey" },
      { screen: "trip", id: ID },
      { screen: "edit", id: ID },
      { screen: "edit", id: null },
      { screen: "stats" },
    ] as const) {
      expect(route(pathOf(to))).toEqual(to);
    }
  });

  it("what is not recognised is the map", () => {
    expect(route("/travel/whatever")).toEqual({ screen: "map" });
  });
});

describe("the nights calendar", () => {
  it("counts the nights of each month of each year, the latest year on top", () => {
    const months = nightsByMonth({ "2024-04-10": 1, "2024-04-11": 1, "2025-01-31": 1 });
    expect([...months.keys()]).toEqual([2025, 2024]);
    expect(months.get(2024)![3]).toBe(2);
    expect(months.get(2025)![0]).toBe(1);
  });
});

describe("ideas", () => {
  it("months in a row go together and days, from so many to so many", () => {
    expect(monthsLabel([10, 4, 5, 6])).toBe("Apr–Jun, Oct");
    expect(monthsLabel([12])).toBe("Dec");
    expect(daysRange(4, 6)).toBe("4–6 days");
    expect(daysRange(null, 1)).toBe("1 day");
    expect(daysRange(null, null)).toBeNull();
  });
});

describe("kinds of place", () => {
  it("a place without a kind shows as other", () => {
    expect(categoryOf({ category: "beach" }).icon).toBe("umbrella");
    expect(categoryOf({ category: null }).label).toBe("Other");
    expect(categoryOf(null).label).toBe("Other");
  });

  it("on the iPhone it opens Apple Maps and elsewhere Google Maps", () => {
    expect(mapsLink(47.507, 19.0456, "Parliament", true)).toBe(
      "https://maps.apple.com/?ll=47.507000,19.045600&q=Parliament",
    );
    expect(mapsLink(47.507, 19.0456, "Parliament", false)).toContain("google.com/maps/search");
  });
});

describe("a trip's sections", () => {
  const id = "3abfed4f-8cde-44ad-b81a-d0039f5a2ba6";
  it("each one has its address, there and back", () => {
    for (const screen of ["trip", "days", "tripmap", "bookings", "money", "notes"] as const) {
      expect(route(pathOf({ screen, id }))).toEqual({ screen, id });
    }
  });
});
