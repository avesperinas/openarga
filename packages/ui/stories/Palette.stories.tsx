import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../calendar.css";
import { Button, CommandPalette, matching, useShortcut } from "../src/index";

const meta = { title: "Paleta", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const COMMANDS = [
  { key: "today", label: "Go to today", icon: "today" as const, shortcut: "T", run: () => undefined },
  { key: "week", label: "See the week", icon: "calendar" as const, shortcut: "W", run: () => undefined },
  { key: "new", label: "Nuevo evento", icon: "plus" as const, shortcut: "N", run: () => undefined },
];
const NOTES = [
  { key: "n1", label: "Ideas for the trip", detail: "Viajes", icon: "note" as const, run: () => undefined },
  { key: "n2", label: "Reading list", detail: "Libros", icon: "note" as const, run: () => undefined },
];

export const Abierta: Story = {
  render: function Render() {
    const [open, setOpen] = React.useState(true);
    const [query, setQuery] = React.useState("");
    useShortcut("k", () => setOpen(true));
    return (
      <>
        <Button onClick={() => setOpen(true)}>Abrir (⌘K)</Button>
        {open && (
          <CommandPalette
            label="Search and commands"
            placeholder="What you want to do, or a note"
            query={query}
            onQuery={setQuery}
            onClose={() => setOpen(false)}
            groups={[
              { label: "Comandos", items: matching(COMMANDS, query) },
              { label: "Notas", items: matching(NOTES, query) },
            ]}
          />
        )}
      </>
    );
  },
};

const EVENTS = [
  { key: "e1", label: "Dinner with Ane", detail: "jue, 29 oct · 21:00 · Casa", tone: 5, run: () => undefined },
  { key: "e2", label: "English", detail: "Wed, 28 Oct · 19:00", tone: 3, icon: "repeat" as const, run: () => undefined },
];

export const ConEventos: Story = {
  render: function Render() {
    const [query, setQuery] = React.useState("");
    return (
      <CommandPalette
        label="Search and commands"
        placeholder="Search events or type a command"
        query={query}
        onQuery={setQuery}
        onClose={() => undefined}
        groups={[
          { label: "Eventos", items: EVENTS },
          { label: "Comandos", items: matching(COMMANDS, query) },
        ]}
      />
    );
  },
};
