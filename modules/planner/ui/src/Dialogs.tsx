import { Button, CheckChips, SegmentedControl, Sheet, TONES, TextField, type Tone, useNow } from "@openarga/ui";
import * as React from "react";

import type { Display, Layer, Scope } from "./api";
import { statusLine } from "./Subscribe";

const SCOPES: Record<Scope, { edit: string; cancel: string }> = {
  this: { edit: "Solo este", cancel: "Solo este" },
  following: { edit: "Este y los siguientes", cancel: "Este y los siguientes" },
  all: { edit: "Todos", cancel: "Todos" },
};

export interface ScopeQuestion {
  question: "edit" | "cancel";
  allowed: Scope[];
  resolve: (scope: Scope | null) => void;
}

export function ScopeDialog({ ask }: { ask: ScopeQuestion }) {
  const close = React.useCallback(() => ask.resolve(null), [ask]);
  return (
    <Sheet title={ask.question === "edit" ? "Es un evento que se repite" : "¿Cancelar un evento que se repite?"} onClose={close}>
      <p className="cr-sheet-note">
        {ask.question === "edit" ? "¿A cuáles se aplica el cambio?" : "Lo cancelado deja de verse; no se borra."}
      </p>
      <div className="cr-scope">
        {ask.allowed.map((scope, index) => (
          <Button
            key={scope}
            block
            variant={ask.question === "cancel" ? "destructive" : index === 0 ? "primary" : "secondary"}
            autoFocus={index === 0}
            onClick={() => ask.resolve(scope)}
          >
            {SCOPES[scope][ask.question]}
          </Button>
        ))}
        <Button block variant="plain" onClick={close}>
          {ask.question === "edit" ? "No cambiar nada" : "No cancelar"}
        </Button>
      </div>
    </Sheet>
  );
}

const DISPLAYS: { value: Display; label: string }[] = [
  { value: "events", label: "Eventos" },
  { value: "background", label: "Fondo" },
];

export function LayerSheet({
  layer,
  layers,
  onClose,
  onSave,
}: {
  layer: Layer | null;
  layers: Layer[];
  onClose: () => void;
  onSave: (name: string, tone: Tone, display: Display, daysOffFrom: string[]) => Promise<void>;
}) {
  const [name, setName] = React.useState(layer?.name ?? "");
  const [tone, setTone] = React.useState<Tone>((layer?.tone as Tone) ?? 5);
  const [display, setDisplay] = React.useState<Display>(layer?.display ?? "events");
  const [daysOffFrom, setDaysOffFrom] = React.useState<string[]>(layer?.days_off_from ?? []);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const now = useNow(60_000);
  const subscribed = layer?.origin === "subscription";
  const own = !layer || layer.origin === "own";
  const offSources = layers.filter((one) => one.id !== layer?.id && one.origin !== "app");
  const save = async () => {
    if (!name.trim()) {
      setError("Ponle un nombre.");
      return;
    }
    setBusy(true);
    try {
      await onSave(name.trim(), tone, display, daysOffFrom.filter((id) => offSources.some((one) => one.id === id)));
      onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet
      title={subscribed ? "Suscripción" : layer?.origin === "app" ? "Capa de una app" : layer ? "Capa" : "Nueva capa"}
      onClose={onClose}
      action={{ label: busy ? "Guardando…" : layer ? "Guardar" : "Crear capa", onClick: () => void save(), disabled: busy }}
    >
      <TextField label="Nombre" value={name} placeholder="Trabajo, Familia, Deporte…" autoFocus onChange={setName} onSubmit={() => void save()} invalid={!!error} hint={error ?? undefined} />
      <div className="cr-tones" role="radiogroup" aria-label="Tono">
        {TONES.map((one) => (
          <button
            key={one.tone}
            type="button"
            role="radio"
            aria-checked={tone === one.tone}
            aria-label={one.name}
            title={one.name}
            className="cr-tone"
            data-tone={one.tone}
            onClick={() => setTone(one.tone)}
          />
        ))}
      </div>
      <div className="cr-display">
        <span className="cr-display-label">Se ve como</span>
        <SegmentedControl label="Se ve como" options={DISPLAYS} value={display} onChange={setDisplay} />
        <p className="cr-sheet-note">
          {display === "background"
            ? "El marco en el que caen los eventos, como el horario laboral o un viaje: tiñe su tramo y los eventos van encima. No cuenta como ocupado ni sale en lo próximo."
            : "Cada evento ocupa su hueco en la rejilla."}
        </p>
      </div>
      {own && offSources.length > 0 && (
        <div className="cr-display">
          <span className="cr-display-label">Días libres</span>
          <CheckChips
            label="Días libres"
            options={offSources.map((one) => ({ value: one.id, label: one.name }))}
            values={daysOffFrom}
            onChange={setDaysOffFrom}
          />
          <p className="cr-sheet-note">
            Lo que se repite en esta capa no sale los días que estas tienen algo de todo el día: tu jornada, un festivo o
            unas vacaciones. Lo que pongas a mano ese día sí sale.
          </p>
        </div>
      )}
      {layer?.origin === "app" && (
        <p className="cr-sheet-note">Se llena sola con lo que tiene fecha en la app. Lo suyo se cambia allí.</p>
      )}
      {subscribed && layer && (
        <div className="cr-subscription-foot">
          <p className="cr-sheet-note" data-failing={layer.subscription?.failing || undefined}>
            {statusLine(layer, now)}. Lo suscrito se actualiza solo y no se edita.
          </p>
          {layer.connection_id && (
            <a className="cr-link" href={`/hub/${layer.connection_id}`}>
              Ver en Hub: pausarla o ver cada pasada. Se quita en Suscripciones
            </a>
          )}
        </div>
      )}
    </Sheet>
  );
}
