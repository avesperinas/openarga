import { describe, expect, it } from "vitest";

import {
  type CalendarEvent,
  addDays,
  atMinute,
  backdropsOf,
  dayRange,
  daysBetween,
  isoWeek,
  layoutBars,
  layoutDay,
  mondayOf,
  monthDays,
  segmentsOf,
  stripDays,
} from "../src/calendar-layout";

const at = (day: string, time: string) => new Date(`${day}T${time}:00`);
const timed = (id: string, day: string, from: string, to: string): CalendarEvent => ({
  id,
  title: id,
  start: at(day, from),
  end: at(day, to),
  tone: 1,
});
const place = (events: CalendarEvent[], day = "2026-09-28", cascadeAfter = 30) =>
  Object.fromEntries(
    layoutDay(segmentsOf(events, day), { cascadeAfter }).map((p) => [
      p.segment.event.id,
      { left: +p.left.toFixed(3), width: +p.width.toFixed(3), nested: p.nested, layer: p.layer },
    ]),
  );

describe("los días", () => {
  it("la semana empieza en lunes", () => {
    expect(mondayOf("2026-09-27")).toBe("2026-09-21");
    expect(mondayOf("2026-09-28")).toBe("2026-09-28");
  });

  it("cuenta días por el calendario también en el cambio de hora", () => {
    expect(daysBetween("2026-10-24", "2026-10-26")).toBe(2);
    expect(addDays("2026-10-25", 1)).toBe("2026-10-26");
    expect(dayRange("2026-03-28", 3)).toEqual(["2026-03-28", "2026-03-29", "2026-03-30"]);
  });

  it("la semana ISO", () => {
    expect(isoWeek("2026-01-01")).toBe(1);
    expect(isoWeek("2026-09-28")).toBe(40);
    expect(isoWeek("2027-01-01")).toBe(53);
  });

  it("un mes son siempre seis semanas desde el lunes", () => {
    const days = monthDays("2026-02-01");
    expect(days).toHaveLength(42);
    expect(days[0]).toBe("2026-01-26");
  });

  it("el minuto 1440 es la medianoche siguiente", () => {
    expect(atMinute("2026-09-28", 1440).getDate()).toBe(29);
  });
});

describe("los tramos de un día", () => {
  it("lo que cruza la medianoche se parte en dos", () => {
    const late: CalendarEvent = { id: "late", title: "Cena", start: at("2026-09-28", "22:00"), end: at("2026-09-29", "01:30"), tone: 2 };
    const [today] = segmentsOf([late], "2026-09-28");
    const [tomorrow] = segmentsOf([late], "2026-09-29");
    expect(today).toMatchObject({ top: 22 * 60, bottom: 1440, continuesAfter: true, continuesBefore: false });
    expect(tomorrow).toMatchObject({ top: 0, bottom: 90, continuesBefore: true, continuesAfter: false });
  });

  it("lo de todo el día y lo de 24 h o más va a la franja, no a la rejilla", () => {
    const allDay: CalendarEvent = { id: "a", title: "Fiesta", start: "2026-10-12", end: "2026-10-13", allDay: true, tone: 4 };
    const trip: CalendarEvent = { id: "t", title: "Viaje", start: at("2026-10-01", "09:00"), end: at("2026-10-03", "18:00"), tone: 6 };
    expect(segmentsOf([allDay, trip], "2026-10-12")).toEqual([]);
    expect(stripDays(allDay)).toEqual(["2026-10-12", "2026-10-12"]);
    expect(stripDays(trip)).toEqual(["2026-10-01", "2026-10-03"]);
  });
});

