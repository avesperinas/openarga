import { missingKeys } from "@openarga/ui";
import { afterEach, describe, expect, it } from "vitest";

import { CATALOGS, setLocale } from "./lang";
import { VIEWS, fetchWindow, monthOf, parsePlace, pathOf, scroll, step, switchView, titleOf, visibleDays } from "./views";

const TODAY = "2026-09-30";

describe("the address", () => {
  it("with nothing, the week on a computer and three days on a phone, today", () => {
    expect(parsePlace("/planner", 1280, TODAY)).toEqual({ view: "week", day: TODAY });
    expect(parsePlace("/planner/", 390, TODAY)).toEqual({ view: "three", day: TODAY });
  });

  it("each view goes there and back", () => {
    for (const place of [
      { view: "day", day: "2026-10-02" },
      { view: "three", day: "2026-10-02" },
      { view: "week", day: "2026-10-02" },
      { view: "month", day: "2026-10-01" },
      { view: "month", day: "2026-10-19" },
    ] as const) {
      expect(parsePlace(pathOf(place, TODAY), 1280, TODAY)).toEqual(place);
    }
    expect(pathOf({ view: "agenda", day: TODAY }, TODAY)).toBe("/planner/agenda");
    expect(pathOf({ view: "month", day: "2026-10-01" }, TODAY)).toBe("/planner/month/2026-10");
    expect(pathOf({ view: "month", day: "2026-10-19" }, TODAY)).toBe("/planner/month/2026-10-19");
  });
});

describe("the days of each view", () => {
  it("the week runs Monday to Sunday even if the day is a Wednesday", () => {
    const days = visibleDays({ view: "week", day: TODAY });
    expect([days[0], days[6]]).toEqual(["2026-09-28", "2026-10-04"]);
  });

  it("the month is six weeks and the agenda sixty days", () => {
    expect(visibleDays({ view: "month", day: "2026-09-01" })).toHaveLength(42);
    expect(visibleDays({ view: "agenda", day: TODAY })).toHaveLength(60);
  });

  it("a step is as long as the view, except three days, which goes day by day", () => {
    expect(step({ view: "three", day: TODAY }, 1).day).toBe("2026-10-01");
    expect(step({ view: "three", day: TODAY }, -2).day).toBe("2026-09-28");
    expect(step({ view: "week", day: TODAY }, -1).day).toBe("2026-09-21");
    expect(step({ view: "month", day: "2026-01-01" }, 1).day).toBe("2026-02-01");
  });

  it("the month moves week by week, and weeks of two months show together", () => {
    const october = { view: "month", day: "2026-10-01" } as const;
    expect(visibleDays(october)[0]).toBe("2026-09-28");
    const later = scroll(october, 3);
    expect(later.day).toBe("2026-10-19");
    expect([visibleDays(later)[0], visibleDays(later)[41]]).toEqual(["2026-10-19", "2026-11-29"]);
    expect(scroll(later, -3)).toEqual({ view: "month", day: "2026-09-28" });
  });

  it("the month in charge is the one in the middle of what shows, and the arrows start from it", () => {
    expect(monthOf({ view: "month", day: "2026-10-01" })).toBe("2026-10");
    expect(monthOf({ view: "month", day: "2026-10-19" })).toBe("2026-11");
    expect(monthOf({ view: "month", day: "2026-10-05" })).toBe("2026-10");
    expect(step({ view: "month", day: "2026-10-19" }, 1).day).toBe("2026-12-01");
    expect(step({ view: "month", day: "2026-10-19" }, -1).day).toBe("2026-10-01");
    expect(titleOf({ view: "month", day: "2026-10-19" }).title).toBe("Noviembre 2026");
    expect(switchView({ view: "month", day: "2026-10-19" }, "week", TODAY)).toEqual({ view: "week", day: "2026-11-01" });
  });

  it("leaving the month for another view goes to today if it is this month", () => {
    expect(switchView({ view: "month", day: "2026-09-01" }, "day", TODAY)).toEqual({ view: "day", day: TODAY });
    expect(switchView({ view: "month", day: "2026-11-01" }, "week", TODAY)).toEqual({ view: "week", day: "2026-11-01" });
    expect(switchView({ view: "week", day: TODAY }, "month", TODAY)).toEqual({ view: "month", day: "2026-09-01" });
  });

  it("what is asked for has a step of margin on each side", () => {
    const { from, to } = fetchWindow({ view: "week", day: TODAY });
    expect(from.getDate()).toBe(21);
    expect(to.getDate()).toBe(12);
  });

  it("the month asks for whole months: moving a week asks for nothing new", () => {
    const window = fetchWindow({ view: "month", day: "2026-10-01" });
    expect([window.from.getMonth(), window.from.getDate(), window.to.getMonth(), window.to.getDate()]).toEqual([8, 1, 11, 1]);
    expect(fetchWindow({ view: "month", day: "2026-10-05" })).toEqual(window);
  });
});

describe("the title", () => {
  it("one month, two months and one day", () => {
    expect(titleOf({ view: "week", day: "2026-09-14" })).toEqual({ title: "September 2026", week: 38 });
    expect(titleOf({ view: "week", day: TODAY }).title).toBe("Sept – Oct 2026");
    expect(titleOf({ view: "day", day: TODAY }).title).toBe("Wednesday 30 September");
    expect(titleOf({ view: "three", day: "2026-12-30" }).title).toBe("Dec 2026 – Jan 2027");
  });
});

describe("the language", () => {
  afterEach(() => setLocale("en"));

  it("both catalogs have the same keys", () => {
    expect(missingKeys(CATALOGS)).toEqual([]);
  });

  it("follows the person's locale", () => {
    setLocale("es");
    expect(VIEWS[0]?.label).toBe(CATALOGS.es!["view.day"]);
    expect(titleOf({ view: "week", day: "2026-09-14" }).title.toLowerCase()).toContain("septiembre");
    setLocale("en");
    expect(VIEWS[0]?.label).toBe("Day");
  });
});
