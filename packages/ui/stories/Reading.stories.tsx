import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import {
  Collapsible,
  DataTable,
  FlowMap,
  List,
  ListRow,
  MultiSelectField,
  SelectField,
  ShareChart,
  StatRow,
  StatTile,
} from "../src/index";

const meta: Meta = { title: "Gráficas/Leer con calma" };
export default meta;

const euros = (value: number) => `${Math.round(value).toLocaleString("es-ES")} €`;

export const Cifras: StoryObj = {
  render: () => (
    <StatRow label="Cómo vas">
      <StatTile
        label="Fondo de contingencia"
        value="3.000 €"
        foot="50 % de 6.000 € (6 meses)"
        tone="warning"
        progress={0.5}
      />
      <StatTile label="Patrimonio en 365 días" value="+6.500 €" foot="+32,5 % en un año" tone="positive" />
      <StatTile label="Tasa de ahorro" value="12 %" foot="60 % de la meta del 20 %" tone="warning" progress={0.6} />
    </StatRow>
  ),
};

export const Tabla: StoryObj = {
  render: () => (
    <DataTable
      label="Saldos"
      columns={[
        { key: "name", label: "Cuenta", cell: (row: { name: string; value: number }) => row.name },
        {
          key: "value",
          label: "Tuyo",
          numeric: true,
          cell: (row: { name: string; value: number }) => euros(row.value),
        },
      ]}
      rows={[
        { name: "Corriente", value: 1200 },
        { name: "Ahorro", value: 8000 },
        { name: "Fondo indexado", value: 15000 },
      ]}
      rowKey={(row) => row.name}
      onRowClick={() => undefined}
      footer={["Total", euros(24200)]}
    />
  ),
};

export const Quesito: StoryObj = {
  render: () => (
    <ShareChart
      label="Cómo se reparte"
      format={euros}
      items={[
        { key: "liquidity", name: "Liquidez", value: 9200 },
        { key: "investment", name: "Productos de inversión", value: 15000 },
        { key: "pension", name: "Plan de pensiones", value: 5000 },
      ]}
    />
  ),
};

export const CajasYFlechas: StoryObj = {
  render: () => (
    <FlowMap
      label="Flujos del mes"
      format={euros}
      nodes={[
        {
          id: "out",
          name: "Entra de fuera",
          kind: "income",
          group: "out",
          group_name: "Fuera",
          inflow: 0,
          outflow: 2400,
        },
        {
          id: "other",
          name: "Alguien",
          kind: "person",
          group: "other",
          group_name: "Alguien",
          inflow: 0,
          outflow: 700,
        },
        {
          id: "pay",
          name: "Nómina",
          kind: "account",
          group: "b1",
          group_name: "Banco Uno",
          inflow: 2400,
          outflow: 2300,
        },
        {
          id: "home",
          name: "Cuenta de casa",
          kind: "common",
          group: "b1",
          group_name: "Banco Uno",
          inflow: 1400,
          outflow: 1300,
        },
        { id: "save", name: "Ahorro", kind: "account", group: "b2", group_name: "Banco Dos", inflow: 900, outflow: 0 },
        {
          id: "spent",
          name: "Gastos",
          kind: "expense",
          group: "spent",
          group_name: "Gastos",
          inflow: 1300,
          outflow: 0,
        },
      ]}
      links={[
        { source: "out", target: "pay", value: 2400 },
        { source: "pay", target: "home", value: 700 },
        { source: "other", target: "home", value: 700 },
        { source: "pay", target: "save", value: 900 },
        { source: "home", target: "spent", value: 1300 },
        { source: "pay", target: "spent", value: 700 },
      ]}
    />
  ),
};

export const MenuPlegable: StoryObj = {
  render: () => {
    const [level, setLevel] = React.useState("bucket");
    return (
      <div style={{ display: "grid", gap: "12px" }}>
        <SelectField
          label="Agrupar por"
          options={[
            { value: "total", label: "Total" },
            { value: "bucket", label: "Liquidez, inversión, pensión" },
          ]}
          value={level}
          onChange={setLevel}
        />
        <Collapsible title="Cuentas y productos" subtitle="12 productos, sus fuentes y los bancos" defaultOpen>
          <List>
            <ListRow
              title="Corriente"
              subtitle="Banco Uno · Corriente"
              accessory="chevron-right"
              onClick={() => undefined}
            />
          </List>
        </Collapsible>
        <Collapsible title="Objetivos" subtitle="Fondo de contingencia, tasa de ahorro">
          <p>Dentro</p>
        </Collapsible>
      </div>
    );
  },
};

export const VariasALaVez: StoryObj = {
  render: function Render() {
    const [types, setTypes] = React.useState<string[]>(["funds"]);
    const [accounts, setAccounts] = React.useState<string[]>([]);
    return (
      <div style={{ display: "flex", gap: "8px", maxWidth: "28rem" }}>
        <MultiSelectField
          label="Tipo de producto"
          all="Todos los tipos"
          options={[
            { value: "cash", label: "Efectivo" },
            { value: "funds", label: "Fondos" },
            { value: "pension", label: "Pensión" },
          ]}
          values={types}
          onChange={setTypes}
        />
        <MultiSelectField
          label="Cuenta"
          all="Todas las cuentas"
          options={[
            { value: "a", label: "Corriente" },
            { value: "b", label: "Indexado" },
            { value: "c", label: "Plan de empleo" },
          ]}
          values={accounts}
          onChange={setAccounts}
        />
      </div>
    );
  },
};
