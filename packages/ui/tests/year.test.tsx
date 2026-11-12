import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { YearCalendar, monthStarts, yearCells, yearLevel } from "../src/index";

describe("el año", () => {
  it("son 53 semanas que acaban en el último día, con el lunes arriba", () => {
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

  it("sin dato no es cero, y sin objetivo los escalones se reparten hasta el tope", () => {
    expect(yearLevel(undefined, 8000)).toBe("none");
    expect(yearLevel(0, 8000)).toBe(0);
    expect(yearLevel(1500, 8000)).toBe(1);
    expect(yearLevel(4000, 8000)).toBe(2);
    expect(yearLevel(6500, 8000)).toBe(4);
    expect(yearLevel(8000, 8000)).toBe(4);
  });

  it("con objetivo, el cuarto escalón es llegar y quedarse cerca no cuenta", () => {
    expect(yearLevel(0, 10000, true)).toBe(0);
    expect(yearLevel(2000, 10000, true)).toBe(1);
    expect(yearLevel(5000, 10000, true)).toBe(2);
    expect(yearLevel(9999, 10000, true)).toBe(3);
    expect(yearLevel(10000, 10000, true)).toBe(4);
    expect(yearLevel(15000, 10000, true)).toBe(4);
  });

  it("pinta los días con dato, los huecos y la leyenda", () => {
    const html = renderToStaticMarkup(
      <YearCalendar
        label="Pasos"
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
    expect(html).toContain("2 de 369 días con dato");
    expect(html).toContain("objetivo");
  });

  it("sin días lo dice", () => {
    expect(renderToStaticMarkup(<YearCalendar label="Pasos" days={[]} />)).toContain("Sin datos");
  });
});
