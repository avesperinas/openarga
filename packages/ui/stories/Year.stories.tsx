import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../library.css";

import { YearCalendar } from "../src/index";

const meta: Meta = { title: "Gráficas/Año" };
export default meta;

function steps() {
  const out: { day: string; value: number }[] = [];
  const end = Date.UTC(2026, 8, 25);
  for (let back = 0; back < 371; back++) {
    if ((back > 60 && back < 82) || back % 29 === 3) continue;
    const weekend = new Date(end - back * 86_400_000).getUTCDay() % 6 === 0;
    const value = Math.max(0, Math.round(7500 + Math.sin(back / 9) * 3000 + (weekend ? 2500 : 0) - (back % 17 === 0 ? 7500 : 0)));
    out.push({ day: new Date(end - back * 86_400_000).toISOString().slice(0, 10), value });
  }
  return out;
}

const pasos = (value: number) => `${value.toLocaleString("es-ES")} pasos`;

export const ConObjetivo: StoryObj = {
  render: () => <YearCalendar label="Pasos del año" days={steps()} goal={8000} format={pasos} />,
};

export const SinObjetivo: StoryObj = {
  render: () => <YearCalendar label="Páginas del año" days={steps().map((one) => ({ ...one, value: Math.round(one.value / 200) }))} />,
};
