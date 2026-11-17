import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { YearCalendar, monthStarts, yearCells, yearLevel } from "../src/index";

describe("the year", () => {
  it("they are 53 weeks ending on the last day, with Monday on top", () => {
    const cells = yearCells([], "2026-09-25");

    expect(cells.at(-1)).toMatchObject({ day: "2026-09-25", week: 52, weekday: 4 });
    expect(cells[0]).toMatchObject({ week: 0, weekday: 0 });
    expect(new Date(`${cells[0]!.day}T12:00:00Z`).getUTCDay()).toBe(1);
    expect(cells).toHaveLength(52 * 7 + 5);
  });

  it("pone cada mes donde empieza", () => {
    const months = monthStarts(yearCells([], "2026-09-25"));

    expect(months.at(-1)).toMatchObject({ label: "sep" });
    expect(months.map((one) => one.label)).toContain("ene");
  });

  it("no data is not zero, and without a target the steps spread up to the top", () => {
    expect(yearLevel(undefined, 8000)).toBe("none");
    expect(yearLevel(0, 8000)).toBe(0);
    expect(yearLevel(1500, 8000)).toBe(1);
    expect(yearLevel(4000, 8000)).toBe(2);
    expect(yearLevel(6500, 8000)).toBe(4);
    expect(yearLevel(8000, 8000)).toBe(4);
  });

  it("with a target, the fourth step is reaching it and getting close does not count", () => {
    expect(yearLevel(0, 10000, true)).toBe(0);
    expect(yearLevel(2000, 10000, true)).toBe(1);
    expect(yearLevel(5000, 10000, true)).toBe(2);
    expect(yearLevel(9999, 10000, true)).toBe(3);
    expect(yearLevel(10000, 10000, true)).toBe(4);
    expect(yearLevel(15000, 10000, true)).toBe(4);
  });

  it("renders the days with data, the gaps and the legend", () => {
    const html = renderToStaticMarkup(
      <YearCalendar
        label="Steps"
        days={[
          { day: "2026-09-24", value: 9000 },
          { day: "2026-09-25", value: 0 },
        ]}
        goal={8000}
      />,
    );

    expect(html).toContain('data-scale="goal"');
    expect(html).toContain('data-day="2026-09-24" data-level="4"');
    expect(html).toContain('data-day="2026-09-25" data-level="0"');
    expect(html).toContain('data-day="2026-09-23" data-level="none"');
    expect(html).toContain("2 of 369 days with data");
    expect(html).toContain("target");
  });

  it("without days it says so", () => {
    expect(renderToStaticMarkup(<YearCalendar label="Steps" days={[]} />)).toContain("No data this year");
  });
});
