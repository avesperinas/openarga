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

const meta: Meta = { title: "Charts/Read calmly" };
export default meta;

const euros = (value: number) => `${Math.round(value).toLocaleString("en-GB")} €`;

export const Cifras: StoryObj = {
  render: () => (
    <StatRow label="How you are doing">
      <StatTile
        label="Emergency fund"
        value="3.000 €"
        foot="50 % of €6,000 (6 months)"
        tone="warning"
        progress={0.5}
      />
      <StatTile label="Net worth over 365 days" value="+6.500 €" foot="+32.5 % in a year" tone="positive" />
      <StatTile label="Savings rate" value="12 %" foot="60 % of the 20 % goal" tone="warning" progress={0.6} />
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
      label="How it is split"
      format={euros}
      items={[
        { key: "liquidity", name: "Liquidez", value: 9200 },
        { key: "investment", name: "Investment products", value: 15000 },
        { key: "pension", name: "Pension plan", value: 5000 },
      ]}
    />
  ),
};

export const CajasYFlechas: StoryObj = {
  render: () => (
    <FlowMap
      label="The month's flows"
      format={euros}
      nodes={[
        {
          id: "out",
          name: "Comes in from outside",
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
          name: "Salary",
          kind: "account",
          group: "b1",
          group_name: "Banco Uno",
          inflow: 2400,
          outflow: 2300,
        },
        {
          id: "home",
          name: "Household account",
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
          label="Group by"
          options={[
            { value: "total", label: "Total" },
            { value: "bucket", label: "Cash, investment, pension" },
          ]}
          value={level}
          onChange={setLevel}
        />
        <Collapsible title="Accounts and products" subtitle="12 products, their sources and the banks" defaultOpen>
          <List>
            <ListRow
              title="Corriente"
              subtitle="Banco Uno · Corriente"
              accessory="chevron-right"
              onClick={() => undefined}
            />
          </List>
        </Collapsible>
        <Collapsible title="Objetivos" subtitle="Emergency fund, savings rate">
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
          label="Product kind"
          all="All kinds"
          options={[
            { value: "cash", label: "Efectivo" },
            { value: "funds", label: "Fondos" },
            { value: "pension", label: "Pension" },
          ]}
          values={types}
          onChange={setTypes}
        />
        <MultiSelectField
          label="Cuenta"
          all="All accounts"
          options={[
            { value: "a", label: "Corriente" },
            { value: "b", label: "Indexado" },
            { value: "c", label: "Workplace pension" },
          ]}
          values={accounts}
          onChange={setAccounts}
        />
      </div>
    );
  },
};
