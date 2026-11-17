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
import { monthShort, todayIso } from "./words";
import { plural, t } from "./lang";

const monthOptions = () => Array.from({ length: 12 }, (_, index) => ({ value: String(index + 1), label: monthShort(index + 1) }));

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
      title={idea ? t("idea.edit") : t("idea.new")}
      onClose={onClose}
      action={{
        label: idea ? t("action.save") : t("idea.create"),
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
        <TextField label={t("editor.title")} value={title} onChange={setTitle} placeholder={t("idea.title_example")} autoFocus />
        <TextField
          label={t("editor.budget")}
          inputMode="decimal"
          value={budget}
          onChange={setBudget}
          invalid={badBudget}
          hint={badBudget ? t("editor.budget_invalid") : undefined}
        />
        <div className="travel-form-row">
          <div className="travel-field">
            <span className="travel-field-label">{t("idea.days_min")}</span>
            <Stepper label={t("idea.days_min")} value={daysMin} onChange={setDaysMin} min={1} max={365} step={1} />
          </div>
          <div className="travel-field">
            <span className="travel-field-label">{t("idea.days_max")}</span>
            <Stepper label={t("idea.days_max_label")} value={daysMax} onChange={setDaysMax} min={1} max={365} step={1} />
          </div>
        </div>
        {backwards && <Hint tone="warning">{t("idea.days_backwards")}</Hint>}
        <CheckChips label={t("idea.months")} values={months} onChange={setMonths} options={monthOptions()} />
        <TextField label={t("trip.tags")} value={tags} onChange={setTags} hint={t("editor.comma_separated")} />
        <TextField label={t("editor.notes")} value={notes} onChange={setNotes} />
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
      title={t("idea.to_plan")}
      onClose={onClose}
      action={{
        label: t("idea.create_plan"),
        disabled: !ready,
        onClick: () => {
          setBusy(true);
          void onPlan({ starts_on: starts, ends_on: ends, travellers: travellers ?? 1 }).finally(() => setBusy(false));
        },
      }}
    >
      <div className="travel-sheet-stack">
        <Hint>
          {t("idea.plan_hint", { places: plural(idea.places.length, "count.destinations") })}
        </Hint>
        <div className="travel-form-row">
          <DateField label={t("editor.first_day")} value={starts} onChange={setStarts} min={todayIso()} />
          <DateField
            label={t("editor.last_day")}
            value={ends}
            onChange={setEnds}
            invalid={backwards}
            hint={backwards ? t("editor.backwards") : undefined}
          />
        </div>
        <div className="travel-field">
          <span className="travel-field-label">{t("trip.kpi.travellers")}</span>
          <Stepper label={t("trip.kpi.travellers")} value={travellers} onChange={setTravellers} min={1} max={50} step={1} />
        </div>
      </div>
    </Sheet>
  );
}
