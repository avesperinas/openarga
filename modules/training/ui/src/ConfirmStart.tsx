import { Button, ChoiceChips, Hint, Sheet, type Translate, useT } from "@openarga/ui";
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
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Sheet title={t("start.title", { name })} onClose={busy ? () => undefined : onCancel}>
      <Hint>{t("start.hint", { detail })}</Hint>
      {days && days.length > 1 && chosen && onChoose && (
        <ChoiceChips
          label={t("today.other_day")}
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
          {t("common.cancel")}
        </Button>
        <Button
          variant="primary"
          block
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setError(null);
            onStart().catch((reason: unknown) => {
              setError(reason instanceof Error ? reason.message : t("activity.start_failed"));
              setBusy(false);
            });
          }}
        >
          {busy ? t("start.starting") : t("today.start_named", { name })}
        </Button>
      </div>
    </Sheet>
  );
}

export function rotationDetail(t: Translate, rotationNumber: number, day: number, days: number): string {
  return t("start.rotation", { rotation: rotationNumber, day, days });
}
