import { describe, expect, it } from "vitest";

import type { Occurrence } from "./api";
import { blankForm, changesOf, draftOf, formOf, moveStart, problemOf } from "./form";

const occurrence = (over: Partial<Occurrence>): Occurrence => ({
  id: "e1",
  event_id: "e1",
  calendar_id: "c1",
  title: "Pádel",
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

describe("el formulario", () => {
  it("de todo el día enseña el último día incluido y manda el siguiente", () => {
    const form = formOf(occurrence({ all_day: true, start: "2026-10-01", end: "2026-10-05" }), null);
    expect([form.startDay, form.endDay]).toEqual(["2026-10-01", "2026-10-04"]);
    const draft = draftOf(form, "Europe/Madrid");
    expect([draft.start, draft.end]).toEqual(["2026-10-01", "2026-10-05"]);
  });

  it("con hora, en el reloj de quien mira", () => {
    const form = formOf(occurrence({}), null);
    expect([form.startDay, form.startTime, form.endTime]).toEqual(["2026-09-30", "18:30", "20:00"]);
  });

  it("mover el inicio arrastra el fin y conserva la duración", () => {
    const form = moveStart(formOf(occurrence({}), null), "2026-10-01", "23:30");
    expect([form.endDay, form.endTime]).toEqual(["2026-10-02", "01:00"]);
  });

  it("solo manda lo que ha cambiado, y la hora entera o nada", () => {
    const before = formOf(occurrence({}), "FREQ=WEEKLY");
    expect(changesOf(before, { ...before, title: "Pádel con Mikel" }, "Europe/Madrid")).toEqual({ title: "Pádel con Mikel" });
    const moved = changesOf(before, { ...before, endTime: "21:00" }, "Europe/Madrid");
    expect(Object.keys(moved).sort()).toEqual(["all_day", "end", "start"]);
    expect(changesOf(before, { ...before, location: "" }, "Europe/Madrid")).toEqual({ location: null });
  });

  it("dice lo que no cuadra", () => {
    const blank = blankForm(new Date(2026, 8, 30, 10), new Date(2026, 8, 30, 11), "c1");
    expect(problemOf(blank)).toBe("Ponle un título.");
    expect(problemOf({ ...blank, title: "x", endTime: "09:00" })).toBe("El fin va después del inicio.");
    expect(problemOf({ ...blank, title: "x", url: "ejemplo.com" })).toBe("El enlace empieza por https://.");
    expect(problemOf({ ...blank, title: "x" })).toBeNull();
  });
});
