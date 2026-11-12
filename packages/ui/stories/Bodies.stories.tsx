import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import {
  Widget,
  WidgetBars,
  WidgetCalendar,
  WidgetChart,
  WidgetHeatmap,
  WidgetKpi,
  WidgetKpiDelta,
  WidgetProgress,
  WidgetRing,
  WidgetRow,
  WidgetRows,
  WidgetShortcuts,
  WidgetStats,
  WidgetStreak,
  WidgetUpNext,
} from "../src/index";
import "../widget.css";

const meta = {
  title: "Widget/Cuerpos",
  component: Widget,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof Widget>;

export default meta;
type Story = StoryObj<typeof meta>;

const hace5min = new Date(Date.now() - 5 * 60 * 1000);
const base = { hue: 1, state: "ready", updatedAt: hace5min } as const;

export const Kpi: Story = {
  args: { ...base, title: "Pasos", size: "2x2", shape: "number" },
  render: (args) => (
    <Widget {...args}>
      <WidgetKpi value={1284} unit="pasos" detail="12 más que ayer" />
    </Widget>
  ),
};

export const KpiConSimbolo: Story = {
  args: { ...base, title: "Siguiente entreno", size: "2x2", shape: "number", hue: 2 },
  render: (args) => (
    <Widget {...args}>
      <WidgetKpi value="Pull" detail="rotación 7, día 2 de 3" icon="pull" hue={2} />
    </Widget>
  ),
};

export const KpiDelta: Story = {
  args: { ...base, title: "Peso", size: "2x2", shape: "number" },
  render: (args) => (
    <Widget {...args}>
      <WidgetKpiDelta
        value={62.5}
        previous={63.1}
        unit="kg"
        since="la semana pasada"
        goodWhen="down"
      />
    </Widget>
  ),
};

export const Chart: Story = {
  args: { ...base, title: "Gasto", size: "4x2", shape: "number" },
  render: (args) => (
    <Widget {...args}>
      <WidgetChart series={[12, 19, 8, 24, 17, 22, 15]} value={117} unit="€" detail="esta semana" />
    </Widget>
  ),
};

export const Bars: Story = {
  args: { ...base, title: "Entrenos", size: "4x2", shape: "number" },
  render: (args) => (
    <Widget {...args}>
      <WidgetBars
        series={[1, 0, 1, 1, 0, 2, 0]}
        labels={["L", "M", "X", "J", "V", "S", "D"]}
        value={5}
        detail="esta semana"
        highlight={5}
      />
    </Widget>
  ),
};

export const Heatmap: Story = {
  args: { ...base, title: "Constancia", size: "4x2", shape: "number" },
  render: (args) => (
    <Widget {...args}>
      <WidgetHeatmap
        values={[0, 1, 2, 0, 3, 1, 0, 2, 2, 0, 1, 3, 3, 0, 1, 1, 2, 0, 0, 3, 2]}
        columns={7}
        detail="últimas tres semanas"
      />
    </Widget>
  ),
};

export const Progress: Story = {
  args: { ...base, title: "Ahorro", size: "2x2", shape: "number" },
  render: (args) => (
    <Widget {...args}>
      <WidgetProgress value={640} target={1000} unit="€" label="de 1.000 este mes" />
    </Widget>
  ),
};

export const Ring: Story = {
  args: { ...base, title: "Esta semana", size: "2x2", shape: "number" },
  render: (args) => (
    <Widget {...args}>
      <WidgetRing value={2} target={5} label="de 5 esta semana" show="value" />
    </Widget>
  ),
};

export const Streak: Story = {
  args: { ...base, title: "Racha", size: "2x2", shape: "number" },
  render: (args) => (
    <Widget {...args}>
      <WidgetStreak current={4} best={9} days={[true, true, false, true, true, true, true]} label="días" />
    </Widget>
  ),
};

export const Stats: Story = {
  args: { ...base, title: "Última sesión", size: "4x2", shape: "number" },
  render: (args) => (
    <Widget {...args}>
      <WidgetStats
        items={[
          { label: "Series", value: 18 },
          { label: "Volumen", value: 4820, unit: "kg" },
          { label: "Duración", value: "52", unit: "min" },
        ]}
      />
    </Widget>
  ),
};

export const Lista: Story = {
  args: { ...base, title: "Comercios", size: "2x4", shape: "list" },
  render: (args) => (
    <Widget {...args}>
      <WidgetRows>
        <WidgetRow label="Mercadona" value="31 €" />
        <WidgetRow label="Alba Market" value="7 €" />
        <WidgetRow label="Bar Zurbano" value="4 €" />
      </WidgetRows>
    </Widget>
  ),
};

export const Calendario: Story = {
  args: { ...base, title: "Septiembre", size: "4x4", shape: "list" },
  render: (args) => (
    <Widget {...args}>
      <WidgetCalendar marked={[1, 3, 8, 10, 15, 17]} today={17} />
    </Widget>
  ),
};

export const LoSiguiente: Story = {
  args: { ...base, title: "Lo siguiente", size: "4x2", shape: "list" },
  render: (args) => (
    <Widget {...args}>
      <WidgetUpNext
        events={[
          { at: "2026-09-18T18:00:00Z", title: "Push", detail: "rotación 7, día 3" },
          { at: "2026-09-20T09:30:00Z", title: "Leg" },
        ]}
      />
    </Widget>
  ),
};

export const AccesosDirectos: Story = {
  args: { ...base, title: "Training", size: "2x2", shape: "list" },
  render: (args) => (
    <Widget {...args}>
      <WidgetShortcuts
        actions={[
          { label: "Empezar", href: "/training", icon: "target" },
          { label: "Plan", href: "/training/plan", icon: "edit" },
        ]}
      />
    </Widget>
  ),
};
