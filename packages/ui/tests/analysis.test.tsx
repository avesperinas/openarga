import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { OTHERS, SeriesChart, axisOf, foldSeries, labelStep, niceCeiling } from "../src/index";

const series = (key: string, values: number[]) => ({ key, name: key, values });

describe("the series", () => {
  it("from the sixth on they join in Others, summed point by point", () => {
    const many = ["a", "b", "c", "d", "e", "f", "g"].map((key, index) => series(key, [10 - index, 1]));
    const folded = foldSeries(many);
    expect(folded.map((one) => one.key)).toEqual(["a", "b", "c", "d", "e", OTHERS]);
    expect(folded[5]!.values).toEqual([5 + 4, 2]);
  });

  it("the order, and with it the colour, is set by the key and not by today's total", () => {
    const order = ["ocio", "super", "casa"];
    const today = foldSeries([series("casa", [900]), series("ocio", [10]), series("super", [300])], order);
    expect(today.map((one) => one.key)).toEqual(["ocio", "super", "casa"]);
  });

  it("the axis starts at zero and ends on a round number, stacked and with negatives too", () => {
    expect(niceCeiling(1830)).toBe(2000);
    expect(niceCeiling(240)).toBe(250);
    expect(axisOf([series("a", [100, 300]), series("b", [200, 50])], "stacked")).toEqual({ min: 0, max: 500 });
    expect(axisOf([series("a", [-120, 300])], "bars")).toEqual({ min: -200, max: 500 });
    expect(labelStep(12)).toBe(2);
  });
});

describe("the chart", () => {
  const html = renderToStaticMarkup(
    <SeriesChart
      label="Spending by category"
      labels={["jul", "ago", "sep"]}
      series={[series("super", [300, 280, 310]), series("ocio", [120, 90, 60])]}
      kind="stacked"
      order={["super", "ocio"]}
      format={(value) => `${value} €`}
    />,
  );

  it("each series takes its colour from its key, and there is a legend with more than one", () => {
    expect(html).toContain('data-series="0"');
    expect(html).toContain('data-series="1"');
    expect(html).toContain("series-chart-legend");
  });

  it("each point reads with the keyboard and in the table, not only on hover", () => {
    expect(html).toContain('aria-label="ago: super 280 €, ocio 90 €"');
    expect(html).toContain("<summary>See as a table</summary>");
    expect(html).toContain("<td>310 €</td>");
  });

  it("without data it says so instead of drawing an empty axis", () => {
    expect(renderToStaticMarkup(<SeriesChart label="x" labels={[]} series={[]} />)).toContain("No data in this range");
  });
});

describe("the reference line", () => {
  const html = renderToStaticMarkup(
    <SeriesChart
      label="Net worth"
      kind="stacked"
      labels={["Jan", "Feb"]}
      series={[series("cash", [100, 200]), series("fund", [300, 400])]}
      overlay={{ key: "put", name: "Put in", values: [350, 500] }}
    />,
  );

  it("draws on top, dashed, and enters the legend and the table", () => {
    expect(html).toContain("series-chart-overlay");
    expect(html.match(/Put in/g)?.length).toBeGreaterThanOrEqual(2);
    expect(html).toContain("<td>500</td>");
  });

  it("the axis reaches the reference even when the bars stay below", () => {
    const tall = renderToStaticMarkup(
      <SeriesChart
        label="x"
        labels={["a"]}
        series={[series("a", [100])]}
        overlay={{ key: "r", name: "Ref", values: [900] }}
      />,
    );
    expect(tall).toContain("1,000");
  });
});
