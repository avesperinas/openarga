import type { Meta, StoryObj } from "@storybook/react";

import * as React from "react";

import {
  HealthRing,
  HourStrip,
  Panes,
  SplitBar,
  ToggleGroup,
  ToggleList,
  ToggleRow,
  TrendTile,
  TrendTiles,
  VitalCard,
  VitalCards,
} from "../src/index";

const meta: Meta = { title: "Piezas/Rediseño" };
export default meta;

const weeks = (base: number, drift: number) => Array.from({ length: 26 }, (_, i) => (i === 9 ? null : base + Math.sin(i / 3) * 2 + (i > 21 ? drift : 0)));

export const DeUnVistazo: StoryObj = {
  render: () => (
    <VitalCards label="Cómo estás hoy">
      <VitalCard label="Sueño" icon="moon" ring={{ value: 85, target: 100, display: "85" }} verdict="Buena" tone="good" detail="7 h 30 · tardaste 20 min" onOpen={() => undefined} />
      <VitalCard label="Recuperación" icon="heart" ring={{ value: 62, target: 100, display: "62", mark: 0.5 }} verdict="Mejor que de costumbre" tone="good" detail="VFC alta, reposo normal" info="De 0 a 100; 50 es lo de siempre." onOpen={() => undefined} />
      <VitalCard label="Movimiento" icon="today" ring={{ value: 3200, target: 8000, display: "3.200" }} verdict="3.200 pasos" tone="neutral" detail="media de 7 días: 8.100" />
      <VitalCard label="Entreno" icon="flame" ring={{ value: 240, target: 297, display: "240", mark: 1 }} verdict="Por debajo de tu ritmo" tone="fair" detail="hoy: nada · semana: 2" onOpen={() => undefined} />
    </VitalCards>
  ),
};

export const ConSuLinea: StoryObj = {
  render: () => (
    <TrendTiles label="Corazón">
      <TrendTile label="FC en reposo" value="56 lpm" foot="Bajando: 56 lpm este mes; antes, 60." direction="down" weeks={weeks(60, -4)} onOpen={() => undefined} />
      <TrendTile label="Variabilidad (VFC)" value="62 ms" foot="media 30 días: 60 ms" weeks={weeks(60, 1)} changedAt={14} info="Del cambio de aparato en adelante." />
      <TrendTile label="VO₂ máx." value="48,0" foot="media del año: 47,5" weeks={weeks(47, 0)} />
    </TrendTiles>
  ),
};

export const AnilloConMarca: StoryObj = {
  render: () => (
    <div className="health-rings">
      <HealthRing value={240} target={297} display="240" caption="normal hoy: 297" label="Carga" mark={1} />
      <HealthRing value={2} target={3} display="2" caption="normal hoy: 2,3" label="Entrenos" mark={0.77} />
    </div>
  ),
};

export const LasHoras: StoryObj = {
  render: () => (
    <HourStrip label="Tensión por horas" values={[0, 0, 0, 0, 0, 0, 0, 2, 8, 20, 35, 12, 4, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0]} format={(v) => `${v} min`} now={17} />
  ),
};

export const RepartoConHueco: StoryObj = {
  render: () => (
    <SplitBar
      label="Las kcal del día por comidas"
      parts={[
        { label: "Desayuno", value: "450", share: 450, hue: 3 },
        { label: "Comida", value: "800", share: 800, hue: 2 },
      ]}
      rest={{ label: "Queda", value: "850", share: 850 }}
    />
  ),
};

export const Interruptores: StoryObj = {
  render: () => {
    const [open, setOpen] = React.useState(true);
    return (
      <div style={{ maxWidth: 280 }}>
        <ToggleList label="Capas">
          <ToggleRow name="Personal" tone={1} checked onChange={() => undefined} action={{ icon: "edit", label: "Editar Personal", onClick: () => undefined }} />
          <ToggleRow name="Festivos · Comunidad" tone={3} detail="Suscrito · al día" checked onChange={() => undefined} />
          <ToggleGroup name="Viajes" count="1 de 2" tone={5} state="mixed" onChange={() => undefined} open={open} onOpen={setOpen}>
            <ToggleRow name="Plan" tone={5} checked onChange={() => undefined} />
            <ToggleRow name="Trayectos" tone={5} checked={false} onChange={() => undefined} />
          </ToggleGroup>
        </ToggleList>
      </div>
    );
  },
};

export const ConApoyo: StoryObj = {
  render: () => (
    <Panes
      asideLabel="Atajos"
      main={<div className="surface" style={{ minHeight: 400 }} />}
      aside={<div className="surface" style={{ minHeight: 200 }} />}
    />
  ),
};

export const ConApoyoPrimero: StoryObj = {
  render: () => (
    <Panes
      asideFirst
      asideLabel="El plan"
      main={<div className="surface" style={{ minHeight: 400 }} />}
      aside={<div className="surface" style={{ minHeight: 120 }} />}
    />
  ),
};
