import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import en from "../src/i18n/en.json";

import {
  HealthRing,
  Hypnogram,
  QualityMonth,
  SleepSchedule,
  WorkoutHeart,
  ZoneBar,
  heartDomain,
  hourTicks,
  hypnogramBars,
  minutesText,
  monthCells,
  nightMinute,
  scheduleDomain,
  zoneEdges,
} from "../src/index";

const local = (day: number, hour: number, minute = 0) => new Date(2026, 9, day, hour, minute).toISOString();
const START = local(12, 23);
const END = local(13, 7);

describe("the night", () => {
  it("puts each phase in its lane and place, and clips what is outside", () => {
    const bars = hypnogramBars(
      [
        { start: local(12, 22, 30), end: local(13, 1), stage: "light" },
        { start: local(13, 1), end: local(13, 3), stage: "deep" },
        { start: local(13, 3), end: local(13, 3, 10), stage: "restless" },
      ],
      START,
      END,
    );

    expect(bars.map((one) => [one.stage, one.lane])).toEqual([
      ["light", 2],
      ["deep", 3],
      ["awake", 0],
    ]);
    expect(bars[0]).toMatchObject({ x: 0, width: 0.25 });
    expect(bars[1]).toMatchObject({ x: 0.25, width: 0.25 });
  });

  it("marks the even hours of the night", () => {
    expect(hourTicks(START, END).map((one) => one.label)).toEqual(["00:00", "02:00", "04:00", "06:00"]);
  });

  it("without stages it says so, and with them it draws one rectangle per span", () => {
    expect(renderToStaticMarkup(<Hypnogram segments={[]} start={START} end={END} label="La noche" />)).toContain("without stages");
    const html = renderToStaticMarkup(
      <Hypnogram
        segments={[{ start: START, end: END, stage: "rem" }]}
        start={START}
        end={END}
        pulse={[
          { at: START, bpm: 60 },
          { at: END, bpm: 50 },
        ]}
        label="La noche"
      />,
    );
    expect(html).toContain('data-stage="rem"');
    expect(html).toContain("de 50 a 60 lpm");
  });
});

describe("the schedule", () => {
  it("counts from midnight of the day one wakes up", () => {
    expect(nightMinute(START, "2026-10-13")).toBe(-60);
    expect(nightMinute(END, "2026-10-13")).toBe(420);
    expect(
      scheduleDomain([
        { day: "2026-10-13", start: local(12, 23, 40), end: END },
        { day: "2026-10-14", start: local(14, 0, 20), end: local(14, 8, 15) },
      ]),
    ).toEqual({ top: -60, bottom: 540 });
  });

  it("renders one bar per night", () => {
    const html = renderToStaticMarkup(<SleepSchedule label="Horario" nights={[{ day: "2026-10-13", start: START, end: END, quality: "good" }]} />);
    expect(html).toContain('data-quality="good"');
    expect(html).toContain("from 23:00 to 07:00");
  });
});

describe("the month", () => {
  it("starts on Monday with leading gaps and finishes the week", () => {
    const weeks = monthCells("2026-10");
    expect(weeks[0]).toEqual([null, null, null, "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]);
    expect(weeks.at(-1)?.at(-1)).toBeNull();
    expect(weeks.flat().filter(Boolean)).toHaveLength(31);
  });

  it("colours each night by its quality and leaves missing ones untouched", () => {
    const html = renderToStaticMarkup(<QualityMonth label="October" month="2026-10" days={[{ day: "2026-10-13", value: 84, quality: "good" }]} onSelect={() => {}} />);
    expect(html).toContain('aria-label="13: 84, good"');
    expect(html).toContain('aria-label="14, no night"');
  });
});

describe("the vitals", () => {
  it("each zone starts at its share of the maximum", () => {
    expect(zoneEdges(180)).toEqual([90, 108, 126, 144, 162]);
  });

  it("the axis leaves a margin and rounds to tens", () => {
    expect(
      heartDomain([
        { s: 0, bpm: 92 },
        { s: 60, bpm: 151 },
      ]),
    ).toEqual({ low: 80, high: 160 });
  });

  it("the breakdown says each zone's minutes with its range", () => {
    const html = renderToStaticMarkup(<ZoneBar zones={[2, 0, 4, 1, 3]} maxHeartRate={180} />);
    expect(html).toContain("126–143");
    expect(html).toContain("≥ 162");
    expect(html).toContain("4 min");
  });

  it("a workout says where its heart rate comes from and how much it dropped", () => {
    const html = renderToStaticMarkup(
      <WorkoutHeart
        start="2026-10-13T18:30:00+02:00"
        heart={{
          minutes: 60,
          avg: 124,
          max: 151,
          zones: [18, 14, 24, 0, 0],
          load: 118,
          recovery_2min: 21,
          source: "band",
          kcal: 562,
          max_heart_rate: 180,
          beats: [
            { s: 0, bpm: 95 },
            { s: 1800, bpm: 140 },
            { s: 3600, bpm: 120 },
          ],
          marks: [{ at: "2026-10-13T18:40:00+02:00", label: "Press banca · 8 × 60 kg" }],
        }}
      />,
    );
    expect(html).toContain(en["heart.from_band"]);
    expect(html).toContain("−21 lpm");
    expect(html).toContain("562 kcal");
    expect(html).toContain("84 % of your maximum");
  });
});

describe("the ring", () => {
  it("says its figure and quality, and overfilled it does not loop again", () => {
    const html = renderToStaticMarkup(<HealthRing value={130} target={100} display="130" label="Score" caption="Excellent" quality="excellent" />);
    expect(html).toContain('stroke-dashoffset="0"');
    expect(html).toContain("Score: 130, Excellent");
  });

  it("writes minutes as hours", () => {
    expect(minutesText(425)).toBe("7 h 05");
    expect(minutesText(45)).toBe("45 min");
  });
});
