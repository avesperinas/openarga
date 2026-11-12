import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { type CalendarEvent, MiniMonth, MonthGrid, TimeGrid, dayRange } from "../src/index";

const NOW = new Date(2026, 8, 30, 11, 20);
const events: CalendarEvent[] = [
  { id: "a", title: "Revisión", start: new Date(2026, 8, 30, 10, 0), end: new Date(2026, 8, 30, 12, 0), tone: 1, subtitle: "Sala 2" },
  { id: "b", title: "Café", start: new Date(2026, 8, 30, 11, 0), end: new Date(2026, 8, 30, 11, 20), tone: 7 },
  { id: "c", title: "Ayer", start: new Date(2026, 8, 29, 9, 0), end: new Date(2026, 8, 29, 10, 0), tone: 2, subscribed: true },
  { id: "d", title: "Fiesta", start: "2026-10-01", end: "2026-10-02", allDay: true, tone: 4, recurring: true },
  { id: "e", title: "Tutoría", start: new Date(2026, 9, 2, 9, 0), end: new Date(2026, 9, 2, 10, 0), tone: 5, status: "cancelled", readOnly: true },
];
const render = (node: React.ReactElement) => renderToStaticMarkup(node);

describe("TimeGrid", () => {
  const html = render(<TimeGrid label="Semana" days={dayRange("2026-09-28", 7)} events={events} now={NOW} weekNumber onEventChange={() => {}} />);

  it("pinta cada evento con su tono, su hora y lo que dice el lector de pantalla", () => {
    expect(html).toContain('data-tone="1"');
    expect(html).toContain("10:00 – 12:00");
    expect(html).toContain('aria-label="Revisión. miércoles, 30 de septiembre, 10:00 – 12:00. Sala 2"');
  });

  it("uno corto va en una línea, y uno que empieza cuando otro ya lleva un rato va encima", () => {
    expect(html).toMatch(/data-event-id="b"[^>]*data-one-line="true"[^>]*data-nested="true"/);
  });

  it("lo pasado se atenúa y lo suscrito se distingue", () => {
    expect(html).toMatch(/data-event-id="c"[^>]*data-subscribed="true"[^>]*data-past="true"/);
  });

  it("lo de todo el día va a la franja, y lo cancelado lo dice", () => {
    expect(html).toMatch(/class="tg-bar"[^>]*data-tone="4"/);
    expect(html).toContain("Tutoría. viernes, 2 de octubre, 09:00 – 10:00, cancelado");
  });

  it("la línea de ahora cae en hoy, a su minuto, y la semana dice su número", () => {
    expect(html).toContain('class="tg-now" style="--at:680"');
    expect(html).toContain("S40");
    expect(html.match(/data-today="true"/g)).toHaveLength(2);
  });

  it("solo lo editable lleva el asa para estirar", () => {
    expect(html.match(/data-handle/g)).toHaveLength(3);
  });

  it("un horario sin fechas no marca hoy ni pinta la línea", () => {
    const plain = render(<TimeGrid label="Horario" days={dayRange("2026-09-28", 5)} events={[]} now={NOW} showDates={false} />);
    expect(plain).not.toContain("tg-now");
    expect(plain).not.toContain("tg-day-number");
  });
});

