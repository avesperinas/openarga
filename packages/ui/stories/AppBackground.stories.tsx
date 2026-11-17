import type { Meta, StoryObj } from "@storybook/react";

import "../library.css";
import { AppBackdrop, AppHeader, AppSettings, List, ListRow, Screen, Section } from "../src/index";

const meta = { title: "An app's background", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const APP = { id: "training", name: "Training", icon: "/favicon.svg" };

export const Pantalla: Story = {
  render: () => (
    <AppBackdrop app="training">
      <Screen>
        <AppHeader app={APP} eyebrow="Friday 30 October" title="Today" />
        <Section title="This week">
          <List>
            <ListRow title="Pierna" subtitle="Lunes · 52 min" accessory="chevron-right" onClick={() => undefined} />
            <ListRow title="Empuje" subtitle="Wednesday · 47 min" accessory="chevron-right" onClick={() => undefined} />
            <ListRow title="Pull" subtitle="Today" accessory="chevron-right" onClick={() => undefined} />
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
