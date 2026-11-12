import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  Widget,
  WidgetAgenda,
  WidgetCalendar,
  WidgetWeek,
  type WidgetSize,
  onDay,
  parseEntries,
  untilLabel,
} from "../src/index";

const NOW = new Date(2026, 8, 29, 10, 0);
const at = (days: number, hour: number, minute = 0) =>
  new Date(2026, 8, 29 + days, hour, minute).toISOString();

const ENTRIES = [
  { start: "2026-09-29", allDay: true, title: "Cumpleaños", tone: 5 },
  { start: at(0, 9), end: at(0, 9, 45), title: "Desayuno", tone: 1 },
  { start: at(0, 10, 25), end: at(0, 11), title: "Dentista", detail: "Sur", tone: 4 },
  { start: at(0, 19), end: at(0, 20), title: "Pádel", tone: 2 },
  { start: at(1, 8), end: at(1, 9), title: "Banco", tone: 3 },
  { start: "2026-10-03", end: "2026-10-05", allDay: true, title: "Lisboa", tone: 8 },
];

const card = (size: WidgetSize, body: React.ReactNode) =>
  renderToStaticMarkup(
    <Widget title="Hoy" hue={6} size={size} shape="list" state="ready">
      {body}
    </Widget>,
  );

describe("las entradas del calendario", () => {
  it("una fecha sola es un día local, no medianoche en UTC", () => {
    const [birthday] = parseEntries([{ start: "2026-09-29", title: "Cumpleaños" }]);
    expect(birthday!.from.getDate()).toBe(29);
    expect(birthday!.allDay).toBe(true);
  });

  it("algo de varios días está en cada uno, y el día de fin no cuenta", () => {
    const all = parseEntries(ENTRIES);
    const titles = (day: number) => onDay(all, new Date(2026, 9, day)).map((e) => e.title);
    expect(titles(3)).toContain("Lisboa");
    expect(titles(4)).toContain("Lisboa");
    expect(titles(5)).not.toContain("Lisboa");
  });

  it("lo de todo el día va delante de lo que tiene hora", () => {
    expect(onDay(parseEntries(ENTRIES), NOW)[0]!.title).toBe("Cumpleaños");
  });

  it("cuánto falta se dice como se dice", () => {
    const soon = new Date(2026, 8, 29, 10, 25);
    expect(untilLabel(soon, new Date(2026, 8, 29, 11), NOW)).toBe("En 25 min");
    expect(untilLabel(new Date(2026, 8, 29, 13), new Date(2026, 8, 29, 14), NOW)).toBe("En 3 h");
    expect(untilLabel(new Date(2026, 8, 29, 9), new Date(2026, 8, 29, 11), NOW)).toBe("Ahora");
  });
});

describe("hoy según el hueco", () => {
  it("en un 1x1 es cuánto falta para lo siguiente con hora", () => {
    const html = card("1x1", <WidgetAgenda entries={ENTRIES} now={NOW} />);
    expect(html).toContain("En 25 min");
    expect(html).toContain("Dentista");
  });

  it("en una tira dice además cuántas cosas quedan hoy", () => {
    expect(card("4x1", <WidgetAgenda entries={ENTRIES} now={NOW} />)).toContain("+2 hoy");
  });

  it("en un 2x2 no enseña lo que ya pasó", () => {
    const html = card("2x2", <WidgetAgenda entries={ENTRIES} now={NOW} />);
    expect(html).not.toContain("Desayuno");
    expect(html).toContain("Pádel");
  });

  it("en un 4x2 hoy y mañana lado a lado", () => {
    const html = card("4x2", <WidgetAgenda entries={ENTRIES} now={NOW} />);
    expect(html).toContain("Banco");
    expect(html).toContain("Mañana");
  });

  it("en un 4x4 hoy es una línea de tiempo con la raya de ahora", () => {
    const html = card("4x4", <WidgetAgenda entries={ENTRIES} now={NOW} />);
    expect(html).toContain("timeline-now");
    expect(html.match(/timeline-block/g)).toHaveLength(3);
  });

  it("cada cosa lleva el tono de su capa", () => {
    expect(card("2x2", <WidgetAgenda entries={ENTRIES} now={NOW} />)).toContain('data-tone="4"');
  });
});

describe("la semana y el mes", () => {
  it("la semana empieza hoy y tiene siete días", () => {
    const html = card("4x2", <WidgetWeek entries={ENTRIES} now={NOW} />);
    expect(html.match(/class="week-day"/g)).toHaveLength(7);
    expect(html).toContain("Lisboa");
  });

  it("en un 1x1, cuántas cosas hay en siete días", () => {
    expect(card("1x1", <WidgetWeek entries={ENTRIES} now={NOW} />)).toContain(">7<");
  });

  it("el mes grande no escribe nada en los días: lo de hoy va en la columna de al lado", () => {
    const html = card(
      "4x4",
      <WidgetCalendar month={new Date(2026, 8, 1)} entries={ENTRIES} />,
    );
    const grid = html.slice(html.indexOf("month-entries"), html.indexOf("agenda-day"));
    expect(grid).not.toContain("Banco");
    expect(grid).not.toContain("+3");
    expect(html).toContain("agenda-day");
  });

  it("en un 1x2 el mes es hoy y la semana, de arriba abajo", () => {
    expect(card("1x2", <WidgetCalendar entries={ENTRIES} />)).toContain("data-vertical");
  });
});
