import type { Meta, StoryObj } from "@storybook/react";

import "../library.css";
import { AppBackdrop, AppHeader, AppSettings, List, ListRow, Screen, Section } from "../src/index";

const meta = { title: "Fondo de una app", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const APP = { id: "training", name: "Training", icon: "/favicon.svg" };

export const Pantalla: Story = {
  render: () => (
    <AppBackdrop app="training">
      <Screen>
        <AppHeader app={APP} eyebrow="Viernes, 30 de octubre" title="Hoy" />
        <Section title="Esta semana">
          <List>
            <ListRow title="Pierna" subtitle="Lunes · 52 min" accessory="chevron-right" onClick={() => undefined} />
            <ListRow title="Empuje" subtitle="Miércoles · 47 min" accessory="chevron-right" onClick={() => undefined} />
            <ListRow title="Tirón" subtitle="Hoy" accessory="chevron-right" onClick={() => undefined} />
          </List>
        </Section>
      </Screen>
    </AppBackdrop>
  ),
};

export const Ajustes: Story = {
  render: () => (
    <AppBackdrop app="training">
      <AppSettings app={APP} />
    </AppBackdrop>
  ),
};
