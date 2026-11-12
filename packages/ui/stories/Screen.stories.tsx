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
        <AppHeader app={APP} eyebrow="Martes, 22 de octubre" title="Tu lista" />
        <SearchField label="Buscar en Demo" placeholder="Buscar" value={query} onChange={setQuery} />
        <Notice tone="warning" title="El acceso caduca en 5 días" action={{ label: "Renovar", onClick: () => undefined }}>
          Sin renovarlo, dejan de llegar los movimientos.
        </Notice>
        <Section title="Pendiente" count={2} action={{ label: "Ver todo", onClick: () => undefined }}>
          <List>
            <ListRow title="Una cosa sintética" subtitle="mañana" accessory="chevron-right" onClick={() => undefined} />
            <ListRow title="Otra cosa sintética" subtitle="el jueves" accessory="chevron-right" onClick={() => undefined} />
          </List>
        </Section>
        <Heading count={1}>Hecho</Heading>
        <GroupLabel>Esta semana</GroupLabel>
        <Hint>Lo hecho se guarda una semana.</Hint>
        <CreateButton label="Cosa" onClick={() => undefined} />
      </Screen>
    );
  },
};

export const Vacia: Story = {
  render: () => (
    <Screen>
      <AppHeader app={APP} title="Tu lista" />
      <EmptyState icon="list" title="Todavía no hay nada" action={{ label: "Añadir la primera", onClick: () => undefined, icon: "plus" }}>
        Lo que añadas sale aquí, lo más próximo arriba.
      </EmptyState>
    </Screen>
  ),
};

export const TextoEscritoAMano: Story = {
  render: () => (
    <Screen>
      <AppHeader app={APP} title="Notas del viaje" />
      <Hint lines>{"Llevar el adaptador.\nEl museo cierra los lunes.\nReservar la cena del sábado."}</Hint>
    </Screen>
  ),
};
