import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../library.css";
import { AreaTrend, BalanceHero, Card, DivergingBars, GainChart, MonthStrip, Sankey, SegmentedControl, SeriesChart, Treemap } from "../src/index";
import { plain } from "../src/format";

const meta = { title: "Dinero", parameters: { layout: "padded" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const months = ["dic", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov"];
const worth = [39180, 39820, 40100, 41020, 41500, 41300, 42900, 43800, 43600, 45400, 46900, 48320];
const euros = (value: number) => `${plain(value)} €`;

export const CifraConCurva: Story = {
  render: () => {
    const [which, setWhich] = React.useState<"total" | "liquid">("total");
    return (
      <div style={{ maxWidth: 390 }}>
        <Card>
          <AreaTrend
            label="Patrimonio"
            value={euros(which === "total" ? 48320 : 41200)}
            delta={{ text: "+9.140 € · +23,3 % en 12 meses", tone: "positive" }}
            points={months.map((label, index) => ({ label, value: worth[index]! * (which === "total" ? 1 : 0.85) }))}
            aside={
              <SegmentedControl
                label="Qué patrimonio"
                value={which}
                onChange={setWhich}
                options={[
                  { value: "total", label: "Total" },
                  { value: "liquid", label: "Líquido" },
                ]}
              />
            }
          />
        </Card>
      </div>
    );
  },
};

export const TiraDeMeses: Story = {
  render: () => {
    const [chosen, setChosen] = React.useState("11");
    return (
      <div style={{ maxWidth: 390 }}>
        <MonthStrip
          label="Meses"
          selected={chosen}
          onSelect={setChosen}
          items={months.map((label, index) => ({
            key: String(index),
            label,
            value: 1500 + ((index * 337) % 900),
            description: `${label}, ${euros(1500 + ((index * 337) % 900))}`,
          }))}
        />
      </div>
    );
  },
};

export const QuienDebe: Story = {
  render: () => (
    <div style={{ maxWidth: 390, display: "grid", gap: "var(--space-4)" }}>
      <Card>
        <BalanceHero payer={{ name: "Sam", hue: 6 }} payee={{ name: "Alex", hue: 5 }} amount="312 €" detail="Por lo de 2026 · sin liquidar" />
      </Card>
      <Card>
        <BalanceHero payer={{ name: "Sam", hue: 6 }} payee={{ name: "Alex", hue: 5 }} amount="0 €" detail="2025 liquidado" even />
      </Card>
    </div>
  ),
};

export const AportadoContraValor: Story = {
  render: () => (
    <div style={{ maxWidth: 390 }}>
      <Card>
        <GainChart
          label="Fondos: lo que valen contra lo aportado"
          labels={months}
          value={worth.map((one) => one * 0.4)}
          contributed={months.map((_, index) => 15000 + index * 300)}
          format={euros}
        />
      </Card>
    </div>
  ),
};

export const MapaDeBloques: Story = {
  render: () => (
    <div style={{ maxWidth: 390, display: "grid", gap: "var(--space-4)" }}>
      <Card>
        <Treemap
          label="Gasto del año por categoría"
          onSelect={() => undefined}
          items={[
            { key: "casa", label: "Casa", value: 6500, detail: "6.500 €", hue: 3 },
            { key: "super", label: "Súper", value: 4120, detail: "4.120 €", hue: 2, mark: "▲" },
            { key: "viajes", label: "Viajes", value: 3200, detail: "3.200 €", hue: 1 },
            { key: "ocio", label: "Ocio", value: 2010, detail: "2.010 €", hue: 7 },
            { key: "transporte", label: "Transporte", value: 1890, detail: "1.890 €", hue: 6 },
            { key: "salud", label: "Salud", value: 900, detail: "900 €", hue: 5 },
            { key: "resto", label: "El resto", value: 790, detail: "790 €", hue: 8 },
          ]}
        />
        <DivergingBars
          label="Contra tu media"
          rows={[
            { key: "super", label: "Súper", value: 0.18, text: "+18 %", tone: "negative" },
            { key: "ocio", label: "Ocio", value: 0.09, text: "+9 %", tone: "negative" },
            { key: "viajes", label: "Viajes", value: -0.12, text: "−12 %", tone: "positive" },
            { key: "transporte", label: "Transporte", value: -0.05, text: "−5 %", tone: "positive" },
          ]}
        />
      </Card>
    </div>
  ),
};

export const AreasApiladas: Story = {
  render: () => (
    <div style={{ maxWidth: 520 }}>
      <Card>
        <SeriesChart
          kind="area"
          label="Patrimonio por tipo"
          labels={months}
          format={euros}
          series={[
            { key: "cash", name: "Efectivo", values: worth.map((one) => one * 0.2) },
            { key: "fondos", name: "Fondos", values: worth.map((one) => one * 0.5) },
            { key: "pension", name: "Pensión", values: worth.map((one) => one * 0.22) },
            { key: "cripto", name: "Cripto", values: worth.map((one) => one * 0.08) },
          ]}
        />
      </Card>
    </div>
  ),
};

export const FlujoEnVertical: Story = {
  render: () => (
    <div style={{ maxWidth: 390 }}>
      <Card>
        <Sankey
          vertical
          label="A dónde va cada euro"
          format={euros}
          share={(_, value) => `${Math.round((value / 2400) * 100)} %`}
          nodes={[
            { id: "nomina", name: "Nómina", column: 0, kind: "income" },
            { id: "tu", name: "Tú", column: 1, kind: "you" },
            { id: "comun", name: "Común", column: 1, kind: "common" },
            { id: "casa", name: "Casa", column: 2, kind: "expense" },
            { id: "ocio", name: "Ocio", column: 2, kind: "expense" },
            { id: "ahorro", name: "Ahorro", column: 2, kind: "saving" },
            { id: "super", name: "Súper", column: 2, kind: "expense" },
          ]}
          links={[
            { source: "nomina", target: "tu", value: 1860 },
            { source: "nomina", target: "comun", value: 540 },
            { source: "tu", target: "casa", value: 480 },
            { source: "tu", target: "ocio", value: 320 },
            { source: "tu", target: "ahorro", value: 1060 },
            { source: "comun", target: "super", value: 540 },
          ]}
        />
      </Card>
    </div>
  ),
};
