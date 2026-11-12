import {
  CheckChips,
  DateField,
  Hint,
  Sheet,
  Stepper,
  TextField,
} from "@openarga/ui";
import { useState } from "react";

import type { Idea, IdeaIn } from "./api";
import { MONTHS_SHORT, todayIso } from "./words";

const MONTH_OPTIONS = MONTHS_SHORT.map((label, index) => ({ value: String(index + 1), label }));

export function IdeaSheet({
  idea,
  onClose,
  onSave,
}: {
  idea: Idea | null;
  onClose: () => void;
  onSave: (data: IdeaIn) => Promise<void>;
}) {
  const [title, setTitle] = useState(idea?.title ?? "");
  const [budget, setBudget] = useState(idea?.budget_eur !== null && idea?.budget_eur !== undefined ? String(idea.budget_eur) : "");
  const [daysMin, setDaysMin] = useState<number | null>(idea?.days_min ?? null);
  const [daysMax, setDaysMax] = useState<number | null>(idea?.days_max ?? null);
  const [months, setMonths] = useState<string[]>((idea?.months ?? []).map(String));
  const [tags, setTags] = useState(idea?.tags.join(", ") ?? "");
  const [notes, setNotes] = useState(idea?.notes ?? "");
  const [busy, setBusy] = useState(false);
  const amount = budget.trim().replace(",", ".");
  const badBudget = amount !== "" && !/^\d+(\.\d{1,2})?$/.test(amount);
  const backwards = daysMin !== null && daysMax !== null && daysMax < daysMin;
  const ready = title.trim().length > 0 && !badBudget && !backwards && !busy;

  return (
    <Sheet
      title={idea ? "Editar idea" : "Nueva idea"}
      onClose={onClose}
      action={{
        label: idea ? "Guardar" : "Crear idea",
        disabled: !ready,
        onClick: () => {
          setBusy(true);
          void onSave({
            title: title.trim(),
            notes: notes.trim() || null,
            budget_eur: amount || null,
            days_min: daysMin,
            days_max: daysMax,
            months: months.map(Number),
            tags: tags
              .split(",")
              .map((one) => one.trim())
              .filter(Boolean),
          }).finally(() => setBusy(false));
        },
      }}
    >
      <div className="travel-sheet-stack">
        <TextField label="Título" value={title} onChange={setTitle} placeholder="Japón en otoño" autoFocus />
        <TextField
          label="Presupuesto por persona, en euros"
          inputMode="decimal"
          value={budget}
          onChange={setBudget}
          invalid={badBudget}
          hint={badBudget ? "Un importe como 900 o 900,50" : undefined}
        />
        <div className="travel-form-row">
          <div className="travel-field">
            <span className="travel-field-label">Días, como poco</span>
            <Stepper label="Días como poco" value={daysMin} onChange={setDaysMin} min={1} max={365} step={1} />
          </div>
          <div className="travel-field">
            <span className="travel-field-label">Como mucho</span>
            <Stepper label="Días como mucho" value={daysMax} onChange={setDaysMax} min={1} max={365} step={1} />
          </div>
        </div>
        {backwards && <Hint tone="warning">Como mucho no puede ser menos que como poco.</Hint>}
        <CheckChips label="Meses buenos" values={months} onChange={setMonths} options={MONTH_OPTIONS} />
        <TextField label="Etiquetas" value={tags} onChange={setTags} hint="Separadas por comas" />
        <TextField label="Notas" value={notes} onChange={setNotes} />
      </div>
    </Sheet>
  );
}

export function PlanSheet({
  idea,
  onClose,
  onPlan,
}: {
  idea: Idea;
  onClose: () => void;
  onPlan: (plan: { starts_on: string; ends_on: string; travellers: number }) => Promise<void>;
}) {
  const [starts, setStarts] = useState("");
  const [ends, setEnds] = useState("");
  const [travellers, setTravellers] = useState<number | null>(1);
  const [busy, setBusy] = useState(false);
  const backwards = Boolean(starts && ends && ends < starts);
  const ready = Boolean(starts && ends) && !backwards && !busy;

  return (
    <Sheet
      title="Pasar a plan"
      onClose={onClose}
      action={{
        label: "Crear el plan",
        disabled: !ready,
        onClick: () => {
          setBusy(true);
          void onPlan({ starts_on: starts, ends_on: ends, travellers: travellers ?? 1 }).finally(() => setBusy(false));
        },
      }}
    >
      <div className="travel-sheet-stack">
        <Hint>
          Un viaje en plan, con fechas que aún pueden moverse. Sus {idea.places.length} destino(s) esperan en «Sin día» para
          colocarlos.
        </Hint>
        <div className="travel-form-row">
          <DateField label="Primer día" value={starts} onChange={setStarts} min={todayIso()} />
          <DateField
            label="Último día"
            value={ends}
            onChange={setEnds}
            invalid={backwards}
            hint={backwards ? "Acaba antes de empezar" : undefined}
          />
        </div>
        <div className="travel-field">
          <span className="travel-field-label">Viajeros</span>
          <Stepper label="Viajeros" value={travellers} onChange={setTravellers} min={1} max={50} step={1} />
        </div>
      </div>
    </Sheet>
  );
}
