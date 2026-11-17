import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { TrendChart, trendDomain, trendX } from "../src/index";

const weights = [
  { day: "2026-09-01", value: 80.4, average: 80.4 },
  { day: "2026-09-02", value: 79.6, average: 80.0 },
  { day: "2026-09-11", value: 79.0, average: 79.0 },
];

describe("the trend", () => {
  it("fits the axis to the data and the band, not from zero", () => {
    const { min, max } = trendDomain(weights, { low: 72, high: 76 });

    expect(min).toBeGreaterThan(70);
    expect(min).toBeLessThan(72);
    expect(max).toBeGreaterThan(80.4);
    expect(max).toBeLessThan(82);
  });

  it("a single value has an axis around it", () => {
    expect(trendDomain([{ day: "2026-09-01", value: 120 }])).toEqual({ min: 119, max: 121 });
  });

  it("puts each point at its date, with gaps as gaps", () => {
    expect(trendX(weights)).toEqual([0, 0.1, 1]);
    expect(trendX([{ day: "2026-09-01", value: 1 }])).toEqual([0.5]);
  });

  it("draws the average, the measured values, the band and marks what falls outside it", () => {
    const html = renderToStaticMarkup(
      <TrendChart label="Weight" points={weights} band={{ low: 72, high: 76 }} valueName="Weighing" averageName="7-day average" />,
    );

    expect(html).toContain("trend-chart-band");
    expect(html).toContain("trend-chart-raw");
    expect(html).toContain("7-day average");
    expect(html.match(/trend-chart-dot/g)).toHaveLength(3);
    expect(html.match(/data-out/g)).toHaveLength(3);
  });

  it("without an average, the measured values are the main line, and with many points each one is not marked", () => {
    const many = Array.from({ length: 90 }, (_, index) => ({
      day: `2026-0${1 + Math.floor(index / 30)}-${String(1 + (index % 28)).padStart(2, "0")}`,
      value: 100 + index,
    }));

    const html = renderToStaticMarkup(<TrendChart label="LDL" points={many} />);

    expect(html).not.toContain("trend-chart-raw");
    expect(html).toContain("trend-chart-line");
    expect(html).not.toContain("trend-chart-dot");
  });

  it("without points it says so", () => {
    expect(renderToStaticMarkup(<TrendChart label="Weight" points={[]} />)).toContain("No data in this range");
  });

  it("marks the day of the change with its line and name, only if it falls inside", () => {
    const marked = renderToStaticMarkup(
      <TrendChart label="VFC" points={weights} marker={{ day: "2026-09-02", label: "Cambio a la pulsera" }} />,
    );
    const outside = renderToStaticMarkup(
      <TrendChart label="VFC" points={weights} marker={{ day: "2026-10-01", label: "Cambio a la pulsera" }} />,
    );

    expect(marked).toContain("trend-chart-marker");
    expect(marked).toContain("Cambio a la pulsera");
    expect(outside).not.toContain("trend-chart-marker");
  });

  it("marks the highlighted points apart, with their name in the legend", () => {
    const html = renderToStaticMarkup(
      <TrendChart
        label="e1RM"
        highlightName="Record"
        points={[
          { day: "2026-09-01", value: 100 },
          { day: "2026-09-08", value: 104, highlight: true },
        ]}
      />,
    );

    expect(html.match(/data-highlight=""/g)).toHaveLength(1);
    expect(html).toContain('data-key="highlight"');
    expect(html).toContain("Record");
  });

  it("without marking outliers, the band is only a reference", () => {
    const html = renderToStaticMarkup(
      <TrendChart
        label="e1RM"
        flagOutside={false}
        band={{ low: 100, high: 102 }}
        points={[
          { day: "2026-09-01", value: 95 },
          { day: "2026-09-08", value: 110 },
        ]}
      />,
    );

    expect(html).not.toContain("data-out");
  });
});
