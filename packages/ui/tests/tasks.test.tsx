import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { Widget, WidgetTasks, type WidgetSize, dueLabel } from "../src/index";

const NOW = new Date(2026, 8, 29, 10, 0);
const TASKS = [
  { id: "a", title: "Send the invoice", due: "2026-09-27", overdue: true, hue: 4, detail: "Work" },
  { id: "b", title: "Call the plumber", due: "2026-09-29T18:00:00", hue: 3 },
  { id: "c", title: "Water the plants", due: "2026-09-29" },
  { id: "d", title: "Bread", done: true },
];

const card = (size: WidgetSize, onToggle?: (id: string, done: boolean) => Promise<boolean>) =>
  renderToStaticMarkup(
    <Widget title="For today" hue={3} size={size} shape="list" state="ready">
      <WidgetTasks tasks={TASKS} count={5} now={NOW} onToggle={onToggle} />
    </Widget>,
  );

describe("when a task is due", () => {
  it("overdue counts the days, today shows the time if it has one", () => {
    expect(dueLabel("2026-09-27", NOW)).toBe("2 days ago");
    expect(dueLabel("2026-09-28", NOW)).toBe("Yesterday");
    expect(dueLabel("2026-09-29", NOW)).toBe("Today");
    expect(dueLabel("2026-09-29T18:00:00", NOW)).toBe("18:00");
    expect(dueLabel("2026-09-30", NOW)).toBe("Tomorrow");
  });
});

describe("la lista de tareas (ADR-0086 §4)", () => {
  it("con quien actúa, la casilla es un botón que dice qué hace", () => {
    const html = card("2x2", async () => true);
    expect(html).toContain('<button type="button" class="task-check"');
    expect(html).toContain('aria-label="Mark Send the invoice done"');
  });

  it("sin quien actúa, la casilla no es un botón y la tarjeta abre la app", () => {
    expect(card("2x2")).not.toContain("<button");
  });

  it("lo hecho sale tachado y se puede desmarcar", () => {
    const html = card("4x4", async () => true);
    expect(html).toContain('aria-label="Unmark Bread"');
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
    expect(html).toContain("Send the invoice");
    expect(html).not.toContain("Water the plants");
    expect(html).toContain("+4");
  });

  it("en un 4x4 se agrupa: vencidas, hoy y lo demás", () => {
    const html = card("4x4");
    expect(html).toContain("Overdue");
    expect(html).toContain("Today");
  });
});
