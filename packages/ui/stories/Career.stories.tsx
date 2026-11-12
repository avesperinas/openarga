import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../library.css";
import { Card, MonthDots, PeriodBars, SeriesChart, SpanRibbon, Waterfall, monthRange } from "../src/index";
import type { Period, PeriodSpan } from "../src/index";
import { plain } from "../src/format";

const meta = { title: "Carrera", parameters: { layout: "padded" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const euros = (value: number) => `${plain(Math.round(value))} €`;
const spans: PeriodSpan[] = [
  { key: "vision", name: "Visión Labs", hue: 5, from: "2023-01", to: "2024-04" },
  { key: "ribera", name: "Datos Ribera", hue: 1, from: "2024-05", to: "2026-02" },
  { key: "qubit", name: "Qubit Works", hue: 7, from: "2026-03", to: "2026-06" },
  { key: "paro", name: "Paro", hue: 8, from: "2026-07", to: "2026-07", muted: true },
  { key: "campo", name: "Campo Digital", hue: 2, from: "2026-08", to: null },
];
const months = monthRange("2023-01", "2027-10");
const net: Record<string, number> = { vision: 1580, ribera: 2340, qubit: 3030, paro: 1050, campo: 2629 };
const periods: Period[] = months.map((key) => {
  const span = spans.find((one) => key >= one.from && key <= (one.to ?? "2099-12"))!;
  const extra = (key.endsWith("-06") || key.endsWith("-12")) && (span.key === "vision" || span.key === "campo");
  return {
    key,
    label: key,
    projected: key > "2026-10",
    parts: [{ group: span.key, value: net[span.key]! * (extra ? 1.85 : 1), estimated: key < "2024-05" }],
  };
});

export const Carrera: Story = {
  render: () => {
    const [chosen, setChosen] = React.useState<string | null>(null);
    return (
      <div style={{ maxWidth: 960 }}>
        <Card title="Tu carrera, mes a mes">
          <PeriodBars
            label="Neto de cada mes por empresa, con los 12 que vienen"
            periods={periods}
            groups={spans.map(({ key, name, hue }) => ({ key, name, hue }))}
            spans={spans}
            format={euros}
            axisFormat={(value) => `${plain(value / 1000)} mil`}
            selected={chosen}
            onSelect={setChosen}
          />
        </Card>
      </div>
    );
  },
};

export const Cinta: Story = {
  render: () => (
    <div style={{ maxWidth: 390 }}>
      <SpanRibbon spans={spans} months={monthRange("2023-01", "2026-11")} label="Contratos" onSelect={() => undefined} />
    </div>
  ),
};

export const Cuadre: Story = {
  render: () => (
    <div style={{ maxWidth: 390 }}>
      <MonthDots
        label="Nóminas de 2026"
        onSelect={() => undefined}
        items={["e", "f", "m", "a", "m", "j", "j", "a", "s", "o", "n", "d"].map((label, index) => ({
          key: String(index),
          label,
          state: index < 2 ? "estimated" : index === 7 ? "differs" : index > 9 ? "projected" : "matched",
          description: label,
        }))}
      />
    </div>
  ),
};

export const Cascada: Story = {
  render: () => (
    <div style={{ maxWidth: 390 }}>
      <Waterfall
        label="De la cuota al resultado"
        format={euros}
        steps={[
          { key: "due", label: "Cuota íntegra", value: 9420, kind: "total" },
          { key: "min", label: "Mínimo personal", value: -1084, kind: "change", tone: "positive" },
          { key: "work", label: "Por trabajo", value: -400, kind: "change", tone: "positive" },
          { key: "net", label: "Cuota líquida", value: 7936, kind: "total" },
          { key: "held", label: "Retenido", value: -6556, kind: "change", tone: "positive" },
          { key: "result", label: "A pagar", value: 1380, kind: "result", tone: "warning" },
        ]}
      />
    </div>
  ),
};

export const Escalones: Story = {
  render: () => {
    const labels = monthRange("2023-01", "2026-11");
    const gross = labels.map((key) =>
      key < "2023-05" ? 24000 : key < "2024-05" ? 27000 : key < "2026-03" ? 38000 : key < "2026-07" ? 52000 : key < "2026-08" ? Number.NaN : 46000,
    );
    return (
      <div style={{ maxWidth: 390 }}>
        <SeriesChart kind="step" label="Bruto anual de cada contrato" labels={labels} series={[{ key: "gross", name: "Bruto anual", values: gross }]} format={euros} />
      </div>
    );
  },
};
