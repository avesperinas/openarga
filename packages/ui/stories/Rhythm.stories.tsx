import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../controls.css";
import "../library.css";
import {
  Card,
  Columns,
  Cover,
  CoverWall,
  DayTimeline,
  DayTimelines,
  DockBar,
  FrequencyBar,
  FrequencyRow,
  FrequencyRows,
  MediaCard,
  MediaHero,
  RingFigure,
} from "../src/index";

const meta = { title: "Cifras con forma y carriles", parameters: { layout: "padded" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const noop = () => {};

export const Anillos: Story = {
  render: () => (
    <div data-kind="hue-3" style={{ maxWidth: 390, display: "grid", gap: "var(--space-4)" }}>
      <Card>
        <Columns>
          <RingFigure share={0.42} value="42 %" label="Ventana" detail="acaba a las 18:30" />
          <RingFigure share={0.71} value="71 %" label="Semana" detail="a 0 el jueves" tone="warning" />
        </Columns>
      </Card>
      <Card>
        <RingFigure size="medium" share={0.7} value="14" label="14 de 20 este año" detail="2 por delante del ritmo" />
      </Card>
      <Card title="Del color de cómo va">
        <Columns>
          <RingFigure size="medium" share={0.2} value="20 %" label="De sobra" tone="positive" />
          <RingFigure size="medium" share={0.5} value="50 %" label="A ritmo" tone="info" />
        </Columns>
        <Columns>
          <RingFigure size="medium" share={0.8} value="80 %" label="Ojo" tone="warning" />
          <RingFigure size="medium" share={0.95} value="95 %" label="Al límite" tone="negative" />
        </Columns>
      </Card>
    </div>
  ),
};

export const CadaCuanto: Story = {
  render: () => (
    <div data-kind="hue-1" style={{ maxWidth: 390, display: "grid", gap: "var(--space-3)" }}>
      <FrequencyBar since={15} every={8} label="cada 8 días, hace 15" />
      <FrequencyBar since={7} every={7} label="cada semana, hace 7 días" />
      <FrequencyBar since={2} every={14} label="cada 2 semanas, hace 2 días" />
      <FrequencyBar since={5} every={null} label="hace 5 días" />
      <FrequencyRows label="Lo que compras">
        <FrequencyRow title="Tomate" since={15} every={8} label="cada 8 días, hace 15" value="15 / 8 d" onClick={noop} />
        <FrequencyRow title="Café" since={11} every={14} label="cada 2 semanas, hace 11" value="11 / 14 d" onClick={noop} />
        <FrequencyRow title="Pan" since={1} every={3} label="cada 3 días, hace 1" value="1 / 3 d" onClick={noop} />
      </FrequencyRows>
    </div>
  ),
};

export const ElDiaEnVeinticuatroHoras: Story = {
  render: () => (
    <div data-kind="hue-3" style={{ maxWidth: 390 }}>
      <Card>
        <DayTimelines>
          {[
            ["L", [7, 12.1, 17.2]],
            ["M", [7, 12.1, 17.2]],
            ["X", [8.4, 13.5, 18.6]],
            ["J", [10]],
            ["V", []],
          ].map(([name, pings], index) => (
            <DayTimeline
              key={name as string}
              name={name as string}
              label={`${name}: ${(pings as number[]).length} pings`}
              marks={pings as number[]}
              spans={(pings as number[]).map((hour) => ({ from: hour, to: hour + 5 }))}
              now={index === 2 ? 16.3 : undefined}
              state={index === 2 ? "today" : (pings as number[]).length === 0 ? "off" : undefined}
              onClick={noop}
            />
          ))}
        </DayTimelines>
      </Card>
      <Card title="Discreta: solo marca los periodos">
        <DayTimeline label="Hoy: pings a las 7:00 y 12:05" marks={[7, 12.1]} spans={[{ from: 7, to: 12 }, { from: 12.1, to: 17.1 }]} now={14.5} quiet />
      </Card>
    </div>
  ),
};

export const BarraDeAbajo: Story = {
  render: () => (
    <div data-kind="hue-1" style={{ maxWidth: 390, display: "grid", gap: "var(--space-4)" }}>
      <DockBar title="4 en el carro" detail="Pan, plátanos y 2 más" action={{ label: "Terminar", icon: "done", onClick: noop }} />
    </div>
  ),
};

export const Portadas: Story = {
  render: () => (
    <div data-kind="hue-5" style={{ maxWidth: 390, display: "grid", gap: "var(--space-4)" }}>
      <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "end" }}>
        <Cover size="large" title="Un libro largo" subtitle="Autora de ejemplo" />
        <Cover size="small" title="Corto" />
      </div>
      <CoverWall
        onOpen={noop}
        items={[
          { id: "1", title: "Uno", note: "★★★★" },
          { id: "2", title: "Dos", note: "★★★" },
          { id: "3", title: "Tres", subtitle: "Alguien" },
          { id: "4", title: "Cuatro", muted: true },
        ]}
      />
    </div>
  ),
};

export const LoQueTienesEntreManos: Story = {
  render: () => (
    <div data-kind="hue-5" style={{ maxWidth: 390, display: "grid", gap: "var(--space-4)" }}>
      <MediaCard
        media={<Cover size="large" title="Un libro largo" subtitle="Autora de ejemplo" />}
        title="Un libro largo"
        lines={["Autora de ejemplo", "Desde el 12 oct · 19 días", "452 páginas"]}
        onOpen={noop}
        action={{ label: "Terminado hoy", icon: "done", onClick: noop }}
      />
      <MediaHero media={<Cover size="hero" title="Otro libro" subtitle="Alguien" />}>
        <span>Alguien · 2016</span>
      </MediaHero>
    </div>
  ),
};

