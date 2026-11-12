import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";

import "../library.css";
import { Button, EmptyState, ErrorState, OfflineNotice, ToastHost, useToast } from "../src/index";

const meta = { title: "Estados", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

const column = { display: "grid", gap: "var(--space-4)", width: "min(26rem, 100%)" } as const;

export const VacioErrorYSinRed: Story = {
  render: () => (
    <div style={column}>
      <OfflineNotice offline pending={2} />
      <EmptyState icon="basket" title="No hay nada apuntado" action={{ label: "Apuntar algo", onClick: () => undefined, icon: "plus" }}>
        Escribe arriba lo que haga falta.
      </EmptyState>
      <ErrorState detail="El servicio no ha contestado." onRetry={() => new Promise((resolve) => setTimeout(resolve, 800))} />
    </div>
  ),
};

function Fire() {
  const toast = useToast();
  React.useEffect(() => toast({ message: "Quitado · Leche", action: { label: "Deshacer", run: () => undefined } }), [toast]);
  return <Button onClick={() => toast({ message: "Hecho · Vacuna" })}>Otro aviso</Button>;
}

export const Aviso: Story = {
  render: () => (
    <ToastHost>
      <Fire />
    </ToastHost>
  ),
};
