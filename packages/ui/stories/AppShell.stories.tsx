import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../library.css";
import { AppShell, List, ListRow, Screen, SETTINGS_TAB, Heading, Hint } from "../src/index";

const meta = { title: "Armazón", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const BOOKS = ["Un libro sintético", "Otro libro", "El tercero"];

function Shell({ startOpen }: { startOpen: boolean }) {
  const [tab, setTab] = React.useState<"shelf" | "stats" | "settings">("shelf");
  const [open, setOpen] = React.useState<string | null>(startOpen ? BOOKS[0]! : null);
  return (
    <AppShell
      label="Secciones"
      active={tab}
      onSelect={setTab}
      tabs={[
        { id: "shelf", label: "Estantería", icon: "book" },
        { id: "stats", label: "Estadísticas", icon: "chart" },
        SETTINGS_TAB,
      ]}
      detail={
        open && (
          <Screen>
            <Heading>{open}</Heading>
            <Hint>La ficha, al lado de la lista en ancho.</Hint>
          </Screen>
        )
      }
    >
      <Screen>
        <Heading>Tus libros</Heading>
        <List>
          {BOOKS.map((book) => (
            <ListRow key={book} title={book} accessory="chevron-right" onClick={() => setOpen(book)} />
          ))}
        </List>
      </Screen>
    </AppShell>
  );
}

export const Lista: Story = { render: () => <Shell startOpen={false} /> };
export const ConDetalle: Story = { render: () => <Shell startOpen /> };

function Bare() {
  const [open, setOpen] = React.useState<string | null>(BOOKS[0]!);
  return (
    <AppShell
      detailLabel="Libro"
      detail={
        open && (
          <Screen>
            <Heading>{open}</Heading>
            <Hint>El detalle, sin rail a la izquierda.</Hint>
          </Screen>
        )
      }
    >
      <Screen>
        <Heading>Tus libros</Heading>
        <List>
          {BOOKS.map((book) => (
            <ListRow key={book} title={book} accessory="chevron-right" onClick={() => setOpen(book)} />
          ))}
        </List>
      </Screen>
    </AppShell>
  );
}

export const SinSecciones: Story = { render: () => <Bare /> };
