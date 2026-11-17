import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { type CalendarEvent, MiniMonth, MonthGrid, TimeGrid, dayRange } from "../src/index";

const NOW = new Date(2026, 8, 30, 11, 20);
const events: CalendarEvent[] = [
  { id: "a", title: "Review", start: new Date(2026, 8, 30, 10, 0), end: new Date(2026, 8, 30, 12, 0), tone: 1, subtitle: "Room 2" },
  { id: "b", title: "Café", start: new Date(2026, 8, 30, 11, 0), end: new Date(2026, 8, 30, 11, 20), tone: 7 },
  { id: "c", title: "Yesterday", start: new Date(2026, 8, 29, 9, 0), end: new Date(2026, 8, 29, 10, 0), tone: 2, subscribed: true },
  { id: "d", title: "Fiesta", start: "2026-10-01", end: "2026-10-02", allDay: true, tone: 4, recurring: true },
  { id: "e", title: "Tutorial", start: new Date(2026, 9, 2, 9, 0), end: new Date(2026, 9, 2, 10, 0), tone: 5, status: "cancelled", readOnly: true },
];
const render = (node: React.ReactElement) => renderToStaticMarkup(node);

describe("TimeGrid", () => {
  const html = render(<TimeGrid label="Week" days={dayRange("2026-09-28", 7)} events={events} now={NOW} weekNumber onEventChange={() => {}} />);

  it("renders each event with its tone, its time and what the screen reader says", () => {
    expect(html).toContain('data-tone="1"');
    expect(html).toContain("10:00 – 12:00");
    expect(html).toContain('aria-label="Review. Wednesday 30 September, 10:00 – 12:00. Room 2"');
  });

  it("a short one goes on one line, and one starting while another is running goes on top", () => {
    expect(html).toMatch(/data-event-id="b"[^>]*data-one-line="true"[^>]*data-nested="true"/);
  });

  it("past items dim and subscribed ones stand out", () => {
    expect(html).toMatch(/data-event-id="c"[^>]*data-subscribed="true"[^>]*data-past="true"/);
  });

  it("all-day items go to the strip, and cancelled ones say so", () => {
    expect(html).toMatch(/class="tg-bar"[^>]*data-tone="4"/);
    expect(html).toContain("Tutorial. Friday 2 October, 09:00 – 10:00, cancelled");
  });

  it("the now line falls on today, at its minute, and the week says its number", () => {
    expect(html).toContain('class="tg-now" style="--at:680"');
    expect(html).toContain("S40");
    expect(html.match(/data-today="true"/g)).toHaveLength(2);
  });

  it("only editable items carry the stretch handle", () => {
    expect(html.match(/data-handle/g)).toHaveLength(3);
  });

  it("a schedule without dates neither marks today nor draws the line", () => {
    const plain = render(<TimeGrid label="Horario" days={dayRange("2026-09-28", 5)} events={[]} now={NOW} showDates={false} />);
    expect(plain).not.toContain("tg-now");
    expect(plain).not.toContain("tg-day-number");
  });
});