describe("los solapados", () => {
  it("uno solo ocupa todo el ancho", () => {
    expect(place([timed("a", "2026-09-28", "10:00", "11:00")])).toEqual({
      a: { left: 0, width: 1, nested: false, layer: 0 },
    });
  });

  it("dos que empiezan a la vez se reparten el ancho", () => {
    const out = place([timed("a", "2026-09-28", "10:00", "11:00"), timed("b", "2026-09-28", "10:00", "10:30")]);
    expect(out.a).toMatchObject({ left: 0, width: 0.5 });
    expect(out.b).toMatchObject({ left: 0.5, width: 0.5 });
  });

  it("uno que empieza cuando otro ya lleva un rato va encima y desplazado", () => {
    const out = place([timed("a", "2026-09-28", "10:00", "12:00"), timed("b", "2026-09-28", "11:00", "11:30")]);
    expect(out.a).toEqual({ left: 0, width: 1, nested: false, layer: 0 });
    expect(out.b).toMatchObject({ left: 0.14, width: 0.86, nested: true, layer: 1 });
  });

  it("tres a la vez van en tres columnas, y el que queda libre a su lado se estira", () => {
    const out = place([
      timed("a", "2026-09-28", "10:00", "11:00"),
      timed("b", "2026-09-28", "10:00", "10:20"),
      timed("c", "2026-09-28", "10:05", "10:20"),
      timed("d", "2026-09-28", "10:20", "11:00"),
    ]);
    expect(out.a).toMatchObject({ left: 0, width: 0.333 });
    expect(out.b).toMatchObject({ left: 0.333, width: 0.333 });
    expect(out.c).toMatchObject({ left: 0.667, width: 0.333 });
    expect(out.d).toMatchObject({ left: 0.333, width: 0.667 });
  });

  it("los que no se tocan no se reparten nada", () => {
    const out = place([timed("a", "2026-09-28", "09:00", "10:00"), timed("b", "2026-09-28", "10:00", "11:00")]);
    expect(out.a).toMatchObject({ width: 1 });
    expect(out.b).toMatchObject({ width: 1, nested: false });
  });

  it("un evento corto se reparte por lo que se ve, no por lo que dura", () => {
    const tiny = [timed("a", "2026-09-28", "10:00", "10:05"), timed("b", "2026-09-28", "10:05", "10:10")];
    expect(layoutDay(segmentsOf(tiny, "2026-09-28")).every((p) => p.width === 1)).toBe(true);
    const seen = layoutDay(segmentsOf(tiny, "2026-09-28"), { minimumMinutes: 20 });
    expect(seen.map((p) => p.width)).toEqual([0.5, 0.5]);
  });

  it("la cascada no deja a nadie más estrecho que un 40 %", () => {
    const stack = ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30"].map((from, i) =>
      timed(`e${i}`, "2026-09-28", from, "13:00"),
    );
    for (const placed of Object.values(place(stack))) {
      expect(placed.width).toBeGreaterThanOrEqual(0.4 - 1e-9);
    }
  });
});

describe("la franja", () => {
  const week = dayRange("2026-09-28", 7);
  const allDay = (id: string, from: string, to: string): CalendarEvent => ({ id, title: id, start: from, end: to, allDay: true, tone: 3 });

  it("lo largo arriba, y cada cosa en la primera fila donde cabe", () => {
    const { bars, rows, perDay } = layoutBars(
      [allDay("lunes", "2026-09-28", "2026-09-29"), allDay("viaje", "2026-09-28", "2026-10-02"), allDay("jueves", "2026-10-01", "2026-10-02")],
      week,
    );
    const byId = Object.fromEntries(bars.map((b) => [b.event.id, b]));
    expect(byId.viaje).toMatchObject({ column: 0, span: 4, row: 0 });
    expect(byId.lunes).toMatchObject({ column: 0, span: 1, row: 1 });
    expect(byId.jueves).toMatchObject({ column: 3, span: 1, row: 1 });
    expect(rows).toBe(2);
    expect(perDay).toEqual([2, 1, 1, 2, 0, 0, 0]);
  });

  it("lo que empieza antes o sigue después se corta en el borde", () => {
    const { bars } = layoutBars([allDay("vacaciones", "2026-09-20", "2026-10-10")], week);
    expect(bars[0]).toMatchObject({ column: 0, span: 7, continuesBefore: true, continuesAfter: true });
  });

  it("en el mes, lo que tiene hora va después de las barras", () => {
    const { bars } = layoutBars(
      [allDay("viaje", "2026-09-28", "2026-10-01")],
      week,
      [timed("cita", "2026-09-28", "09:00", "10:00")],
    );
    expect(bars.find((b) => b.event.id === "viaje")!.row).toBe(0);
    expect(bars.find((b) => b.event.id === "cita")!.row).toBe(1);
  });
});

describe("el nombre de un fondo", () => {
  const work: CalendarEvent = { id: "w", title: "Jornada", start: new Date(2026, 8, 28, 9, 0), end: new Date(2026, 8, 28, 17, 0), tone: 2, background: true };

  it("va arriba de su tramo si no hay nada", () => {
    expect(backdropsOf([work], "2026-09-28")[0]!.labelAt).toBe(540);
  });

  it("baja al primer hueco que no pisa un evento", () => {
    const [one] = backdropsOf([work], "2026-09-28", { labelMinutes: 20, busy: [[540, 555], [555, 600]] });
    expect(one!.labelAt).toBe(600);
  });

  it("sin hueco en su tramo, se tiñe sin nombre", () => {
    const [one] = backdropsOf([work], "2026-09-28", { labelMinutes: 20, busy: [[530, 1030]] });
    expect(one!.labelAt).toBeNull();
  });

  it("dos que empiezan a la vez no se escriben uno encima del otro", () => {
    const gym = { ...work, id: "g", title: "Gimnasio" };
    const [a, b] = backdropsOf([work, gym], "2026-09-28", { labelMinutes: 20 });
    expect([a!.labelAt, b!.labelAt]).toEqual([540, 560]);
  });
});
