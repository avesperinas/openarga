import { renderToString } from "react-dom/server";

import type { SessionSummary } from "./api";
import { HistoryScreen, hours, marksOf, monthStats, rotationOf, weekBelow, yearDays } from "./History";
import { describeActivity, nowQuarter } from "./Activities";

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

describe("el calendario", () => {
  it("sin entrenos se pinta el mes entero y dice que no hay nada", () => {
    const html = renderToString(
      <HistoryScreen onOpenSession={() => undefined} now={NOW} initial={{ sessions: [], goal: 4 }} />,
    );

    expect(html).toContain("Septiembre de 2026");
    expect(html.match(/role="gridcell"/g)).toHaveLength(30);
    expect(html).toContain("Todavía no hay entrenos");
  });

  it("con entrenos marca los días por tipo y lista los del mes", () => {
    const sessions = [session("2026-09-15", "pull"), session("2026-09-14", "push")];
    const html = renderToString(
      <HistoryScreen onOpenSession={() => undefined} now={NOW} initial={{ sessions, goal: 4 }} />,
    ).replaceAll("<!-- -->", "");

    expect(html).toMatch(/data-marked="true" data-kind="push"/);
    expect(html).toContain(">Pull<");
    expect(html).toContain("mar, 15 sept · 50 min · 10 series");
    expect(html).toContain("<dt>entrenos</dt><dd>2</dd>");
    expect(html).toContain(">R1</span>");
    expect(html).toContain('aria-label="Series por día en el último año"');
  });

  it("dos entrenos el mismo día, los dos, en el orden en que se hicieron", () => {
    const marks = marksOf([session("2026-09-14", "pull"), session("2026-09-14", "push")]);
    expect(marks["2026-09-14"]?.map((mark) => mark.kind)).toEqual(["push", "pull"]);
  });

  it("el resumen del mes no cuenta en la media lo que no terminó", () => {
    expect(monthStats([session("2026-09-14", "push", 60), session("2026-09-15", "pull", null)])).toEqual({
      count: 2,
      sets: 20,
      averageSeconds: 3600,
      totalSeconds: 3600,
    });
  });

  it("cada semana lleva la rotación de su primer entreno (T-B05)", () => {
    const sessions = [
      { ...session("2026-09-15", "pull"), rotation_number: 13 },
      { ...session("2026-09-14", "push"), rotation_number: 12 },
    ];
    expect(rotationOf("2026-09-14", sessions)).toBe("R12");
    expect(rotationOf("2026-09-07", sessions)).toBeNull();
  });

  it("el año cuenta las series por día, con ceros desde el primer entreno y nada antes", () => {
    const days = yearDays([session("2026-09-14", "push"), session("2026-09-12", "pull")], "2026-09-15");
    expect(days).toEqual([
      { day: "2026-09-12", value: 10 },
      { day: "2026-09-13", value: 0 },
      { day: "2026-09-14", value: 10 },
      { day: "2026-09-15", value: 0 },
    ]);
  });

  it("las horas del mes se leen de un vistazo", () => {
    expect(hours(45 * 60)).toBe("45 min");
    expect(hours(21 * 3600 + 20 * 60)).toBe("21 h");
  });

  it("una semana por debajo solo cuenta si ya pasó y es posterior al primer entreno", () => {
    const sessions = [session("2026-09-08", "push"), session("2026-09-01", "push")];
    expect(weekBelow("2026-09-07", sessions, 3, "2026-09-16")).toBe(true);
    expect(weekBelow("2026-08-24", sessions, 3, "2026-09-16")).toBe(false);
    expect(weekBelow("2026-09-14", sessions, 3, "2026-09-16")).toBe(false);
    expect(weekBelow("2026-09-07", sessions, 1, "2026-09-16")).toBe(false);
  });
});

describe("las actividades en el calendario", () => {
  it("marcan su día, detrás del entreno si ese día también lo hubo", () => {
    const climbing = { id: "a1", activity_type_id: "t", name: "Escalada", day: "2026-09-14", start_time: "18:30:00", duration_seconds: 5400, notes: null };
    const marks = marksOf([session("2026-09-14", "push")], [climbing, { ...climbing, id: "a2", day: "2026-09-12" }]);
    expect(marks["2026-09-14"]?.map((mark) => mark.kind)).toEqual(["push", "activity"]);
    expect(marks["2026-09-12"]).toEqual([{ kind: "activity", label: "Escalada" }]);
  });
});

describe("la hora de una actividad", () => {
  it("se propone la de ahora al cuarto de hora de antes, y se enseña con la duración", () => {
    expect(nowQuarter(new Date(2026, 8, 29, 18, 44))).toBe("18:30");
    expect(nowQuarter(new Date(2026, 8, 29, 7, 5))).toBe("07:00");
    expect(
      describeActivity({ id: "a", activity_type_id: "t", name: "Natación", day: "2026-09-29", start_time: "19:00:00", duration_seconds: 3600, notes: null }),
    ).toBe("19:00 · 1 h 00 min");
  });
});