describe("El fondo", () => {
  const frame: CalendarEvent[] = [
    { id: "work", title: "Workday", start: new Date(2026, 8, 30, 8, 0), end: new Date(2026, 8, 30, 17, 0), tone: 2, background: true },
    { id: "trip", title: "Lisboa", start: "2026-10-01", end: "2026-10-03", allDay: true, tone: 6, background: true },
    { id: "meet", title: "Review", start: new Date(2026, 8, 30, 10, 0), end: new Date(2026, 8, 30, 11, 0), tone: 1 },
  ];
  const html = render(<TimeGrid label="Week" days={dayRange("2026-09-28", 7)} events={frame} now={NOW} onEventChange={() => {}} />);

  it("tints its span and carries its name, which does not take an event's slot", () => {
    expect(html).toMatch(/class="tg-backdrop" data-tone="2" style="--top:480;--bottom:1020"/);
    expect(html).toContain('aria-label="Workday, in the background. Wednesday 30 September, 08:00 – 17:00"');
    expect(html).not.toMatch(/class="tg-event"[^>]*data-event-id="work"/);
  });

  it("moves by its name and stretches by its bottom edge, like an event", () => {
    expect(html).toMatch(/class="tg-backdrop-label"[^>]*data-event-id="work"[^>]*data-editable="true"/);
    expect(html).toMatch(/class="tg-backdrop-handle" data-event-id="work" data-handle="true"/);
  });

  it("what cannot be changed from here neither moves nor stretches", () => {
    const locked = frame.map((event) => ({ ...event, readOnly: true }));
    const grid = render(<TimeGrid label="Week" days={dayRange("2026-09-28", 7)} events={locked} now={NOW} onEventChange={() => {}} />);
    expect(grid).not.toContain("data-editable");
    expect(grid).not.toContain("tg-backdrop-handle");
  });

  it("the event on top takes the full width, as if the background were not there", () => {
    expect(html).toMatch(/data-event-id="meet"[^>]*style="--top:600;--bottom:660;--left:0;--width:1/);
  });

  it("an all-day one tints each day it lasts and carries its name in the strip", () => {
    expect(html.match(/class="tg-backdrop" data-tone="6"/g)).toHaveLength(2);
    expect(html.match(/class="tg-backdrop" data-whole="true" data-tone="6"/g)).toHaveLength(2);
    expect(html).toMatch(/class="tg-bar"[^>]*data-tone="6"[^>]*data-background="true"/);
  });

  it("its name does not go under an event: it drops to the first gap", () => {
    const early = [...frame, { id: "early", title: "Standup", start: new Date(2026, 8, 30, 8, 0), end: new Date(2026, 8, 30, 8, 30), tone: 1 as const }];
    const grid = render(<TimeGrid label="Week" days={dayRange("2026-09-28", 7)} events={early} now={NOW} />);
    expect(grid).toMatch(/class="tg-backdrop-label"[^>]*style="--label-at:30"/);
  });

  it("past items dim without revealing the background", () => {
    expect(html).toMatch(/data-event-id="meet"[^>]*data-past="true"/);
  });

  it("in the month, all-day items tint and timed ones do not show", () => {
    const month = render(<MonthGrid month="2026-09-01" events={frame} now={NOW} />);
    expect(month).toMatch(/class="mg-backdrop" data-tone="6" style="--column:3;--span:2"/);
    expect(month).not.toContain("Workday");
    expect(month).toContain("Review");
  });
});

describe("MonthGrid and MiniMonth", () => {
  it("the month is six weeks and marks today", () => {
    const html = render(<MonthGrid month="2026-09-01" events={events} now={NOW} />);
    expect(html.match(/class="mg-week"/g)).toHaveLength(6);
    expect(html).toMatch(/data-today="true"/);
    expect(html).toContain("1 Sept");
  });

  it("the month can start on any week and dims what is not in its month", () => {
    const html = render(<MonthGrid month="2026-10-01" from="2026-09-14" events={events} now={NOW} onScroll={() => {}} />);
    expect(html.match(/class="mg-week"/g)).toHaveLength(6);
    expect(html).toMatch(/aria-label="Monday 14 September"/);
    expect(html).toMatch(/aria-label="Sunday 25 October"/);
    expect(html).not.toMatch(/aria-label="Monday 26 October"/);
    expect(html).toContain('data-scroll="true"');
    expect(html.match(/data-outside="true"/g)).toHaveLength(17);
  });

  it("the small month marks the band being viewed", () => {
    const html = render(
      <MiniMonth month="2026-09-01" range={dayRange("2026-09-28", 7)} now={NOW} onSelect={() => {}} onMonthChange={() => {}} />,
    );
    expect(html.match(/data-in-range="true"/g)).toHaveLength(7);
    expect(html.match(/data-range-start="true"/g)).toHaveLength(1);
  });
});
