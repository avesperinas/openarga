import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import { Widget, WidgetDetail, WidgetRow, WidgetRows, WidgetValue } from "../src/index";
import "../widget.css";

const meta = {
  title: "Widget",
  component: Widget,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof Widget>;

export default meta;
type Story = StoryObj<typeof meta>;

const hace2h = new Date(Date.now() - 2 * 60 * 60 * 1000);

const base = { title: "● Eventos", hue: 1, size: "2x2", shape: "number" } as const;

export const Ready: Story = {
  args: { ...base, title: "Eventos", state: "ready" },
  render: (args) => (
    <Widget {...args}>
      <WidgetValue>1.284</WidgetValue>
      <WidgetDetail>12 hoy</WidgetDetail>
    </Widget>
  ),
};

export const Loading: Story = {
  args: { ...base, title: "Eventos", state: "loading" },
  render: (args) => <Widget {...args} />,
};

export const Empty: Story = {
  args: { ...base, title: "Entidades", state: "empty" },
  render: (args) => <Widget {...args} />,
};

export const Error: Story = {
  args: { ...base, title: "Entidades", state: "error", updatedAt: hace2h },
  render: (args) => (
    <Widget {...args} onRetry={() => {}}>
      <WidgetValue>47</WidgetValue>
    </Widget>
  ),
};

export const Disconnected: Story = {
  args: { ...base, title: "Sincronía", hue: 3, state: "disconnected" },
  render: (args) => <Widget {...args} onConnect={() => {}} />,
};

export const ConDuda: Story = {
  args: {
    ...base,
    title: "Alba Market",
    state: "ready",
    uncertainty: { summary: "puede faltar: 2 eventos en 1 entidad sin unir" },
  },
  render: (args) => (
    <div style={{ display: "flex", gap: "var(--grid-gap)", alignItems: "flex-start" }}>
      <Widget {...args} onExamineUncertainty={() => {}}>
        <WidgetValue>7</WidgetValue>
        <WidgetDetail>eventos</WidgetDetail>
      </Widget>
      <Widget
        {...args}
        title="Entidades por volumen"
        size="4x2"
        shape="list"
        onExamineUncertainty={() => {}}
      >
        <WidgetRows>
          <WidgetRow label="Mercadona" value="31 eventos" />
          <WidgetRow label="Alba Market" value="7 eventos" />
          <WidgetRow label="Bar Zurbano" value="4 eventos" />
        </WidgetRows>
      </Widget>
    </div>
  ),
};
