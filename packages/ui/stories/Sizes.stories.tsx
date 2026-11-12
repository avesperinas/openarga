/// <reference types="vite/client" />
import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import {
  type Hue,
  SIZES,
  WALLPAPERS,
  Widget,
  WidgetAgenda,
  WidgetBars,
  WidgetCalendar,
  WidgetChart,
  WidgetHeatmap,
  WidgetKpi,
  WidgetKpiDelta,
  WidgetList,
  WidgetProgress,
  WidgetRing,
  WidgetShortcuts,
  WidgetStats,
  WidgetStreak,
  WidgetTasks,
  WidgetUpNext,
  WidgetWeek,
  type WidgetShape,
  type WidgetSize,
  spanOf,
  wallpaperStyle,
} from "../src/index";
import "../library.css";
import "../widget.css";

import moneyIcon from "../../../modules/money/ui/public/icon.svg?url";
import plannerIcon from "../../../modules/planner/ui/public/icon.svg?url";
import vitalsIcon from "../../../modules/vitals/ui/public/icon.svg?url";
import goalsIcon from "../../../modules/goals/ui/public/icon.svg?url";
import trainingIcon from "../../../modules/training/ui/public/icon.svg?url";

const meta = {
  title: "Widget/Formas",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const inHours = (hours: number) => new Date(Date.now() + hours * 3_600_000);

const at = (days: number, hour: number, minute = 0) => {
  const date = new Date();
  date.setDate(date.getDate() + days);
  date.setHours(hour, minute, 0, 0);
  return date.toISOString();
};
const dayIso = (days: number) => {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
};
const now = new Date().getHours();

const ENTRIES = [
  { start: dayIso(0), allDay: true, title: "Cumpleaños de Ane", tone: 5 },
  { start: at(0, 9), end: at(0, 10), title: "Reunión de equipo", detail: "Sala 2", tone: 1 },
  { start: at(0, now, 0), end: at(0, now + 1, 0), title: "Revisión del proyecto", tone: 1 },
  { start: at(0, now + 2, 30), end: at(0, now + 3, 30), title: "Dentista", detail: "Clínica Sur", tone: 4 },
  { start: at(0, 19), end: at(0, 20, 30), title: "Pádel", tone: 2 },
  { start: at(1, 8, 30), end: at(1, 9), title: "Llamar al banco", tone: 3 },
  { start: at(1, 18), end: at(1, 19), title: "Pierna", detail: "Rotación 12", tone: 2 },
  { start: at(2, 13), end: at(2, 14), title: "Comida con Irati", tone: 5 },
  { start: at(3, 10), end: at(3, 12), title: "Examen de Estadística", tone: 6 },
  { start: at(4, 20), end: at(4, 22), title: "Cine", tone: 5 },
  { start: dayIso(5), end: dayIso(7), allDay: true, title: "Viaje a Lisboa", tone: 8 },
  { start: at(9, 9), end: at(9, 10), title: "ITV", tone: 3 },
  { start: at(12, 18), end: at(12, 19), title: "Pádel", tone: 2 },
  { start: at(15, 18), end: at(15, 19), title: "Pádel", tone: 2 },
  { start: at(-3, 18), end: at(-3, 19), title: "Pádel", tone: 2 },
  { start: at(-6, 10), end: at(-6, 11), title: "Médico", tone: 4 },
];

interface Sample {
  title: string;
  hue: Hue;
  icon: string;
  shape: WidgetShape;
  body: () => React.ReactNode;
}

const SAMPLES: Sample[] = [
  {
    title: "Peso",
    hue: 5,
    icon: vitalsIcon,
    shape: "number",
    body: () => (
      <WidgetKpiDelta
        value={74.2}
        previous={75.1}
        unit="kg"
        since="hace 30 días"
        goodWhen="down"
        detail="Media de 7 días"
        series={[76.4, 76.1, 75.9, 75.6, 75.1, 75.3, 74.9, 74.6, 74.2]}
      />
    ),
  },
  {
    title: "Siguiente sesión",
    hue: 4,
    icon: trainingIcon,
    shape: "number",
    body: () => <WidgetKpi value="Pierna" icon="leg" hue={1} detail="Rotación 12" />,
  },
  {
    title: "Tendencia del gasto",
    hue: 2,
    icon: moneyIcon,
    shape: "number",
    body: () => (
      <WidgetChart
        series={[1320, 1180, 1410, 990, 1250, 1100, 1180]}
        value={1180}
        unit="€"
        detail="Gasto medio de los últimos 3 meses"
      />
    ),
  },
  {
    title: "Flujo",
    hue: 2,
    icon: moneyIcon,
    shape: "number",
    body: () => (
      <WidgetBars
        series={[820, 1240, 310, 460, 990, 610]}
        labels={["abr", "may", "jun", "jul", "ago", "sep"]}
        value="+610"
        unit="€"
        detail="Lo que te queda este mes"
        highlight={5}
      />
    ),
  },
  {
    title: "Presupuesto",
    hue: 2,
    icon: moneyIcon,
    shape: "number",
    body: () => (
      <WidgetProgress value={640} target={900} expected={540} unit="€" label="de lo habitual, 900 €" goodWhen="down" />
    ),
  },
  {
    title: "Pasos hoy",
    hue: 5,
    icon: vitalsIcon,
    shape: "number",
    body: () => <WidgetRing value={6480} target={8000} expected={5600} label="de 8.000" />,
  },
  {
    title: "Racha",
    hue: 4,
    icon: trainingIcon,
    shape: "number",
    body: () => (
      <WidgetStreak
        current={6}
        best={21}
        days={[true, true, false, true, true, true, true, true, true, false, true, true, true, true]}
      />
    ),
  },
  {
    title: "Pasos del año",
    hue: 5,
    icon: vitalsIcon,
    shape: "number",
    body: () => (
      <WidgetHeatmap
        values={Array.from({ length: 140 }, (_, i) => ((i * 37) % 11) / 10)}
        columns={20}
        detail="Media de 7.412 al día"
      />
    ),
  },
  {
    title: "Bancos",
    hue: 2,
    icon: moneyIcon,
    shape: "number",
    body: () => (
      <WidgetStats
        items={[
          { label: "Bancos", value: 2 },
          { label: "Cuentas", value: 5 },
          { label: "Sincronizado", value: "2 h" },
        ]}
      />
    ),
  },
  {
    title: "Para hoy",
    hue: 3,
    icon: goalsIcon,
    shape: "list",
    body: () => (
      <WidgetList
        rows={[
          { label: "Pasar la ITV del coche", value: "hace 3 días", tone: "warning" },
          { label: "Llamar al fontanero", value: "10:00" },
          { label: "Renovar el seguro de hogar", value: "hoy" },
          { label: "Devolver el libro", value: "hoy" },
          { label: "Comprar regalo", value: "hoy" },
        ]}
        detail="1 vencida"
      />
    ),
  },
  {
    title: "Próximo",
    hue: 6,
    icon: plannerIcon,
    shape: "list",
    body: () => (
      <WidgetUpNext
        events={[
          { at: inHours(1), title: "Dentista", detail: "Clínica Sur" },
          { at: inHours(4), title: "Cena con amigos" },
          { at: inHours(20), title: "Revisión del coche", detail: "Taller" },
          { at: inHours(23), title: "Pádel" },
          { at: inHours(45), title: "Reunión de vecinos" },
          { at: inHours(70), title: "Cumpleaños" },
          { at: inHours(96), title: "Vuelo a Lisboa", detail: "T4" },
        ]}
      />
    ),
  },
  {
    title: "Este mes",
    hue: 6,
    icon: plannerIcon,
    shape: "list",
    body: () => <WidgetCalendar entries={ENTRIES} />,
  },
  {
    title: "Tareas",
    hue: 3,
    icon: goalsIcon,
    shape: "list",
    body: () => (
      <WidgetTasks
        count={6}
        onToggle={() => new Promise((resolve) => setTimeout(() => resolve(true), 400))}
        tasks={[
          { id: "1", title: "Enviar la factura del taller", due: dayIso(-2), overdue: true, hue: 4, detail: "Trabajo" },
          { id: "2", title: "Llamar al fontanero", due: at(0, now + 2), hue: 3, detail: "Casa" },
          { id: "3", title: "Regar las plantas", due: dayIso(0), hue: 3, detail: "Casa" },
          { id: "4", title: "Renovar el DNI", due: dayIso(0), hue: 1, detail: "Personal" },
          { id: "5", title: "Preparar la presentación", due: dayIso(1), hue: 4, detail: "Trabajo" },
          { id: "6", title: "Leche", done: true },
        ]}
      />
    ),
  },
  {
    title: "Hoy",
    hue: 6,
    icon: plannerIcon,
    shape: "list",
    body: () => <WidgetAgenda entries={ENTRIES} />,
  },
  {
    title: "Semana",
    hue: 6,
    icon: plannerIcon,
    shape: "list",
    body: () => <WidgetWeek entries={ENTRIES} />,
  },
  {
    title: "Mes",
    hue: 6,
    icon: plannerIcon,
    shape: "list",
    body: () => <WidgetCalendar entries={ENTRIES} />,
  },
  {
    title: "Accesos",
    hue: 3,
    icon: goalsIcon,
    shape: "number",
    body: () => (
      <WidgetShortcuts
        actions={[
          { label: "Nueva tarea", href: "#", icon: "plus" },
          { label: "Buscar", href: "#", icon: "search" },
        ]}
      />
    ),
  },
];

const CELL = 84;

function Row({ sample }: { sample: Sample }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(20, ${CELL}px)`,
        gridAutoRows: `${CELL}px`,
        gridAutoFlow: "dense",
        gap: "var(--grid-gap)",
        alignItems: "stretch",
      }}
    >
      {SIZES.map((size: WidgetSize) => {
        const [w, h] = spanOf(size);
        return (
          <div
            key={size}
            style={{ gridColumn: `span ${w}`, gridRow: `span ${h}`, minHeight: 0, display: "grid" }}
          >
            <Widget
              title={sample.title}
              hue={sample.hue}
              appIcon={sample.icon}
              size={size}
              shape={sample.shape}
              state="ready"
            >
              {sample.body()}
            </Widget>
          </div>
        );
      })}
    </div>
  );
}

export const Calendario: Story = {
  render: () => (
    <div
      data-wallpaper="desktop"
      style={{
        ...wallpaperStyle(WALLPAPERS[0]!),
        position: "relative",
        display: "grid",
        gap: "var(--space-8)",
        padding: "var(--space-4)",
        width: "fit-content",
      }}
    >
      <div className="wallpaper" aria-hidden="true" style={{ position: "absolute" }} />
      {SAMPLES.filter((sample) => ["Tareas", "Hoy", "Semana", "Mes"].includes(sample.title)).map((sample) => (
        <Row key={sample.title} sample={sample} />
      ))}
    </div>
  ),
};

export const Todas: Story = {
  render: () => (
    <div
      data-wallpaper="desktop"
      style={{
        ...wallpaperStyle(WALLPAPERS[0]!),
        position: "relative",
        display: "grid",
        gap: "var(--space-8)",
        padding: "var(--space-4)",
        width: "fit-content",
      }}
    >
      <div className="wallpaper" aria-hidden="true" style={{ position: "absolute" }} />
      {SAMPLES.map((sample) => (
        <Row key={sample.title} sample={sample} />
      ))}
    </div>
  ),
};
