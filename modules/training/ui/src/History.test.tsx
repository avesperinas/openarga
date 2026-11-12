import { renderToString } from "react-dom/server";

import type { SessionSummary } from "./api";
import { HistoryScreen, hours, marksOf, monthStats, rotationOf, weekBelow, yearDays } from "./History";
import { describeActivity, nowQuarter } from "./Activities";
import { english, inLocale, spanish } from "./i18n/testing";

const NOW = new Date(2026, 8, 16, 12);

function session(day: string, kind: SessionSummary["kind"], minutes: number | null = 50): SessionSummary {
  return {
    id: `s-${day}-${kind}`,
    day,
    started_at: `${day}T17:00:00Z`,
    ended_at: minutes === null ? null : `${day}T18:00:00Z`,
    duration_seconds: minutes === null ? null : minutes * 60,
    day_name: kind === "push" ? "Push" : "Pull",
    kind,
    rotation_number: 1,
    gym: null,
    exercises: 3,
    sets: 10,
  };
}

describe("the calendar", () => {
  it("without workouts it paints the whole month and says there is nothing", () => {
    const html = renderToString(
      inLocale(<HistoryScreen onOpenSession={() => undefined} now={NOW} initial={{ sessions: [], goal: 4 }} />),
    );

    expect(html.match(/role="gridcell"/g)).toHaveLength(30);
    expect(html).toContain("No workouts yet");
  });

  it("with workouts it marks the days by kind and lists those of the month", () => {
    const sessions = [session("2026-09-15", "pull"), session("2026-09-14", "push")];
    const html = renderToString(
      inLocale(<HistoryScreen onOpenSession={() => undefined} now={NOW} initial={{ sessions, goal: 4 }} />),
    ).replaceAll("<!-- -->", "");

    expect(html).toMatch(/data-marked="true" data-kind="push"/);
    expect(html).toContain(">Pull<");
    expect(html).toContain("Tue, Sep 15 · 50 min · 10 sets");
    expect(html).toContain("<dt>workouts</dt><dd>2</dd>");
    expect(html).toContain(">R1</span>");
    expect(html).toContain('aria-label="Sets per day in the last year"');
  });

  it("two workouts on the same day, both, in the order they were done", () => {
    const marks = marksOf([session("2026-09-14", "pull"), session("2026-09-14", "push")]);
    expect(marks["2026-09-14"]?.map((mark) => mark.kind)).toEqual(["push", "pull"]);
  });

  it("the month summary leaves out of the average what did not finish", () => {
    expect(monthStats([session("2026-09-14", "push", 60), session("2026-09-15", "pull", null)])).toEqual({
      count: 2,
      sets: 20,
      averageSeconds: 3600,
      totalSeconds: 3600,
    });
  });

  it("each week carries the rotation of its first workout (T-B05)", () => {
    const sessions = [
      { ...session("2026-09-15", "pull"), rotation_number: 13 },
      { ...session("2026-09-14", "push"), rotation_number: 12 },
    ];
    expect(rotationOf("2026-09-14", sessions)).toBe("R12");
    expect(rotationOf("2026-09-07", sessions)).toBeNull();
  });

  it("the year counts sets per day, with zeros from the first workout and nothing before", () => {
    const days = yearDays([session("2026-09-14", "push"), session("2026-09-12", "pull")], "2026-09-15");
    expect(days).toEqual([
      { day: "2026-09-12", value: 10 },
      { day: "2026-09-13", value: 0 },
      { day: "2026-09-14", value: 10 },
      { day: "2026-09-15", value: 0 },
    ]);
  });

  it("the hours of the month read at a glance", () => {
    expect(hours(45 * 60)).toBe("45 min");
    expect(hours(21 * 3600 + 20 * 60)).toBe("21 h");
  });

  it("a week below only counts if it is over and after the first workout", () => {
    const sessions = [session("2026-09-08", "push"), session("2026-09-01", "push")];
    expect(weekBelow("2026-09-07", sessions, 3, "2026-09-16")).toBe(true);
    expect(weekBelow("2026-08-24", sessions, 3, "2026-09-16")).toBe(false);
    expect(weekBelow("2026-09-14", sessions, 3, "2026-09-16")).toBe(false);
    expect(weekBelow("2026-09-07", sessions, 1, "2026-09-16")).toBe(false);
  });
});

describe("activities on the calendar", () => {
  it("mark their day, after the workout if there was one that day too", () => {
    const climbing = { id: "a1", activity_type_id: "t", name: "Climbing", day: "2026-09-14", start_time: "18:30:00", duration_seconds: 5400, notes: null };
    const marks = marksOf([session("2026-09-14", "push")], [climbing, { ...climbing, id: "a2", day: "2026-09-12" }]);
    expect(marks["2026-09-14"]?.map((mark) => mark.kind)).toEqual(["push", "activity"]);
    expect(marks["2026-09-12"]).toEqual([{ kind: "activity", label: "Climbing" }]);
  });
});

describe("the time of an activity", () => {
  it("proposes now, rounded down to the quarter hour, and shows it with the duration", () => {
    expect(nowQuarter(new Date(2026, 8, 29, 18, 44))).toBe("18:30");
    expect(nowQuarter(new Date(2026, 8, 29, 7, 5))).toBe("07:00");
    expect(
      describeActivity({ id: "a", activity_type_id: "t", name: "Swimming", day: "2026-09-29", start_time: "19:00:00", duration_seconds: 3600, notes: null }, english),
    ).toBe("19:00 · 1 h 00 min");
  });
});

describe("the calendar in Spanish", () => {
  it("names the month and the sets in the language of the person", () => {
    const html = renderToString(
      inLocale(
        <HistoryScreen onOpenSession={() => undefined} now={NOW} initial={{ sessions: [session("2026-09-15", "pull")], goal: 4 }} />,
        "es",
      ),
    ).replaceAll("<!-- -->", "");

    expect(html).toContain(spanish("common.sets.other", { count: 10 }));
    expect(html).toContain(spanish("history.this_month"));
  });
});
