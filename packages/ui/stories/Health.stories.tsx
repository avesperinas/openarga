import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../library.css";
import "../health.css";

import { HealthRing, Hypnogram, QualityMonth, SleepSchedule, StageBreakdown, WorkoutHeart, ZoneBar } from "../src/index";
import type { Quality, StageSegment } from "../src/index";

const meta: Meta = { title: "Gráficas/Salud" };
export default meta;

const local = (day: number, hour: number, minute = 0) => new Date(2026, 9, day, hour, minute).toISOString();
const START = local(12, 23, 20);
const END = local(13, 7, 10);

function segments(): StageSegment[] {
  const order: StageSegment["stage"][] = ["light", "deep", "light", "rem", "awake", "light", "deep", "light", "rem", "light", "rem", "awake"];
  const minutes = [25, 55, 40, 20, 5, 60, 35, 50, 30, 60, 45, 5];
  let at = Date.parse(START);
  return order.map((stage, index) => {
    const start = new Date(at).toISOString();
    at += (minutes[index] ?? 30) * 60_000;
    return { start, end: new Date(at).toISOString(), stage };
  });
}

function pulse() {
  const out = [];
  for (let at = Date.parse(START); at < Date.parse(END); at += 5 * 60_000) {
    out.push({ at: new Date(at).toISOString(), bpm: 56 + Math.sin(at / 3_600_000) * 5 });
  }
  return out;
}

const QUALITIES: Quality[] = ["excellent", "good", "good", "fair", "poor", "good", "excellent"];

export const LaNoche: StoryObj = {
  render: () => (
    <div style={{ display: "grid", gap: 24, maxWidth: 560 }}>
      <HealthRing value={84} target={100} display="84" caption="Buena" quality="good" label="La nota de la noche" size="l" />
      <Hypnogram segments={segments()} start={START} end={END} pulse={pulse()} label="La noche por fases" />
      <StageBreakdown
        stages={[
          { stage: "awake", minutes: 10, usual: 22 },
          { stage: "rem", minutes: 95, usual: 88 },
          { stage: "light", minutes: 235, usual: 240 },
          { stage: "deep", minutes: 90, usual: 70 },
        ]}
      />
    </div>
  ),
};

export const ElMes: StoryObj = {
  render: () => (
    <div style={{ maxWidth: 420 }}>
      <QualityMonth
        label="Octubre"
        month="2026-10"
        selected="2026-10-13"
        onSelect={() => {}}
        onPrevious={() => {}}
        days={Array.from({ length: 13 }, (_, index) => {
          const quality = QUALITIES[index % QUALITIES.length] ?? "good";
          const value = { excellent: 92, good: 84, fair: 71, poor: 52 }[quality];
          return { day: `2026-10-${String(index + 1).padStart(2, "0")}`, value, quality };
        })}
      />
    </div>
  ),
};

export const ElHorario: StoryObj = {
  render: () => (
    <div style={{ maxWidth: 560 }}>
      <SleepSchedule
        label="Horario de las últimas noches"
        nights={Array.from({ length: 14 }, (_, index) => ({
          day: `2026-10-${String(index + 1).padStart(2, "0")}`,
          start: local(index, 23, (index * 17) % 60),
          end: local(index + 1, 7, (index * 23) % 60),
          quality: QUALITIES[index % QUALITIES.length],
        }))}
      />
    </div>
  ),
};

export const UnEntreno: StoryObj = {
  render: () => (
    <div style={{ display: "grid", gap: 24, maxWidth: 560 }}>
      <ZoneBar zones={[16.5, 16.9, 26, 0.8, 0]} maxHeartRate={185} />
      <WorkoutHeart
        start={local(13, 18, 30)}
        heart={{
          minutes: 63,
          avg: 127,
          max: 158,
          zones: [16.5, 16.9, 26, 0.8, 0],
          load: 132,
          recovery_2min: 23,
          source: "band",
          kcal: 562,
          max_heart_rate: 185,
          beats: Array.from({ length: 130 }, (_, index) => ({ s: index * 30, bpm: 100 + Math.sin(index / 6) * 25 + (index % 9) })),
          marks: [],
        }}
      />
    </div>
  ),
};
