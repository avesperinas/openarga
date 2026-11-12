import { remember, reset } from "@openarga/app";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { Machine, MuscleSummary, Stats, VariantPoint } from "./api";
import { english, inLocale, spanish } from "./i18n/testing";
import { ExerciseSummary, StatsScreen, VolumeCard, exerciseLabel, periodLabel, signed, sparkline, whyNot } from "./Stats";

describe("how the Stats numbers read", () => {
  it("the sign goes in the text, not only in the colour", () => {
    expect(signed(2.1, "en")).toBe("+2.1 %");
    expect(signed(-2.1, "en")).toBe("−2.1 %");
    expect(signed(0, "en")).toBe("+0.0 %");
  });

  it("the decimal mark is the one of the person", () => {
    expect(signed(12.35, "es")).toContain(",");
    expect(signed(12.35, "es")).not.toContain(".");
    expect(signed(12.35, "en")).toContain(".");
  });

  it("each period has its name written", () => {
    expect(periodLabel("4w", english)).toBe("4 weeks");
    expect(periodLabel("all", english)).toBe("Since the beginning");
    expect(periodLabel("all", spanish)).toBe(spanish("stats.period.all"));
  });
});

describe("the index line", () => {
  const coords = (values: number[]): { x: number; y: number }[] =>
    sparkline(values)
      .split(" ")
      .filter(Boolean)
      .map((pair) => {
        const [x, y] = pair.split(",").map(Number);
        return { x: x ?? 0, y: y ?? 0 };
      });

  it("starts on the left and ends on the right, inside the box", () => {
    const points = coords([100, 102, 104]);

    expect(points).toHaveLength(3);
    expect(points[0]?.x).toBe(0);
    expect(points[2]?.x).toBe(320);
    expect(points.every((point) => point.y >= 0 && point.y <= 64)).toBe(true);
  });

  it("the highest is painted on top", () => {
    const points = coords([100, 101, 105]);

    expect(points[2]?.y).toBeLessThan(points[0]?.y ?? 0);
  });

  it("a flat line does not leave the box", () => {
    const points = coords([100, 100, 100]);

    expect(points.every((point) => Number.isFinite(point.y) && point.y >= 0 && point.y <= 64)).toBe(
      true,
    );
  });

  it("with a single point there is no line to draw", () => {
    expect(sparkline([100])).toBe("");
  });
});

describe("how it is named and explained", () => {
  it("a variant that already carries the exercise in its name does not repeat it", () => {
    expect(exerciseLabel({ exercise: "Bench press", variant: "Barbell bench press" })).toBe("Barbell bench press");
    expect(exerciseLabel({ exercise: "Lat pulldown", variant: "High cable" })).toBe("Lat pulldown · High cable");
  });

  const point: VariantPoint = {
    id: "p",
    session_id: "s",
    day: "2025-04-02",
    reps: 3,
    load: 140,
    e1rm: 154,
    reliable: true,
    status: "high",
    reference: 115.5,
    verdict: null,
  };

  it("a day set aside says how far it is and from what", () => {
    expect(whyNot(point, english, "en")).toBe("33 % above the surrounding sessions on this machine (the usual, 115.5 kg)");
    expect(whyNot(point, spanish, "es")).toContain("115,5 kg");
    expect(whyNot({ ...point, status: "excluded", verdict: "excluded" }, english, "en")).toBe("You set it aside");
    expect(whyNot({ ...point, status: "counted", verdict: "counted" }, english, "en")).toBe("It counts because you said so");
    expect(whyNot({ ...point, status: "counted" }, english, "en")).toBeNull();
  });
});

