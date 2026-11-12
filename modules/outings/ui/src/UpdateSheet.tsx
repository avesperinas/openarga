import { Button, Hint, Sheet } from "@openarga/ui";
import { useState } from "react";

import { readAgendaPrompt } from "./api";

export function UpdateSheet({ onClose }: { onClose: () => void }) {
  const [said, setSaid] = useState<{ tone?: "warning"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function copy() {
    setBusy(true);
    try {
      const { prompt } = await readAgendaPrompt();
      await navigator.clipboard.writeText(prompt);
      setSaid({ text: "Copiado. Pégalo en Claude Code o en Claude con arga conectado: buscará y lo apuntará aquí." });
    } catch (error) {
      setSaid({ tone: "warning", text: error instanceof Error ? error.message : "No se ha podido copiar." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet title="Actualizar la agenda" onClose={onClose}>
      <div className="outings-fields">
        <Hint>
          La agenda la llena tu Claude, con tu suscripción. Una tarea programada lo hace cada semana; para hacerlo ya,
          copia el encargo y pégaselo.
        </Hint>
        <Button variant="primary" icon="copy" onClick={() => void copy()} disabled={busy}>
          Buscar con Claude
        </Button>
        {said && <Hint tone={said.tone}>{said.text}</Hint>}
      </div>
    </Sheet>
  );
}
