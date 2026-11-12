import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../controls.css";

import { RecurrencePicker, recurrenceRule, toRRule, type RecurrenceRule } from "../src/index";

const meta: Meta = { title: "Controles/Repetición" };
export default meta;

function Playground({ date, initial }: { date: string; initial: RecurrenceRule | null }) {
  const [value, setValue] = React.useState(initial);
  return (
    <div style={{ maxWidth: 420, display: "grid", gap: 16 }}>
      <RecurrencePicker date={date} value={value} onChange={setValue} />
      <code style={{ fontSize: 12, opacity: 0.6, overflowWrap: "anywhere" }}>{value ? toRRule(value) : "—"}</code>
    </div>
  );
}

export const NoSeRepite: StoryObj = { render: () => <Playground date="2027-01-12" initial={null} /> };

export const CadaSemana: StoryObj = {
  render: () => <Playground date="2027-01-12" initial={recurrenceRule("weekly", { byDay: [{ weekday: "TU" }] })} />,
};

export const Personalizada: StoryObj = {
  render: () => (
    <Playground
      date="2027-01-12"
      initial={recurrenceRule("weekly", {
        interval: 2,
        byDay: [{ weekday: "TU" }, { weekday: "TH" }],
        until: "2027-06-30",
      })}
    />
  ),
};

export const ElUltimoViernes: StoryObj = {
  render: () => (
    <Playground date="2027-01-29" initial={recurrenceRule("monthly", { byDay: [{ weekday: "FR", pos: -1 }], count: 12 })} />
  ),
};
