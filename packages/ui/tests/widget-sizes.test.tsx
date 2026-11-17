import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  SIZES,
  Widget,
  WidgetCalendar,
  WidgetHeatmap,
  WidgetKpiDelta,
  WidgetList,
  WidgetProgress,
  WidgetStats,
  WidgetUpNext,
  type WidgetSize,
  dayLabel,
  fitsUncertaintyLine,
  layoutOf,
} from "../src/index";

const card = (size: WidgetSize, body: React.ReactNode) =>
  renderToStaticMarkup(
    <Widget title="Test" hue={1} size={size} shape="list" state="ready">
      {body}
    </Widget>,
  );

describe("the shape of each size (ADR-0086)", () => {
  it("strips are one row tall", () => {
    expect(layoutOf("2x1")).toBe("strip");
    expect(layoutOf("4x1")).toBe("strip");
  });

  it("each size has its shape, and an unknown one falls back to a 2x2", () => {
    expect(SIZES.map(layoutOf)).toEqual([
      "tiny",
      "strip",
      "strip",
      "narrow",
      "square",
      "tall",
      "wide",
      "large",
      "large",
]);
    expect(layoutOf("9x9")).toBe("square");
  });

  it("the card says its shape, which is what the CSS reads", () => {
    expect(card("4x1", null)).toContain('data-layout="strip"');
  });

  it("a strip has no height for the line that quantifies doubt", () => {
    expect(fitsUncertaintyLine("4x1")).toBe(false);
    expect(fitsUncertaintyLine("4x2")).toBe(true);
  });
});

const ROWS = [
  { label: "Pasar la ITV del coche", value: "hace 3 días", tone: "warning" as const },
  { label: "Llamar al fontanero", value: "10:00" },
  { label: "Devolver el libro", value: "today" },
];

describe("a list by the space available", () => {
  it("in a half card, with a long value, each row takes two lines instead of being cut", () => {
    expect(card("2x2", <WidgetList rows={ROWS} />)).toContain("data-stacked");
    expect(card("2x2", <WidgetList rows={ROWS.slice(1)} />)).not.toContain("data-stacked");
  });

  it("in a 1x1 it says how many there are and warns if one needs something", () => {
    const html = card("1x1", <WidgetList rows={ROWS} />);
    expect(html).toContain(">3<");
    expect(html).toContain('data-tone="warning"');
  });

  it("in a strip, the first and how many are left", () => {
    const html = card("4x1", <WidgetList rows={ROWS} />);
    expect(html).toContain("Pasar la ITV del coche");
    expect(html).not.toContain("Llamar al fontanero");
    expect(html).toContain("+2");
  });

  it("in a wide one with many rows, two columns", () => {
    const many = Array.from({ length: 6 }, (_, index) => ({ label: `Fila ${index}`, value: "1" }));
    expect(card("4x2", <WidgetList rows={many} />)).toContain("data-columns");
  });
});

const NOW = new Date(2026, 8, 29, 10, 0);
const at = (days: number, hour: number) => new Date(2026, 8, 29 + days, hour, 0);

describe("the next thing by the space available", () => {
  const events = [
    { at: at(0, 12), title: "Dentista" },
    { at: at(0, 18), title: "Cena" },
    { at: at(1, 10), title: "Taller" },
  ];

  it("tall, it groups by day and says the day once", () => {
    const html = card("2x4", <WidgetUpNext events={events} />);
    expect(html.match(/upnext-day-label/g)).toHaveLength(2);
  });

  it("in a strip it is a single line", () => {
    const html = card("4x1", <WidgetUpNext events={events} />);
    expect(html).toContain("Dentista");
    expect(html).not.toContain("Cena");
  });

  it("the day is said as one says it", () => {
    expect(dayLabel(at(0, 9), NOW)).toBe("Today");
    expect(dayLabel(at(1, 9), NOW)).toBe("Tomorrow");
    expect(dayLabel(at(2, 9), NOW)).toBe("Thursday");
  });
});

describe("the other type sizes at their new values", () => {
  it("a change with a series draws its shape", () => {
    const html = card(
      "4x2",
      <WidgetKpiDelta value={74} previous={75} series={[76, 75, 74]} />,
    );
    expect(html).toContain("sparkline");
  });

  it("the bar marks where one should be", () => {
    const html = card("2x2", <WidgetProgress value={600} target={900} expected={450} />);
    expect(html).toContain("progress-pace");
    expect(html).toContain("--pace:0.5");
  });

  it("the consistency map in a strip is the last days in a row", () => {
    const html = card("4x1", <WidgetHeatmap values={Array.from({ length: 100 }, () => 1)} />);
    expect(html.match(/heatmap-cell/g)).toHaveLength(21);
  });

  it("the calendar in a strip is the week, and in a 1x1 today", () => {
    expect(card("4x1", <WidgetCalendar marked={[1]} />).match(/calendar-week-day/g)).toHaveLength(7);
    expect(card("1x1", <WidgetCalendar marked={[1]} />)).toContain("calendar-today-date");
  });

  it("the month with entries draws nothing in the days: it tells them in the side column", () => {
    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    const entries = [{ title: "Dentista", start: today, allDay: true, tone: 2 }];
    for (const size of ["4x2", "4x4", "2x4"] as WidgetSize[]) {
      const html = card(size, <WidgetCalendar entries={entries} />);
      expect(html).toContain("month-split");
      expect(html).not.toContain("entry-chip");
      expect(html).not.toContain("week-dot");
      expect(html).toContain("Dentista");
      expect(html).toMatch(/class="month-cell"[^>]*data-today="true"/);
    }
    const square = card("2x2", <WidgetCalendar entries={entries} />);
    expect(square).not.toContain("Dentista");
    expect(square).not.toContain("week-dot");
  });

  it("the figures in a 1x1 keep the first one", () => {
    const html = card(
      "1x1",
      <WidgetStats items={[{ label: "A", value: 1 }, { label: "B", value: 2 }]} />,
    );
    expect(html).toContain('data-count="1"');
  });
});

describe("a bar with a ceiling (ADR-0086)", () => {
  it("going over a budget is not meeting it: it says how much over", () => {
    const html = card("2x2", <WidgetProgress value={1000} target={900} unit="€" goodWhen="down" />);
    expect(html).not.toContain("Goal met");
    expect(html).toContain('data-standing="over"');
    expect(html).toContain("100 € over");
  });

  it("being ahead of pace is flagged before overshooting", () => {
    const html = card(
      "2x2",
      <WidgetProgress value={600} target={900} expected={450} goodWhen="down" />,
    );
    expect(html).toContain('data-standing="ahead"');
  });
});
