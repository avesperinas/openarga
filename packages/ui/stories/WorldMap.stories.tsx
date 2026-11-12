import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../map.css";
import { MapFigures, type MapLevel, TimeBar, WorldMap } from "../src/world-map";

const meta = {
  title: "Mapa/WorldMap",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const ROUTES = [
  { id: "a1", group: "flandes", order: 0, from: [-3.7, 40.42], to: [3.23, 51.21], mode: "plane" },
  { id: "a2", group: "flandes", order: 1, from: [3.23, 51.21], to: [3.72, 51.05], mode: "train" },
  { id: "a3", group: "flandes", order: 2, from: [3.72, 51.05], to: [3.06, 50.63], mode: "bus" },
  { id: "a4", group: "flandes", order: 3, from: [3.06, 50.63], to: [-3.7, 40.42], mode: "plane" },
  { id: "b1", group: "italia", order: 0, from: [-3.7, 40.42], to: [12.5, 41.9], mode: "plane" },
  { id: "b2", group: "italia", order: 1, from: [12.5, 41.9], to: [11.25, 43.77], mode: "train" },
  { id: "c1", group: "baleares", order: 0, from: [-0.38, 39.47], to: [2.65, 39.57], mode: "boat" },
  { id: "d1", group: "norte", order: 0, from: [-3.7, 40.42], to: [-2.93, 43.26], mode: "car" },
] as const;

function Demo({ level, highlight }: { level: MapLevel; highlight: string | null }) {
  const [years, setYears] = React.useState<[number, number]>([2019, 2025]);
  const [playing, setPlaying] = React.useState(false);
  return (
    <div style={{ position: "relative", height: "100vh", margin: "calc(-1 * var(--space-8))" }}>
      <WorldMap
        geoBase="/geo/"
        level={level}
        label="Mapa de viajes"
        areas={
          level === "country"
            ? [
                { code: "ES", tone: "slept", weight: 1 },
                { code: "BE", tone: "slept", weight: 0.5 },
                { code: "IT", tone: "slept", weight: 0.3 },
                { code: "FR", tone: "visited", weight: 0 },
                { code: "PT", tone: "home", weight: 0 },
              ]
            : [
                { code: "ES-PV", tone: "slept", weight: 0.4 },
                { code: "ES-MD", tone: "slept", weight: 1 },
                { code: "ES-IB", tone: "slept", weight: 0.2 },
                { code: "BE-VLG", tone: "slept", weight: 0.6 },
                { code: "IT-62", tone: "slept", weight: 0.3 },
                { code: "IT-52", tone: "slept", weight: 0.2 },
                { code: "FR-HDF", tone: "visited", weight: 0 },
              ]
        }
        places={[
          { id: "1", lon: 3.23, lat: 51.21, kind: "stay", size: 0.6 },
          { id: "2", lon: 3.72, lat: 51.05, kind: "stay", size: 0.3 },
          { id: "3", lon: 3.06, lat: 50.63, kind: "visit", size: 0 },
          { id: "4", lon: 12.5, lat: 41.9, kind: "stay", size: 0.8 },
          { id: "5", lon: 11.25, lat: 43.77, kind: "stay", size: 0.4 },
          { id: "6", lon: 2.65, lat: 39.57, kind: "stay", size: 1 },
        ]}
        routes={ROUTES.map((route) => ({ ...route, from: [...route.from], to: [...route.to] })) as never}
        highlight={highlight}
      />
      <div style={{ position: "absolute", inset: "var(--space-4) var(--space-4) auto" }}>
        <MapFigures
          figures={[
            { label: "Países", value: "4" },
            { label: "Regiones", value: "7" },
            { label: "Viajes", value: "4" },
            { label: "Noches", value: "31" },
            { label: "Km", value: "6.540" },
          ]}
        />
      </div>
      <div style={{ position: "absolute", inset: "auto var(--space-4) var(--space-4)" }}>
        <TimeBar
          min={2016}
          max={2025}
          value={years}
          onChange={setYears}
          playing={playing}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
        />
      </div>
    </div>
  );
}

export const Paises: Story = { render: () => <Demo level="country" highlight={null} /> };
export const Regiones: Story = { render: () => <Demo level="region" highlight={null} /> };
export const ViajeAnimado: Story = { render: () => <Demo level="country" highlight="flandes" /> };
