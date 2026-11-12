import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../library.css";
import { AreaOrbs, AreaPanel, AreaPanelSkeleton, PageTabs, PanelBlockView } from "../src/index";
import type { PanelTab } from "../src/index";

const meta = { title: "Paneles", parameters: { layout: "padded" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const months = ["dic", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov"];
const worth = [39180, 39820, 40100, 41020, 41500, 41300, 42900, 43800, 43600, 45400, 46900, 48320];

const money: PanelTab[] = [
  {
    id: "money.resumen",
    label: "Resumen",
    blocks: [
      { type: "figure", label: "Patrimonio", value: "48.320 €", delta: "+23 % en 12 meses", tone: "positive" },
      { type: "trend", unit: "money", points: months.map((label, index) => ({ label, value: worth[index]! })) },
      { type: "split", label: "Noviembre, hasta hoy", total: "entran 2.940 €", parts: [{ label: "Gastas", value: "1.410 €", share: 1410, hue: 4 }, { label: "Inviertes", value: "600 €", share: 600, hue: 5 }, { label: "Queda", value: "930 €", share: 930, hue: 2 }] },
      { type: "tiles", items: [{ label: "Colchón", value: "1,5 meses", foot: "de 3" }, { label: "Ahorras", value: "28 %", foot: "tu media, 21 %" }, { label: "Sam te debe", value: "86 €", foot: "Liquidar", href: "/money/compartido" }, { label: "Renta 2026", value: "a pagar 1.380 €", tone: "warning" }] },
      { type: "alert", text: "3 movimientos por etiquetar", href: "/money/movimientos" },
    ],
    actions: [{ label: "Etiquetar", href: "/money/movimientos", primary: true }, { label: "Abrir Money", href: "/money/" }],
  },
  { id: "money.gasto", label: "Gasto", blocks: [{ type: "treemap", items: [{ label: "Casa", value: 620, hue: 1 }, { label: "Súper", value: 410, hue: 2 }, { label: "Ocio", value: 260, hue: 7 }] }] },
];

const health: PanelTab[] = [
  {
    id: "vitals.hoy",
    label: "Hoy",
    blocks: [
      { type: "rings", items: [{ label: "Disposición", value: "78", share: 0.78, hue: 5 }, { label: "Sueño", value: "82", share: 0.82, hue: 1 }, { label: "Pasos", value: "74 %", share: 0.74, hue: 2 }, { label: "Comida", value: "68 %", share: 0.68, hue: 4 }, { label: "Entreno", value: "3/4", share: 0.75, hue: 3 }] },
      { type: "feature", eyebrow: "Siguiente sesión · Training", title: "Pierna, hoy", text: "6 ejercicios · 9 días sin pierna", body: ["legs"], action: "Empezar", href: "/training/" },
      { type: "tiles", items: [{ label: "Peso", value: "74,2 kg", foot: "−1,6 kg en 12 semanas", tone: "positive", series: [75.8, 75.4, 75.0, 74.7, 74.4, 74.2] }, { label: "FC en reposo", value: "52 ppm", series: [56, 55, 54, 53, 52] }] },
    ],
  },
];

export const Dinero: Story = {
  render: () => (
    <div style={{ maxWidth: 390 }}>
      <AreaPanel area={{ key: "money", label: "Dinero", apps: "Money · Carrera", hue: 2, icon: "€" }} headline={{ text: "Llegas a fin de mes con unos 420 € de margen", emphasis: "unos 420 €", tone: "positive", status: "Vas bien" }} tabs={money} onExpand={() => undefined} />
    </div>
  ),
};

export const DineroAncho: Story = {
  render: () => (
    <div style={{ maxWidth: 900 }}>
      <AreaPanel wide area={{ key: "money", label: "Dinero", apps: "Money · Carrera", hue: 2, icon: "€" }} headline={{ text: "Llegas a fin de mes con unos 420 € de margen", emphasis: "unos 420 €", tone: "positive", status: "Vas bien" }} tabs={money} />
    </div>
  ),
};

export const DineroTablero: Story = {
  name: "Dinero, página del ordenador",
  render: () => (
    <div style={{ maxWidth: 1200 }}>
      <AreaPanel board area={{ key: "money", label: "Dinero", apps: "Money · Carrera", hue: 2, icon: "€" }} headline={{ text: "Llegas a fin de mes con unos 420 € de margen", emphasis: "unos 420 €", tone: "positive", status: "Vas bien" }} tabs={money} />
    </div>
  ),
};

export const Llegando: Story = {
  name: "Mientras llega",
  render: () => (
    <div style={{ maxWidth: 390 }}>
      <AreaPanelSkeleton area={{ key: "money", label: "Dinero", apps: "", hue: 2, icon: "€" }} />
    </div>
  ),
};

export const Pestanas: Story = {
  name: "Pestañas de las páginas",
  render: () => {
    const [current, setCurrent] = React.useState(1);
    return (
      <div style={{ maxWidth: 390 }}>
        <PageTabs
          items={[
            { key: "day", label: "Día", hue: 6, icon: "◷" },
            { key: "money", label: "Dinero", hue: 2, icon: "€" },
            { key: "health", label: "Salud", hue: 5, icon: "♥" },
            { key: "widgets", label: "Widgets" },
          ]}
          current={current}
          onSelect={setCurrent}
        />
      </div>
    );
  },
};

export const Salud: Story = {
  render: () => (
    <div style={{ maxWidth: 390 }}>
      <AreaPanel area={{ key: "health", label: "Salud", apps: "Vitals · Training · Macros", hue: 5, icon: "♥" }} headline={{ text: "Has dormido bien: buen día para pierna", emphasis: "buen día para pierna", tone: "positive", status: "Listo" }} tabs={health} />
    </div>
  ),
};

export const Bolas: Story = {
  render: () => (
    <div style={{ background: "#7fa3d8", padding: 16 }}>
      <AreaOrbs items={[{ key: "day", label: "Día", status: "2 citas", tone: "positive", hue: 6, icon: "◷" }, { key: "money", label: "Dinero", status: "bien", tone: "positive", hue: 2, icon: "€" }, { key: "work", label: "Trabajo", status: "TFM", tone: "warning", hue: 4, icon: "▣" }]} />
    </div>
  ),
};

export const Mes: Story = {
  render: () => (
    <div style={{ maxWidth: 520 }}>
      <PanelBlockView
        block={{
          type: "month",
          month: "2026-11",
          today: 9,
          marked: [3, 9, 12, 13, 20],
          entries: [
            { start: "2026-11-03T18:00:00+01:00", end: "2026-11-03T19:30:00+01:00", title: "Pádel", tone: 4 },
            { start: "2026-11-09T09:00:00+01:00", end: "2026-11-09T09:15:00+01:00", title: "Daily", tone: 1 },
            { start: "2026-11-12", end: "2026-11-14", all_day: true, title: "Viaje a Lisboa", tone: 7 },
            { start: "2026-11-20T17:00:00+01:00", end: "2026-11-20T19:00:00+01:00", title: "Clase del máster", tone: 3 },
          ],
        }}
      />
    </div>
  ),
};
