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
    <Reopen label="¿Salir?">
      {(close) => (
        <Dialog
          title="¿Salir sin guardar?"
          onClose={close}
          actions={[
            { label: "Seguir editando", onClick: close },
            { label: "Salir", onClick: close, tone: "danger" },
          ]}
        >
          Lo escrito en la nota se pierde.
        </Dialog>
      )}
    </Reopen>
  ),
};

export const Hoja: Story = {
  render: () => (
    <Reopen label="Añadir">
      {(close) => (
        <Sheet title="Añadir a la lista" onClose={close} action={{ label: "Añadir", onClick: close }}>
          <TextField label="Qué" value="Leche" onChange={() => undefined} />
          <Hint>Arrástrala hacia abajo desde arriba para cerrarla.</Hint>
        </Sheet>
      )}
    </Reopen>
  ),
};

export const MenuYGlobo: Story = {
  render: () => (
    <div style={{ display: "flex", gap: "var(--space-4)", alignItems: "center" }}>
      <Menu
        label="Acciones del libro"
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
        <Hint>Un globo para algo pequeño que no merece una hoja.</Hint>
      </Popover>
      <Tooltip label="Ir a hoy">
        <IconButton icon="today" label="Hoy" />
      </Tooltip>
    </div>
  ),
};