describe("the muscles card", () => {
  const muscle = (id: string, name: string, region: string, delta: number | null): MuscleSummary => ({
    muscle: id,
    name,
    region,
    sets: delta === null ? 0 : 12,
    band: delta === null ? "low" : "ok",
    value: delta === null ? null : 100 + delta,
    delta,
    direction: delta === null ? null : delta > 1 ? "up" : delta < -1 ? "down" : "flat",
    trend: [],
    last_day: null,
    current: null,
    excluded: 0,
  });
  const stats = (bodyweight: number | null): Stats => ({
    period: "3m",
    since: "2026-06-24",
    until: "2026-09-23",
    sessions: 30,
    index: { value: 102, delta: 2, direction: "up", muscles: 1, trend: [] },
    frequency: { done: 2, goal: 5, average: 4, streak: 0 },
    muscles: [muscle("chest", "Chest", "upper", 4.2), muscle("calves", "Calves", "lower", null)],
    movers: [],
    excluded: 0,
    bodyweight,
  });

  it("shows every group, also those without strength data", () => {
    const html = renderToString(inLocale(<VolumeCard stats={stats(80)} onOpen={() => undefined} />)).replaceAll("<!-- -->", "");

    expect(html).toContain("Chest");
    expect(html).toContain("+4.2 %");
    expect(html).toContain("Calves");
    expect(html).toContain("Lower body");
    expect(html).not.toContain("Without your weight");
  });

  it("paints the body front and back, each muscle a button with its name (T-B05)", () => {
    const html = renderToString(inLocale(<VolumeCard stats={stats(80)} onOpen={() => undefined} />));

    expect(html.match(/aria-label="Strength by muscle in the period, /g)).toHaveLength(2);
    expect(html).toMatch(/data-muscle="chest"[^>]*role="button"[^>]*aria-label="Chest"/);
    expect(html).toContain("var(--positive)");
  });

  it("without bodyweight it warns that pull-ups and dips do not count", () => {
    const html = renderToString(inLocale(<VolumeCard stats={stats(null)} onOpen={() => undefined} />));

    expect(html).toContain("Without your weight");
  });

  it("paints at once with the last thing seen, without waiting for the network (T-B10)", async () => {
    await reset();
    remember("stats:3m", stats(80));

    const html = renderToString(inLocale(<StatsScreen />)).replaceAll("<!-- -->", "");

    expect(html).toContain("Chest");
    expect(html).not.toContain('aria-busy="true"');
    await reset();
  });

  it("the screen goes in sections, with the body first (T-B05)", () => {
    const html = renderToString(inLocale(<StatsScreen initial={stats(80)} />)).replaceAll("<!-- -->", "");
    const titles = [...html.matchAll(/<h2 class="section-title">([^<]+)</g)].map((match) => match[1]);

    expect(titles).toEqual(["Muscles", "Performance", "Consistency"]);
  });
});

describe("an exercise (T-B05)", () => {
  const point = (id: string, day: string, e1rm: number): VariantPoint => ({
    id,
    session_id: `s-${id}`,
    day,
    reps: 5,
    load: Math.round((e1rm / (1 + 5 / 30)) * 10) / 10,
    e1rm,
    reliable: true,
    status: "counted",
    reference: null,
    verdict: null,
  });
  const points = [
    point("1", "2026-07-01", 100),
    point("2", "2026-07-08", 102),
    point("3", "2026-07-15", 101),
    point("4", "2026-07-22", 104),
    point("5", "2026-07-29", 106),
  ];
  const machine: Machine = {
    gym_id: "g",
    gym: "Gym",
    first_day: "2026-07-01",
    last_day: "2026-07-29",
    points,
    segments: [],
    marks: [],
    best: points[4]!,
    records: [
      { range: "1-5", load: 90.9, reps: 5, day: "2026-07-29", reliable: true },
      { range: "11+", load: 60, reps: 12, day: "2026-07-08", reliable: false },
    ],
    without_pr: 0,
    excluded: 0,
  };
  const html = renderToString(inLocale(<ExerciseSummary machine={machine} increment={2.5} external period="3m" />)).replaceAll(
    "<!-- -->",
    "",
  );

  it("says the estimated max and how much it changed in the period", () => {
    expect(html).toContain("106<span");
    expect(html).toContain("+6 kg in 3 months");
  });

  it("the line marks the records and shades the normal range", () => {
    expect(html.match(/data-highlight=""/g)).toHaveLength(3);
    expect(html).toContain("trend-chart-band");
    expect(html).toContain("Your normal range");
  });

  it("says what to do next time", () => {
    expect(html).toContain("2 sessions in a row with a record.");
    expect(html).toContain("For a record next time: 5 × 92.5 kg.");
  });

  it("the records by reps, with the unreliable ones dimmed", () => {
    expect(html).toContain("Records by reps");
    expect(html).toContain('<div data-muted=""><dt>11+ reps</dt>');
  });
});
