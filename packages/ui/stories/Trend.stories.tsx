import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../library.css";

import { TrendChart } from "../src/index";

const meta: Meta = { title: "Charts/Trend" };
export default meta;

const kg = (value: number) => `${value.toLocaleString("en-GB", { maximumFractionDigits: 1 })} kg`;

function weights() {
  const out: { day: string; value: number; average: number }[] = [];
  const start = Date.UTC(2026, 3, 1);
  let window: number[] = [];
  for (let day = 0; day < 180; day++) {
    if (day % 3 === 1 || (day > 60 && day < 75)) continue;
    const value = Math.round((84 - day * 0.03 + Math.sin(day / 2) * 0.6) * 10) / 10;
    window = [...window.filter((_, index) => index > window.length - 5), value];
    const average = Math.round((window.reduce((sum, one) => sum + one, 0) / window.length) * 10) / 10;
    out.push({ day: new Date(start + day * 86_400_000).toISOString().slice(0, 10), value, average });
  }
  return out;
}

export const Peso: StoryObj = {
  render: () => (
    <TrendChart
      label="Peso"
      points={weights()}
      band={{ low: 76, high: 80 }}
      valueName="Pesada"
      averageName="7-day average"
      format={kg}
    />
  ),
};

export const Analito: StoryObj = {
  render: () => (
    <TrendChart
      label="Colesterol LDL"
      points={[
        { day: "2022-09-30", value: 142 },
        { day: "2023-08-23", value: 151 },
        { day: "2024-10-01", value: 128 },
        { day: "2025-06-11", value: 117 },
        { day: "2026-05-11", value: 109 },
      ]}
      band={{ high: 130 }}
      bandName="Reference range"
      valueName="LDL"
      format={(value) => `${Math.round(value)} mg/dL`}
    />
  ),
};

export const Records: StoryObj = {
  render: () => (
    <div style={{ "--trend-tone": "var(--kind-push)" } as React.CSSProperties}>
      <TrendChart
        label="Estimated max per session"
        valueName="Estimated max"
        bandName="Your normal range"
        highlightName="Record"
        format={kg}
        band={{ low: 110, high: 116 }}
        points={[109, 110, 108, 111, 112, 111, 110, 113, 114, 113, 115, 116, 115, 117, 119].map((value, index) => ({
          day: new Date(Date.UTC(2026, 6, 1) + index * 6 * 86_400_000).toISOString().slice(0, 10),
          value,
          highlight: [4, 7, 8, 10, 11, 13, 14].includes(index),
        }))}
      />
    </div>
  ),
};
