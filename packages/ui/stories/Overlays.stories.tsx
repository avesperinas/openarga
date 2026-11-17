import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import { Button, Dialog, Hint, IconButton, Menu, Popover, Sheet, TextField, Tooltip } from "../src/index";

const meta = { title: "Superposiciones", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

function Reopen({ label, children }: { label: string; children: (close: () => void) => React.ReactNode }) {
  const [open, setOpen] = React.useState(true);
  return (
    <>
      <Button onClick={() => setOpen(true)}>{label}</Button>
      {open && children(() => setOpen(false))}
    </>
  );
}

export const Dialogo: Story = {
  render: () => (
    <Reopen label="Leave?">
      {(close) => (
        <Dialog
          title="Leave without saving?"
          onClose={close}
          actions={[
            { label: "Seguir editando", onClick: close },
            { label: "Salir", onClick: close, tone: "danger" },
          ]}
        >
          What was written in the note is lost.
        </Dialog>
      )}
    </Reopen>
  ),
};

export const Hoja: Story = {
  render: () => (
    <Reopen label="Add">
      {(close) => (
        <Sheet title="Add to the list" onClose={close} action={{ label: "Add", onClick: close }}>
          <TextField label="What" value="Leche" onChange={() => undefined} />
          <Hint>Drag it down from the top to close it.</Hint>
        </Sheet>
      )}
    </Reopen>
  ),
};

export const MenuYGlobo: Story = {
  render: () => (
    <div style={{ display: "flex", gap: "var(--space-4)", alignItems: "center" }}>
      <Menu
        label="Book actions"
        items={[
          { label: "Editar", icon: "edit", onSelect: () => undefined },
          { label: "Duplicar", icon: "copy", onSelect: () => undefined },
          { label: "Borrar", icon: "trash", onSelect: () => undefined, tone: "danger" },
        ]}
      />
      <Popover
        label="Filtros"
        trigger={({ ref, ...props }) => (
          <Button ref={ref} icon="filter" {...props}>
            Filtros
          </Button>
        )}
      >
        <Hint>A popover for something small that does not deserve a sheet.</Hint>
      </Popover>
      <Tooltip label="Go to today">
        <IconButton icon="today" label="Today" />
      </Tooltip>
    </div>
  ),
};
