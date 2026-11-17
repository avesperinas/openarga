import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { BodyWeightCard, weighedOn, weightChange } from "../src/index";

const days = [
  { day: "2026-08-20", kg: 81.2 },
  { day: "2026-09-10", kg: 80.6 },
  { day: "2026-09-24", kg: 80.4 },
];

describe("el peso corporal", () => {
  it("says when the last weighing was, as one would say it", () => {
    expect(weighedOn("2026-09-24", "2026-09-24")).toBe("today");
    expect(weighedOn("2026-09-23", "2026-09-24")).toBe("yesterday");
    expect(weighedOn("2026-09-10", "2026-09-24")).toBe("10 Sept");
  });

  it("compares with the weight a month ago, if there is one close", () => {
    expect(weightChange(days)).toBe(-0.8);
    expect(weightChange(days.slice(1))).toBeNull();
    expect(weightChange([])).toBeNull();
    expect(weightChange([{ day: "2025-01-01", kg: 90 }, { day: "2026-09-24", kg: 80 }])).toBeNull();
  });

  it("shows the figure, the change, the line and how to log it", () => {
    const html = renderToStaticMarkup(
      <BodyWeightCard history={{ days, latest: days[2]! }} today="2026-09-24" onLog={() => undefined} />,
    );

    expect(html).toContain("80.4");
    expect(html).toContain("today · −0.8 kg in 30 days");
    expect(html).toContain("trend-chart");
    expect(html).toContain("Log");
    expect(html).toContain("The same weight in Health, Nutrition and Training.");
  });

  it("without weights it says so, and also what is waiting to arrive", () => {
    const empty = renderToStaticMarkup(<BodyWeightCard history={{ days: [], latest: null }} onLog={() => undefined} />);
    const pending = renderToStaticMarkup(
      <BodyWeightCard history={{ days: days.slice(2), latest: days[2]!, pending: true }} today="2026-09-24" onLog={() => undefined} />,
    );

    expect(empty).toContain("No weight logged yet.");
    expect(empty).not.toContain("trend-chart");
    expect(pending).toContain("It will reach Health as soon as it answers.");
  });
});
