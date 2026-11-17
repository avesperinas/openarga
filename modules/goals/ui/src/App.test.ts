import { configureRegional, regional } from "@openarga/ui";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { pathOf, route, type Route } from "./App";
import { english, spanish } from "./i18n/testing";
import { groupOf, grouped, quickDates, todayRing, whenLabel } from "./words";

const ID = "0a0a0a0a-0000-4000-8000-00000000a0a0";

describe("every screen has its address", () => {
  const cases: [string, Route][] = [
    ["/goals/", { tab: "home" }],
    ["/goals/goals", { tab: "goals" }],
    [`/goals/goal/${ID}`, { tab: "goals", goal: ID }],
    [`/goals/task/${ID}`, { tab: "home", task: ID }],
    ["/goals/done", { tab: "done" }],
    ["/goals/categories", { tab: "categories" }],
    ["/goals/settings", { tab: "settings" }],
  ];
  it.each(cases)("%s", (path, expected) => {
    expect(route(path)).toEqual(expected);
    expect(pathOf(expected)).toBe(path);
  });

  it("anything unknown leads to the front page, the tasks", () => {
    expect(route("/goals/whatever")).toEqual({ tab: "home" });
  });
});

const TODAY = "2026-09-28";

describe("when, said short", () => {
  const saved = regional();
  beforeEach(() => configureRegional({ locale: "en-US" }));
  afterEach(() => configureRegional(saved));

  it.each([
    ["2026-09-28", null, "today"],
    ["2026-09-29", null, "tomorrow"],
    ["2026-09-27", null, "yesterday"],
    ["2026-09-25", null, "3 days ago"],
    ["2026-10-02", "18:30:00", "2 Fri · 18:30"],
    ["2026-10-14", null, "Oct 14"],
    ["2027-01-05", null, "Jan 5, 2027"],
  ])("%s %s", (due_on, due_time, expected) => {
    expect(whenLabel(english, { due_on, due_time }, TODAY)).toBe(expected);
  });

  it("without a date it says nothing", () => {
    expect(whenLabel(english, { due_on: null, due_time: null }, TODAY)).toBeNull();
  });
});

describe("when, said short in Spanish", () => {
  const saved = regional();
  beforeEach(() => configureRegional({ locale: "es-ES" }));
  afterEach(() => configureRegional(saved));

  it.each([
    ["2026-09-29", null, spanish("when.tomorrow")],
    ["2026-09-25", null, spanish("when.days_ago", { count: 3 })],
    ["2026-10-14", null, "14 oct"],
  ])("%s %s", (due_on, due_time, expected) => {
    expect(whenLabel(spanish, { due_on, due_time }, TODAY)).toBe(expected);
  });
});

describe("the front page by date", () => {
  it("groups in order and leaves the empty groups out", () => {
    const tasks = [
      { status: "upcoming" as const, due_on: "2026-10-20" },
      { status: "someday" as const, due_on: null },
      { status: "overdue" as const, due_on: "2026-09-26" },
      { status: "today" as const, due_on: "2026-09-28" },
      { status: "upcoming" as const, due_on: "2026-09-29" },
    ];
    const groups = grouped(english, tasks, TODAY);
    expect(groups.map((group) => [group.id, group.tasks.length])).toEqual([
      ["overdue", 1],
      ["today", 1],
      ["tomorrow", 1],
      ["later", 1],
      ["someday", 1],
    ]);
    expect(groups[0]!.label).toBe(english("group.overdue"));
  });

  it("today with its time passed goes with the overdue, because the service says so", () => {
    expect(groupOf({ status: "overdue", due_on: TODAY }, TODAY)).toBe("overdue");
  });

  it("within a week is the week", () => {
    expect(groupOf({ status: "upcoming", due_on: "2026-10-05" }, TODAY)).toBe("week");
  });
});

describe("dates in one tap", () => {
  it("Saturday and Monday are the next ones after today", () => {
    const quick = Object.fromEntries(quickDates(english, TODAY).map((one) => [one.key, one.value]));
    expect(quick).toEqual({
      none: null,
      today: "2026-09-28",
      tomorrow: "2026-09-29",
      saturday: "2026-10-03",
      monday: "2026-10-05",
    });
  });
});

describe("today's ring in Tasks (T-B22)", () => {
  it("counts what was ticked today against what was due today, and warns of the overdue", () => {
    const task = (status: string, done_at: string | null = null) => ({ status, done_at }) as never;
    const today = "2026-11-02";
    const ring = todayRing(
      english,
      [task("overdue"), task("today"), task("someday")],
      [task("done", "2026-11-02T09:00:00Z"), task("done", "2026-11-01T09:00:00Z")],
      today,
    );
    expect(ring).toMatchObject({ value: "1/3", label: "done today", detail: "1 overdue · 3 pending in total", tone: "warning" });
    expect(ring.share).toBeCloseTo(1 / 3);
    expect(todayRing(english, [task("someday")], [], today)).toMatchObject({ share: null, label: "Nothing for today" });
  });
});
