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

describe("the task list (ADR-0086 §4)", () => {
  it("with an actor, the checkbox is a button that says what it does", () => {
    const html = card("2x2", async () => true);
    expect(html).toContain('<button type="button" class="task-check"');
    expect(html).toContain('aria-label="Mark Send the invoice done"');
  });

  it("without an actor, the checkbox is not a button and the card opens the app", () => {
    expect(card("2x2")).not.toContain("<button");
  });

  it("done items show struck through and can be unticked", () => {
    const html = card("4x4", async () => true);
    expect(html).toContain('aria-label="Unmark Bread"');
  });

  it("overdue items are flagged", () => {
    expect(card("2x2")).toContain("data-overdue");
  });

  it("in a 1x1, how many are left and how many overdue", () => {
    const html = card("1x1");
    expect(html).toContain(">5<");
    expect(html).toContain("1 overdue<");
  });

  it("in a strip, the first undone and how many more", () => {
    const html = card("4x1", async () => true);
    expect(html).toContain("Send the invoice");
    expect(html).not.toContain("Water the plants");
    expect(html).toContain("+4");
  });

  it("in a 4x4 it groups: overdue, today and the rest", () => {
    const html = card("4x4");
    expect(html).toContain("Overdue");
    expect(html).toContain("Today");
  });
});
