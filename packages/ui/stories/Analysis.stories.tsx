import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import { ChoiceChips, FilterBar, SegmentedControl, SeriesChart } from "../src/index";

const meta: Meta<typeof SeriesChart> = {
  title: "Gráficas/Análisis",
  component: SeriesChart,
};
export default meta;

const labels = ["abr", "may", "jun", "jul", "ago", "sep"];
const categories = [
  { key: "super", name: "Supermercado", values: [310, 295, 330, 280, 300, 315] },
  { key: "ocio", name: "Ocio", values: [120, 160, 90, 210, 180, 95] },
  { key: "casa", name: "Casa", values: [650, 650, 650, 650, 650, 650] },
  { key: "transporte", name: "Transporte", values: [80, 60, 75, 120, 40, 70] },
  { key: "salud", name: "Salud", values: [30, 0, 45, 20, 0, 60] },
  { key: "ropa", name: "Ropa", values: [0, 90, 0, 40, 0, 110] },
  { key: "regalos", name: "Regalos", values: [0, 0, 25, 0, 60, 0] },
];
const euros = (value: number) => `${value.toLocaleString("es-ES")} €`;

function WithFilters() {
  const [kind, setKind] = React.useState<"stacked" | "bars" | "lines">("stacked");
  const [range, setRange] = React.useState<string | null>("6m");
  return (
    <div style={{ display: "grid", gap: "var(--space-4)", maxWidth: "40rem" }}>
      <FilterBar label="Filtros">
        <ChoiceChips
          label="Rango"
          options={[
            { value: "6m", label: "6 meses" },
            { value: "1y", label: "Un año" },
          ]}
          value={range}
          onChange={setRange}
        />
        <SegmentedControl
          label="Forma"
          options={[
            { value: "stacked", label: "Apilado" },
            { value: "bars", label: "Barras" },
            { value: "lines", label: "Líneas" },
          ]}
          value={kind}
          onChange={setKind}
        />
      </FilterBar>
      <SeriesChart label="Gasto por categoría" labels={labels} series={categories} kind={kind} format={euros} />
    </div>
  );
}

export const ConFiltros: StoryObj = { render: () => <WithFilters /> };

export const AhorroConNegativos: StoryObj = {
  render: () => (
    <SeriesChart
      label="Lo que queda cada mes"
      labels={labels}
      series={[{ key: "net", name: "Te queda", values: [420, -130, 610, 90, 380, -40] }]}
      kind="bars"
      format={euros}
    />
  ),
};

export const PatrimonioConAportado: StoryObj = {
  render: () => (
    <SeriesChart
      label="Patrimonio por tipo, con lo aportado"
      labels={labels}
      kind="stacked"
      series={[
        { key: "cash", name: "Efectivo", values: [2400, 2900, 2300, 1600, 2600, 4000] },
        { key: "funds", name: "Fondos", values: [10600, 11700, 12200, 13100, 13800, 15400] },
      ]}
      overlay={{ key: "put", name: "Aportado", values: [12000, 13400, 13700, 14200, 15500, 17800] }}
      format={euros}
    />
  ),
};
