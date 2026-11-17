import type { Meta, StoryObj } from "@storybook/react";

import { RangeBar } from "../src/index";

const meta: Meta = { title: "Macros/Objetivos" };
export default meta;

export const Barras: StoryObj = {
  render: () => (
    <div style={{ display: "grid", gap: "var(--space-2)", maxWidth: 360 }}>
      <RangeBar label="Energy" value={1850} unit="kcal" low={1900} high={2100} state="low" detail="1.900 – 2.100 kcal" />
      <RangeBar label="Protein" value={142} unit="g" low={130} state="ok" detail="≥ 130 g" />
      <RangeBar label="Grasa saturada" value={22} unit="g" high={15.6} state="high" detail="9.9 % of kcal · cap 7 %" />
      <RangeBar label="Vitamina D" value={2} unit="µg" low={15} state="low" partial detail="Data missing for 60 % of the kcal" />
    </div>
  ),
};
