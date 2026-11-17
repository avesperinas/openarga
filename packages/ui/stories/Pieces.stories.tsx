import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import { Avatar, Badge, Combobox, DateRangeField, FileField, Tabs } from "../src/index";

const meta = { title: "Piezas", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="glass" style={{ display: "grid", gap: "var(--space-4)", width: "min(26rem, 100%)", boxSizing: "border-box", padding: "var(--space-6)" }}>
      {children}
    </div>
  );
}

export const Pestanas: Story = {
  render: function Render() {
    const [active, setActive] = React.useState<"summary" | "moves" | "budget">("moves");
    return (
      <Panel>
        <Tabs
          label="Vistas"
          active={active}
          onSelect={setActive}
          items={[
            { id: "summary", label: "Resumen" },
            { id: "moves", label: "Movimientos", count: 12 },
            { id: "budget", label: "Presupuesto" },
          ]}
        />
      </Panel>
    );
  },
};

export const CarasYEtiquetas: Story = {
  render: () => (
    <Panel>
      <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center" }}>
        <Avatar name="Synthetic Person" size="s" />
        <Avatar name="Otra Persona" />
        <Avatar name="Someone Else" size="l" />
      </div>
      <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
        <Badge>3</Badge>
        <Badge tone="accent">Nuevo</Badge>
        <Badge tone="warning">Caduca</Badge>
        <Badge tone="positive">Hecho</Badge>
        <Badge tone="negative">Suspendida</Badge>
      </div>
    </Panel>
  ),
};

export const Campos: Story = {
  render: function Render() {
    const [country, setCountry] = React.useState<string | null>("jp");
    const [range, setRange] = React.useState({ from: "2026-10-01", to: "2026-10-14" });
    return (
      <Panel>
        <Combobox
          label="Country"
          value={country}
          onChange={setCountry}
          create={(text) => `Add “${text}”`}
          options={[
            { value: "es", label: "Spain" },
            { value: "fr", label: "Francia" },
            { value: "jp", label: "Japan" },
          ]}
        />
        <DateRangeField label="Trip dates" value={range} onChange={setRange} />
        <FileField label="Upload the PDF" accept="application/pdf" hint="A PDF of up to 10 MB." onFiles={() => undefined} />
      </Panel>
    );
  },
};
