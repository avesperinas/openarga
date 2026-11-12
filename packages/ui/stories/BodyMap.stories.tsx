import type { Meta, StoryObj } from "@storybook/react";

import "../health.css";
import { BodyMaps, amountColor, changeColor } from "../src/index";

const meta = { title: "Cuerpo", parameters: { layout: "padded" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const CHANGE: Record<string, number | null> = {
  chest: 8, lats: 7, side_delts: 5, front_delts: -2, hamstrings: 11, quads: 2, adductors: 3,
  calves: -1, glutes: -3, biceps: 0, triceps: 0.5, upper_back: 1.5, abs: null, lower_back: null,
};

export const Fuerza: Story = {
  render: () => (
    <div style={{ maxWidth: 320 }}>
      <BodyMaps
        label="Fuerza por músculo"
        colors={Object.fromEntries(Object.entries(CHANGE).map(([m, d]) => [m, changeColor(d)]))}
      />
    </div>
  ),
};

export const Trabajado: Story = {
  render: () => (
    <div style={{ maxWidth: 320 }}>
      <BodyMaps
        label="Lo trabajado hoy"
        colors={{ lats: amountColor(1), upper_back: amountColor(0.7), biceps: amountColor(0.8), forearms: amountColor(0.3) }}
      />
    </div>
  ),
};
