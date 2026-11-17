import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../library.css";
import {
  AppHeader,
  CreateButton,
  EmptyState,
  GroupLabel,
  Heading,
  Hint,
  List,
  ListRow,
  Notice,
  Screen,
  SearchField,
  Section,
} from "../src/index";

const meta = { title: "Pantalla", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const ICON =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="22" fill="#2b3a4a"/><circle cx="50" cy="50" r="22" fill="#e8e4db"/></svg>',
  );
const APP = { id: "demo", name: "Demo", icon: ICON };

export const Completa: Story = {
  render: function Render() {
    const [query, setQuery] = React.useState("");
    return (
      <Screen>
        <AppHeader app={APP} eyebrow="Tuesday 22 October" title="Your list" />
        <SearchField label="Search Demo" placeholder="Buscar" value={query} onChange={setQuery} />
        <Notice tone="warning" title="Access expires in 5 days" action={{ label: "Renovar", onClick: () => undefined }}>
          Without renewing it, movements stop arriving.
        </Notice>
        <Section title="Pendiente" count={2} action={{ label: "Ver todo", onClick: () => undefined }}>
          <List>
            <ListRow title="A synthetic thing" subtitle="tomorrow" accessory="chevron-right" onClick={() => undefined} />
            <ListRow title="Another synthetic thing" subtitle="on Thursday" accessory="chevron-right" onClick={() => undefined} />
          </List>
        </Section>
        <Heading count={1}>Hecho</Heading>
        <GroupLabel>This week</GroupLabel>
        <Hint>Done items are kept for a week.</Hint>
        <CreateButton label="Cosa" onClick={() => undefined} />
      </Screen>
    );
  },
};

export const Vacia: Story = {
  render: () => (
    <Screen>
      <AppHeader app={APP} title="Your list" />
      <EmptyState icon="list" title="Nothing yet" action={{ label: "Add the first one", onClick: () => undefined, icon: "plus" }}>
        What you add shows here, the soonest on top.
      </EmptyState>
    </Screen>
  ),
};

export const TextoEscritoAMano: Story = {
  render: () => (
    <Screen>
      <AppHeader app={APP} title="Trip notes" />
      <Hint lines>{"Bring the adapter.\nThe museum closes on Mondays.\nBook Saturday's dinner."}</Hint>
    </Screen>
  ),
};
