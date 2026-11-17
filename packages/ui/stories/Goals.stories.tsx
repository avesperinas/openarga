import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import { GoalRow, type WeekDayState, WeekDots } from "../src/index";

const meta: Meta = { title: "Goals/Goal row" };
export default meta;

const WEEK: { day: string; state: WeekDayState }[] = [
  { day: "2026-10-12", state: "met" },
  { day: "2026-10-13", state: "met" },
  { day: "2026-10-14", state: "missed" },
  { day: "2026-10-15", state: "today" },
  { day: "2026-10-16", state: "future" },
  { day: "2026-10-17", state: "future" },
  { day: "2026-10-18", state: "future" },
];

export const Semana: StoryObj = {
  render: () => <WeekDots days={WEEK} label="2 of 5 this week" />,
};

function Periodic() {
  const [done, setDone] = React.useState(false);
  return (
    <GoalRow
      title="Leer 20 minutos"
      subtitle="Learn · 5 days a week"
      hue={7}
      tone={done ? "positive" : "neutral"}
      status="3-week streak"
      week={WEEK.map((one) => (one.state === "today" && done ? { ...one, state: "met" } : one))}
      weekLabel="2 of 5 this week"
      check={{ checked: done, label: "Done today: Read 20 minutes", onClick: () => setDone(!done) }}
      onOpen={() => undefined}
    />
  );
}

export const Metas: StoryObj = {
  render: () => (
    <div style={{ display: "grid", gap: "var(--space-3)", maxWidth: "var(--app-width)" }}>
      <Periodic />
      <GoalRow
        title="Bajar a 80 kg"
        subtitle="Salud · peso · 31 dic"
        hue={6}
        tone="positive"
        status="Ahead"
        figure="82,0 kg"
        against="from 85 to 80 kg · you reach 79.5"
        progress={0.6}
        expected={0.5}
        onOpen={() => undefined}
      />
      <GoalRow
        title="€60,000 net worth"
        subtitle="Dinero · 31 dic"
        hue={4}
        tone="negative"
        status="Behind"
        figure="54.300 €"
        against="of €60,000 · you reach €57,100"
        progress={0.41}
        expected={0.62}
        onOpen={() => undefined}
      />
      <GoalRow title="The German B2" subtitle="Aprender · hito · jun 2027" hue={7} status="Not started" />
    </div>
  ),
};