describe("El fondo", () => {
  const frame: CalendarEvent[] = [
    { id: "work", title: "Jornada", start: new Date(2026, 8, 30, 8, 0), end: new Date(2026, 8, 30, 17, 0), tone: 2, background: true },
    { id: "trip", title: "Lisboa", start: "2026-10-01", end: "2026-10-03", allDay: true, tone: 6, background: true },
    { id: "meet", title: "Revisión", start: new Date(2026, 8, 30, 10, 0), end: new Date(2026, 8, 30, 11, 0), tone: 1 },
  ];
  const html = render(<TimeGrid label="Semana" days={dayRange("2026-09-28", 7)} events={frame} now={NOW} onEventChange={() => {}} />);

  it("tiñe su tramo y lleva su nombre, que no ocupa el hueco de un evento", () => {
    expect(html).toMatch(/class="tg-backdrop" data-tone="2" style="--top:480;--bottom:1020"/);
    expect(html).toContain('aria-label="Jornada, de fondo. miércoles, 30 de septiembre, 08:00 – 17:00"');
    expect(html).not.toMatch(/class="tg-event"[^>]*data-event-id="work"/);
  });

  it("se mueve por su nombre y se estira por su borde de abajo, como un evento", () => {
    expect(html).toMatch(/class="tg-backdrop-label"[^>]*data-event-id="work"[^>]*data-editable="true"/);
    expect(html).toMatch(/class="tg-backdrop-handle" data-event-id="work" data-handle="true"/);
  });

  it("lo que no se puede cambiar desde aquí, ni se mueve ni se estira", () => {
    const locked = frame.map((event) => ({ ...event, readOnly: true }));
    const grid = render(<TimeGrid label="Semana" days={dayRange("2026-09-28", 7)} events={locked} now={NOW} onEventChange={() => {}} />);
    expect(grid).not.toContain("data-editable");
    expect(grid).not.toContain("tg-backdrop-handle");
  });

  it("el evento de encima ocupa todo el ancho, como si el fondo no estuviera", () => {
    expect(html).toMatch(/data-event-id="meet"[^>]*style="--top:600;--bottom:660;--left:0;--width:1/);
  });

  it("uno de días enteros tiñe cada día que dura y lleva el nombre en la franja", () => {
    expect(html.match(/class="tg-backdrop" data-tone="6"/g)).toHaveLength(2);
    expect(html.match(/class="tg-backdrop" data-whole="true" data-tone="6"/g)).toHaveLength(2);
    expect(html).toMatch(/class="tg-bar"[^>]*data-tone="6"[^>]*data-background="true"/);
  });

  it("su nombre no va debajo de un evento: baja al primer hueco", () => {
    const early = [...frame, { id: "early", title: "Standup", start: new Date(2026, 8, 30, 8, 0), end: new Date(2026, 8, 30, 8, 30), tone: 1 as const }];
    const grid = render(<TimeGrid label="Semana" days={dayRange("2026-09-28", 7)} events={early} now={NOW} />);
    expect(grid).toMatch(/class="tg-backdrop-label"[^>]*style="--label-at:30"/);
  });

  it("lo pasado se atenúa sin dejar ver el fondo", () => {
    expect(html).toMatch(/data-event-id="meet"[^>]*data-past="true"/);
  });

  it("en el mes, lo de días enteros tiñe y lo que tiene hora no sale", () => {
    const month = render(<MonthGrid month="2026-09-01" events={frame} now={NOW} />);
    expect(month).toMatch(/class="mg-backdrop" data-tone="6" style="--column:3;--span:2"/);
    expect(month).not.toContain("Jornada");
    expect(month).toContain("Revisión");
  });
});

describe("MonthGrid y MiniMonth", () => {
  it("el mes son seis semanas y marca hoy", () => {
    const html = render(<MonthGrid month="2026-09-01" events={events} now={NOW} />);
    expect(html.match(/class="mg-week"/g)).toHaveLength(6);
    expect(html).toMatch(/data-today="true"/);
    expect(html).toContain("1 sept");
  });

  it("el mes puede empezar en cualquier semana y atenúa lo que no es de su mes", () => {
    const html = render(<MonthGrid month="2026-10-01" from="2026-09-14" events={events} now={NOW} onScroll={() => {}} />);
    expect(html.match(/class="mg-week"/g)).toHaveLength(6);
    expect(html).toMatch(/aria-label="lunes, 14 de septiembre"/);
    expect(html).toMatch(/aria-label="domingo, 25 de octubre"/);
    expect(html).not.toMatch(/aria-label="lunes, 26 de octubre"/);
    expect(html).toContain('data-scroll="true"');
    expect(html.match(/data-outside="true"/g)).toHaveLength(17);
  });

  it("el mes pequeño marca la banda que se está viendo", () => {
    const html = render(
      <MiniMonth month="2026-09-01" range={dayRange("2026-09-28", 7)} now={NOW} onSelect={() => {}} onMonthChange={() => {}} />,
    );
    expect(html.match(/data-in-range="true"/g)).toHaveLength(7);
    expect(html.match(/data-range-start="true"/g)).toHaveLength(1);
  });
});
