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
    <Widget title="Today" hue={6} size={size} shape="list" state="ready">
      {body}
    </Widget>,
  );

describe("the calendar entries", () => {
  it("a bare date is a local day, not midnight UTC", () => {
    const [birthday] = parseEntries([{ start: "2026-09-29", title: "Cumpleaños" }]);
    expect(birthday!.from.getDate()).toBe(29);
    expect(birthday!.allDay).toBe(true);
  });

  it("a multi-day item is on each day, and the end day does not count", () => {
    const all = parseEntries(ENTRIES);
    const titles = (day: number) => onDay(all, new Date(2026, 9, day)).map((e) => e.title);
    expect(titles(3)).toContain("Lisboa");
    expect(titles(4)).toContain("Lisboa");
    expect(titles(5)).not.toContain("Lisboa");
  });

  it("all-day items go before timed ones", () => {
    expect(onDay(parseEntries(ENTRIES), NOW)[0]!.title).toBe("Cumpleaños");
  });

  it("how long is left is said as one says it", () => {
    const soon = new Date(2026, 8, 29, 10, 25);
    expect(untilLabel(soon, new Date(2026, 8, 29, 11), NOW)).toBe("In 25 min");
    expect(untilLabel(new Date(2026, 8, 29, 13), new Date(2026, 8, 29, 14), NOW)).toBe("In 3 h");
    expect(untilLabel(new Date(2026, 8, 29, 9), new Date(2026, 8, 29, 11), NOW)).toBe("Now");
  });
});

describe("today by the space available", () => {
  it("in a 1x1 it is how long until the next timed item", () => {
    const html = card("1x1", <WidgetAgenda entries={ENTRIES} now={NOW} />);
    expect(html).toContain("In 25 min");
    expect(html).toContain("Dentista");
  });

  it("in a strip it also says how many items are left today", () => {
    expect(card("4x1", <WidgetAgenda entries={ENTRIES} now={NOW} />)).toContain("+2 hoy");
  });

  it("in a 2x2 it does not show what is past", () => {
    const html = card("2x2", <WidgetAgenda entries={ENTRIES} now={NOW} />);
    expect(html).not.toContain("Desayuno");
    expect(html).toContain("Pádel");
  });

  it("in a 4x2 today and tomorrow side by side", () => {
    const html = card("4x2", <WidgetAgenda entries={ENTRIES} now={NOW} />);
    expect(html).toContain("Banco");
    expect(html).toContain("Tomorrow");
  });

  it("in a 4x4 today is a timeline with the now line", () => {
    const html = card("4x4", <WidgetAgenda entries={ENTRIES} now={NOW} />);
    expect(html).toContain("timeline-now");
    expect(html.match(/timeline-block/g)).toHaveLength(3);
  });

  it("each item carries its layer's tone", () => {
    expect(card("2x2", <WidgetAgenda entries={ENTRIES} now={NOW} />)).toContain('data-tone="4"');
  });
});

describe("the week and the month", () => {
  it("the week starts today and has seven days", () => {
    const html = card("4x2", <WidgetWeek entries={ENTRIES} now={NOW} />);
    expect(html.match(/class="week-day"/g)).toHaveLength(7);
    expect(html).toContain("Lisboa");
  });

  it("in a 1x1, how many items there are in seven days", () => {
    expect(card("1x1", <WidgetWeek entries={ENTRIES} now={NOW} />)).toContain(">7<");
  });

  it("the large month writes nothing in the days: today's items go in the side column", () => {
    const html = card(
      "4x4",
      <WidgetCalendar month={new Date(2026, 8, 1)} entries={ENTRIES} />,
    );
    const grid = html.slice(html.indexOf("month-entries"), html.indexOf("agenda-day"));
    expect(grid).not.toContain("Banco");
    expect(grid).not.toContain("+3");
    expect(html).toContain("agenda-day");
  });

  it("in a 1x2 the month is today and the week, top to bottom", () => {
    expect(card("1x2", <WidgetCalendar entries={ENTRIES} />)).toContain("data-vertical");
  });
});
