import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

const meta = {
  title: "Material",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

function Card({ className, title, detail }: { className: string; title: string; detail: string }) {
  return (
    <div className={className} style={{ padding: "var(--space-3)", width: 173, height: 173 }}>
      <p
        style={{
          margin: 0,
          fontSize: "var(--text-caption)",
          color: "var(--fg-muted)",
        }}
      >
        {title}
      </p>
      <p
        style={{
          margin: "var(--space-4) 0 0",
          fontSize: "var(--text-display)",
          lineHeight: "var(--leading-tight)",
          letterSpacing: "var(--tracking-display)",
          fontVariantNumeric: "var(--numeric)",
        }}
      >
        1.284
      </p>
      <p style={{ margin: 0, fontSize: "var(--text-caption)", color: "var(--fg-muted)" }}>
        {detail}
      </p>
    </div>
  );
}

export const Tarjeta: Story = {
  render: () => (
    <div style={{ display: "flex", gap: "var(--grid-gap)" }}>
      <Card className="surface" title="● Eventos" detail="12 hoy" />
      <Card className="surface" title="● Entidades" detail="3 esta semana" />
    </div>
  ),
};

export const Cristal: Story = {
  render: () => (
    <div style={{ display: "grid", gap: "var(--space-6)", justifyItems: "start" }}>
      <Card className="surface" title="● Eventos" detail="12 hoy" />
      <div
        className="glass"
        style={{
          padding: "var(--space-3) var(--space-6)",
          display: "flex",
          gap: "var(--space-6)",
          fontSize: "var(--text-caption)",
          marginTop: -80,
          marginLeft: "var(--space-8)",
        }}
      >
        <span style={{ color: "var(--accent)" }}>Hoy</span>
        <span style={{ color: "var(--fg-muted)" }}>Módulos</span>
        <span style={{ color: "var(--fg-muted)" }}>Ajustes</span>
      </div>
    </div>
  ),
};

export const CantoSobreTarjeta: Story = { ...Cristal };
