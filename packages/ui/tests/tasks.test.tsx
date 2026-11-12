import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { Widget, WidgetTasks, type WidgetSize, dueLabel } from "../src/index";

const NOW = new Date(2026, 8, 29, 10, 0);
const TASKS = [
  { id: "a", title: "Enviar la factura", due: "2026-09-27", overdue: true, hue: 4, detail: "Trabajo" },
  { id: "b", title: "Llamar al fontanero", due: "2026-09-29T18:00:00", hue: 3 },
  { id: "c", title: "Regar", due: "2026-09-29" },
  { id: "d", title: "Pan", done: true },
];

const card = (size: WidgetSize, onToggle?: (id: string, done: boolean) => Promise<boolean>) =>
  renderToStaticMarkup(
    <Widget title="Para hoy" hue={3} size={size} shape="list" state="ready">
      <WidgetTasks tasks={TASKS} count={5} now={NOW} onToggle={onToggle} />
    </Widget>,
  );

describe("cuándo toca una tarea", () => {
  it("lo vencido cuenta los días, lo de hoy dice la hora si la tiene", () => {
    expect(dueLabel("2026-09-27", NOW)).toBe("Hace 2 días");
    expect(dueLabel("2026-09-28", NOW)).toBe("Ayer");
    expect(dueLabel("2026-09-29", NOW)).toBe("Hoy");
    expect(dueLabel("2026-09-29T18:00:00", NOW)).toBe("18:00");
    expect(dueLabel("2026-09-30", NOW)).toBe("Mañana");
  });
});

describe("la lista de tareas (ADR-0086 §4)", () => {
  it("con quien actúa, la casilla es un botón que dice qué hace", () => {
    const html = card("2x2", async () => true);
    expect(html).toContain('<button type="button" class="task-check"');
    expect(html).toContain('aria-label="Marcar hecha Enviar la factura"');
  });

  it("sin quien actúa, la casilla no es un botón y la tarjeta abre la app", () => {
    expect(card("2x2")).not.toContain("<button");
  });

  it("lo hecho sale tachado y se puede desmarcar", () => {
    const html = card("4x4", async () => true);
    expect(html).toContain('aria-label="Desmarcar Pan"');
  });

  it("lo vencido va avisado", () => {
    expect(card("2x2")).toContain("data-overdue");
  });

  it("en un 1x1, cuántas quedan y cuántas vencidas", () => {
    const html = card("1x1");
    expect(html).toContain(">5<");
    expect(html).toContain("1 vencida<");
  });

  it("en una tira, la primera sin hacer y cuántas más", () => {
    const html = card("4x1", async () => true);
    expect(html).toContain("Enviar la factura");
    expect(html).not.toContain("Regar");
    expect(html).toContain("+4");
  });

  it("en un 4x4 se agrupa: vencidas, hoy y lo demás", () => {
    const html = card("4x4");
    expect(html).toContain("Vencidas");
    expect(html).toContain("Hoy");
  });
});
