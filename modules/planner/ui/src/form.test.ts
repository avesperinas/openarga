import { describe, expect, it } from "vitest";

import type { Occurrence } from "./api";
import { blankForm, changesOf, draftOf, formOf, moveStart, problemOf } from "./form";

const occurrence = (over: Partial<Occurrence>): Occurrence => ({
  id: "e1",
  event_id: "e1",
  calendar_id: "c1",
  title: "Padel",
  all_day: false,
  start: new Date(2026, 8, 30, 18, 30).toISOString(),
  end: new Date(2026, 8, 30, 20, 0).toISOString(),
  tz: "Europe/Madrid",
  location: "Club",
  notes: null,
  url: null,
  status: "confirmed",
  original_start: null,
  rrule: null,
  repeat: null,
  moved: false,
  ...over,
});

describe("the form", () => {
  it("all day shows the last day included and sends the next", () => {
    const form = formOf(occurrence({ all_day: true, start: "2026-10-01", end: "2026-10-05" }), null);
    expect([form.startDay, form.endDay]).toEqual(["2026-10-01", "2026-10-04"]);
    const draft = draftOf(form, "Europe/Madrid");
    expect([draft.start, draft.end]).toEqual(["2026-10-01", "2026-10-05"]);
  });

  it("timed, on the viewer's clock", () => {
    const form = formOf(occurrence({}), null);
    expect([form.startDay, form.startTime, form.endTime]).toEqual(["2026-09-30", "18:30", "20:00"]);
  });

  it("moving the start drags the end and keeps the duration", () => {
    const form = moveStart(formOf(occurrence({}), null), "2026-10-01", "23:30");
    expect([form.endDay, form.endTime]).toEqual(["2026-10-02", "01:00"]);
  });

  it("only sends what changed, and the whole time or nothing", () => {
    const before = formOf(occurrence({}), "FREQ=WEEKLY");
    expect(changesOf(before, { ...before, title: "Padel with Mikel" }, "Europe/Madrid")).toEqual({ title: "Padel with Mikel" });
    const moved = changesOf(before, { ...before, endTime: "21:00" }, "Europe/Madrid");
    expect(Object.keys(moved).sort()).toEqual(["all_day", "end", "start"]);
    expect(changesOf(before, { ...before, location: "" }, "Europe/Madrid")).toEqual({ location: null });
  });

  it("says what does not add up", () => {
    const blank = blankForm(new Date(2026, 8, 30, 10), new Date(2026, 8, 30, 11), "c1");
    expect(problemOf(blank)).toBe("Give it a title.");
    expect(problemOf({ ...blank, title: "x", endTime: "09:00" })).toBe("The end goes after the start.");
    expect(problemOf({ ...blank, title: "x", url: "example.com" })).toBe("The link starts with https://.");
    expect(problemOf({ ...blank, title: "x" })).toBeNull();
  });
});
