import { Button, ChoiceChips, Hint, Sheet } from "@openarga/ui";
import { useState } from "react";

export interface ConfirmStartSheetProps {
  name: string;
  detail: string;
  days?: { id: string; name: string; done: boolean }[];
  chosen?: string;
  onChoose?: (id: string) => void;
  onCancel: () => void;
  onStart: () => Promise<void>;
}

export function ConfirmStartSheet({ name, detail, days, chosen, onChoose, onCancel, onStart }: ConfirmStartSheetProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Sheet title={`¿Empezar ${name}?`} onClose={busy ? () => undefined : onCancel}>
      <Hint>{detail} El crono de la sesión empieza al confirmar.</Hint>
      {days && days.length > 1 && chosen && onChoose && (
        <ChoiceChips
          label="Otro día"
          value={chosen}
          onChange={onChoose}
          options={days.map((day) => ({ value: day.id, label: day.done ? `${day.name} ✓` : day.name }))}
        />
      )}
      {error && (
        <p className="training-field-error" role="alert">
          {error}
        </p>
      )}
      <div className="training-delete-actions">
        <Button variant="secondary" block onClick={onCancel} disabled={busy}>
          Cancelar
        </Button>
        <Button
          variant="primary"
          block
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setError(null);
            onStart().catch((reason: unknown) => {
              setError(reason instanceof Error ? reason.message : "No se ha podido empezar");
              setBusy(false);
            });
          }}
        >
          {busy ? "Empezando…" : `Empezar ${name}`}
        </Button>
      </div>
    </Sheet>
  );
}

export function rotationDetail(rotationNumber: number, day: number, days: number): string {
  return `Rotación ${rotationNumber}, día ${day} de ${days}.`;
}
