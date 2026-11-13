import { ConfirmPanel, Hint, Sheet, TextField, useT } from "@openarga/ui";
import { useState } from "react";

import { type Entry, type Meal, menuFromMeal, moveMeal, removeMeal, repeatMeal } from "./api";
import { clockOf, mealLine, plural, todayIso } from "./words";

export type MealStep = "repeat" | "time" | "menu" | "delete";

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

export function menuName(meal: Pick<Meal, "label">, entries: Entry[]): string {
  const said = entries.find((entry) => entry.said)?.said;
  if (said && said.length <= 80) return said;
  const names = entries.flatMap((entry) => entry.items.map((item) => item.name)).join(" + ");
  return names.length <= 80 && names ? names : meal.label;
}

export function MealSheet({
  day,
  meal,
  step,
  entries,
  onClose,
  onChanged,
}: {
  day: string;
  meal: Meal;
  step: MealStep;
  entries: Entry[];
  onClose: () => void;
  onChanged: (message?: string) => void;
}) {
  const t = useT();
  const today = todayIso();
  const first = entries[0] ? clockOf(entries[0].eaten_at) : meal.usual_at;
  const [at, setAt] = useState(first);
  const [name, setName] = useState(() => menuName(meal, entries));
  const count = entries.reduce((total, entry) => total + entry.items.length, 0);
  const things = plural(t, "things", count);
  const name_ = meal.label.toLowerCase();

  return (
    <Sheet title={meal.label} onClose={onClose}>
      <Hint>{mealLine(meal, t)}</Hint>

      {step === "repeat" && (
        <ConfirmPanel
          title={t("meal.repeat_title", { meal: name_ })}
          detail={t("meal.repeat_detail", { things })}
          action={t("meal.repeat")}
          onCancel={onClose}
          onConfirm={() => repeatMeal(day, meal.meal, today).then(() => onChanged(t("meal.repeated", { meal: meal.label })))}
        />
      )}

      {step === "time" && (
        <>
          <TextField label={t("common.time")} type="time" value={at} onChange={setAt} autoFocus />
          <ConfirmPanel
            title={t("meal.move_title", { meal: name_ })}
            changes={[{ label: t("common.time"), from: first, to: HHMM.test(at) ? at : "—" }]}
            detail={count > 1 ? t("meal.move_detail", { things }) : undefined}
            action={t("meal.move")}
            onCancel={onClose}
            onConfirm={() => {
              if (!HHMM.test(at)) throw new Error(t("common.time_format"));
              return moveMeal(day, meal.meal, at).then(() => onChanged(t("meal.moved", { meal: meal.label, at })));
            }}
          />
        </>
      )}

      {step === "menu" && (
        <>
          <TextField label={t("menu.name")} value={name} onChange={setName} autoFocus />
          <Hint>{t("menu.hint")}</Hint>
          <ConfirmPanel
            title={t("menu.save_title")}
            changes={[{ label: t("menu.menu"), to: name.trim() || "—" }]}
            detail={t("menu.save_detail", { things, meal: name_ })}
            action={t("menu.save")}
            onCancel={onClose}
            onConfirm={() => {
              if (!name.trim()) throw new Error(t("common.name_it"));
              return menuFromMeal(day, meal.meal, name.trim(), null).then(() => onChanged(t("menu.saved")));
            }}
          />
        </>
      )}

      {step === "delete" && (
        <ConfirmPanel
          title={t("meal.delete_title", { meal: name_ })}
          detail={t("meal.delete_detail", { things })}
          action={t("meal.delete", { meal: name_ })}
          destructive
          onCancel={onClose}
          onConfirm={() => removeMeal(day, meal.meal).then(() => onChanged(t("common.deleted", { name: meal.label })))}
        />
      )}
    </Sheet>
  );
}
