"use client";

import { Button, Hint, Section } from "@openarga/ui";
import * as React from "react";

import type { DesktopLayout, Device } from "../lib/kernel";
import { request } from "../lib/session";
import { currentDevice } from "./Editable";

const DESKTOPS = "/api/kernel/ui/desktops";

type State = "idle" | "asking" | "working" | "failed";

const NAMES: Record<Device, string> = { mobile: "del móvil", desktop: "del ordenador" };

export function StartingDesk({ reload = () => globalThis.location.reload() }: { reload?: () => void }) {
  const [state, setState] = React.useState<State>("idle");
  const [device, setDevice] = React.useState<Device>("mobile");

  React.useEffect(() => setDevice(currentDevice()), []);

  const replace = async () => {
    setState("working");
    try {
      const [starting, current] = await Promise.all(
        [`${DESKTOPS}/starting`, DESKTOPS].map(async (url) => {
          const response = await request(url, { headers: { accept: "application/json" } });
          if (!response.ok) throw new Error(`${url} respondió ${response.status}`);
          return (await response.json()) as Record<Device, DesktopLayout>;
        }),
      );
      const proposed = starting![device];
      const written = await request(`${DESKTOPS}/${device}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          pages: proposed.pages,
          placements: {},
          updated_at: current![device].updated_at ?? null,
        }),
      });
      if (!written.ok) throw new Error(`el escritorio respondió ${written.status}`);
      reload();
    } catch {
      setState("failed");
    }
  };

  return (
    <Section title="Escritorio">
      <Hint>
        El de partida tiene cuatro pantallas: Hoy (agenda, tareas y el uso de Claude), Salud, Dinero y
        Más. Es distinto en el móvil y en el ordenador.
      </Hint>
      {state === "asking" || state === "working" ? (
        <>
          <Hint>
            Sustituye las pantallas y los widgets {NAMES[device]} por los de partida. Lo que tengas
            colocado ahora {NAMES[device]} no se puede recuperar; el otro dispositivo no cambia.
          </Hint>
          <div className="settings-actions">
            <Button variant="destructive" disabled={state === "working"} onClick={replace}>
              Sustituir
            </Button>
            <Button disabled={state === "working"} onClick={() => setState("idle")}>
              Cancelar
            </Button>
          </div>
        </>
      ) : (
        <div className="settings-actions">
          <Button icon="undo" onClick={() => setState("asking")}>
            Usar el de partida {NAMES[device]}
          </Button>
        </div>
      )}
      {state === "failed" && <Hint>No se pudo cambiar. Vuelve a intentarlo en un momento.</Hint>}
    </Section>
  );
}
