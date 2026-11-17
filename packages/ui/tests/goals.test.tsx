import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { GoalRow, WeekDots } from "../src/index";

const WEEK = ["met", "missed", "today", "future", "future", "future", "future"].map((state, index) => ({
  day: `2026-10-1${index}`,
  state: state as "met" | "missed" | "today" | "future",
}));

describe("the week in seven dots", () => {
  it("tells whoever cannot see the dots its state and marks each day", () => {
    const html = renderToStaticMarkup(<WeekDots days={WEEK} label="1 de 5 esta semana" />);
    expect(html).toContain('role="img" aria-label="1 de 5 esta semana"');
    const states = [...html.matchAll(/class="goal-week-day" data-state="([a-z]+)"/g)].map((found) => found[1]);
    expect(states).toEqual(["met", "missed", "today", "future", "future", "future", "future"]);
  });
});

describe("a goal's row", () => {
  it("today's box says whether it is checked", () => {
    const html = renderToStaticMarkup(
      <GoalRow title="Leer" week={WEEK} check={{ checked: true, label: "Hecho hoy: Leer", onClick: () => undefined }} />,
    );
    expect(html).toContain('aria-pressed="true" aria-label="Hecho hoy: Leer"');
  });

  it("the track does not overflow even past the target, and carries today's mark", () => {
    const html = renderToStaticMarkup(
      <GoalRow title="Ahorrar" tone="negative" progress={1.4} expected={0.5} figure="4.200 €" />,
    );
    expect(html).toContain("--filled:1;--pace:0.5");
    expect(html).toContain('class="goal-row-pace"');
    expect(html).toContain('data-tone="negative"');
  });

  it("without a track there is no mark", () => {
    const html = renderToStaticMarkup(<GoalRow title="El B2" status="Sin empezar" />);
    expect(html).not.toContain("goal-row-track");
    expect(html).toContain("Sin empezar");
  });
});
