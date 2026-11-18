import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import {
  WALLPAPERS,
  Widget,
  WidgetFootnote,
  WidgetKpi,
  WidgetRing,
  WidgetRow,
  WidgetRows,
  WidgetStats,
  spanOf,
  wallpaperStyle,
  type WidgetSize,
} from "../src/index";
import "../library.css";
import "../widget.css";

const meta = {
  title: "Escritorio",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

function Grid({ children }: { children: React.ReactNode }) {
  return (
    <div
      data-wallpaper="desktop"
      style={{
        ...wallpaperStyle(WALLPAPERS[0]!),
        position: "relative",
        display: "grid",
        gridTemplateColumns: "repeat(4, 80px)",
        gridAutoRows: "80px",
        gap: "var(--grid-gap)",
        padding: "var(--space-4)",
        width: "fit-content",
      }}
    >
      <div className="wallpaper" aria-hidden="true" style={{ position: "absolute" }} />
      {children}
    </div>
  );
}

function Cell({ size, children }: { size: WidgetSize; children: React.ReactNode }) {
  const [w, h] = spanOf(size);
  return <div style={{ gridColumn: `span ${w}`, gridRow: `span ${h}` }}>{children}</div>;
}

const CONNECTIONS = [
  { label: "BBVA", value: "Caducada", tone: "negative" },
  { label: "Santander", value: "A medias", tone: "warning" },
  { label: "Example Bank", value: "Up to date", tone: "positive" },
  { label: "Correo", value: "Up to date", tone: "positive" },
  { label: "Claude", value: "Paused", tone: "neutral" },
] as const;

export const LasApps: Story = {
  render: () => (
    <Grid>
      <Cell size="2x2">
        <Widget title="Entreno" hue={4} size="2x2" shape="number" state="ready">
          <WidgetRing value={2} target={4} label="of 4 this week" />
        </Widget>
      </Cell>
      <Cell size="2x2">
        <Widget title="Entreno" hue={4} size="2x2" shape="number" state="ready">
          <WidgetRing value={4} target={4} label="of 4 this week" />
        </Widget>
      </Cell>
      <Cell size="2x2">
        <Widget title="Next session" hue={4} size="2x2" shape="number" state="ready">
          <WidgetKpi value="Pull" icon="pull" hue={2} />
        </Widget>
      </Cell>
      <Cell size="2x2">
        <Widget title="Next session" hue={4} size="2x2" shape="number" state="ready">
          <WidgetKpi value="Cuerpo entero" icon="kettlebell" hue={5} />
        </Widget>
      </Cell>
      <Cell size="2x2">
        <Widget title="Hub" hue={6} size="2x2" shape="list" state="ready">
          <WidgetRows href="#">
            {CONNECTIONS.map((row) => (
              <WidgetRow key={row.label} {...row} />
            ))}
          </WidgetRows>
          <WidgetFootnote>Access to BBVA expired on 20/09; it needs reconnecting.</WidgetFootnote>
        </Widget>
      </Cell>
      <Cell size="2x2">
        <Widget title="Bancos" hue={2} size="2x2" shape="number" state="ready">
          <WidgetStats
            items={[
              { label: "Bancos", value: 2 },
              { label: "Cuentas", value: 5 },
              { label: "Last sync", value: "2 h" },
            ]}
          />
        </Widget>
      </Cell>
      <Cell size="4x2">
        <Widget title="Bancos" hue={2} size="4x2" shape="number" state="ready">
          <WidgetStats
            items={[
              { label: "Bancos", value: 2 },
              { label: "Cuentas", value: 5 },
              { label: "Last sync", value: "2 h" },
            ]}
          />
          <WidgetFootnote>Access to BBVA expires in 5 days.</WidgetFootnote>
        </Widget>
      </Cell>
      <Cell size="1x1">
        <Widget title="Entreno" hue={4} size="1x1" shape="number" state="ready">
          <WidgetRing value={3} target={4} />
        </Widget>
      </Cell>
      <Cell size="1x1">
        <Widget title="Entreno" hue={4} size="1x1" shape="number" state="ready">
          <WidgetRing value={4} target={4} />
        </Widget>
      </Cell>
      <Cell size="2x2">
        <Widget
          title="Recetario"
          hue={7}
          size="2x2"
          shape="number"
          state="empty"
          note="no recipes yet"
        />
      </Cell>
    </Grid>
  ),
};
