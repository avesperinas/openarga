import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import { GoalRow, type WeekDayState, WeekDots } from "../src/index";

const meta: Meta = { title: "Metas/Fila de meta" };
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
  render: () => <WeekDots days={WEEK} label="2 de 5 esta semana" />,
};

function Periodic() {
  const [done, setDone] = React.useState(false);
  return (
    <GoalRow
      title="Leer 20 minutos"
      subtitle="Aprender · 5 días por semana"
      hue={7}
      tone={done ? "positive" : "neutral"}
      status="Racha de 3 semanas"
      week={WEEK.map((one) => (one.state === "today" && done ? { ...one, state: "met" } : one))}
      weekLabel="2 de 5 esta semana"
      check={{ checked: done, label: "Hecho hoy: Leer 20 minutos", onClick: () => setDone(!done) }}
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
        status="Por delante"
        figure="82,0 kg"
        against="de 85 a 80 kg · llegas a 79,5"
        progress={0.6}
        expected={0.5}
        onOpen={() => undefined}
      />
      <GoalRow
        title="60.000 € de patrimonio"
        subtitle="Dinero · 31 dic"
        hue={4}
        tone="negative"
        status="Por detrás"
        figure="54.300 €"
        against="de 60.000 € · llegas a 57.100 €"
        progress={0.41}
        expected={0.62}
        onOpen={() => undefined}
      />
      <GoalRow title="El B2 de alemán" subtitle="Aprender · hito · jun 2027" hue={7} status="Sin empezar" />
    </div>
  ),
};
