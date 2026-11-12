import { ConfirmPanel, Hint, Sheet, TextField } from "@openarga/ui";
import { useState } from "react";

import { type Entry, type Meal, menuFromMeal, moveMeal, removeMeal, repeatMeal } from "./api";
import { mealLine, timeOf, todayIso } from "./words";

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
  const today = todayIso();
  const first = entries[0] ? timeOf(entries[0].eaten_at) : meal.usual_at;
  const [at, setAt] = useState(first);
  const [name, setName] = useState(() => menuName(meal, entries));
  const count = entries.reduce((total, entry) => total + entry.items.length, 0);
  const things = count === 1 ? "1 cosa" : `${count} cosas`;

  return (
    <Sheet title={meal.label} onClose={onClose}>
      <Hint>{mealLine(meal)}</Hint>

      {step === "repeat" && (
        <ConfirmPanel
          title={`¿Repetir ${meal.label.toLowerCase()} hoy?`}
          detail={`Se apuntan hoy las mismas ${things}, con sus mismos números.`}
          action="Repetir hoy"
          onCancel={onClose}
          onConfirm={() => repeatMeal(day, meal.meal, today).then(() => onChanged(`Apuntado hoy · ${meal.label}`))}
        />
      )}

      {step === "time" && (
        <>
          <TextField label="Hora" type="time" value={at} onChange={setAt} autoFocus />
          <ConfirmPanel
            title={`¿Mover ${meal.label.toLowerCase()}?`}
            changes={[{ label: "Hora", from: first, to: HHMM.test(at) ? at : "—" }]}
            detail={count > 1 ? `Se mueven las ${things}.` : undefined}
            action="Cambiar la hora"
            onCancel={onClose}
            onConfirm={() => {
              if (!HHMM.test(at)) throw new Error("Pon la hora como 08:30");
              return moveMeal(day, meal.meal, at).then(() => onChanged(`${meal.label} a las ${at}`));
            }}
          />
        </>
      )}

      {step === "menu" && (
        <>
          <TextField label="Nombre del menú" value={name} onChange={setName} autoFocus />
          <Hint>Un menú se apunta de un toque al añadir, con lo que la despensa diga entonces.</Hint>
          <ConfirmPanel
            title="¿Guardar como menú?"
            changes={[{ label: "Menú", to: name.trim() || "—" }]}
            detail={`Con las ${things} de ${meal.label.toLowerCase()}.`}
            action="Guardar menú"
            onCancel={onClose}
            onConfirm={() => {
              if (!name.trim()) throw new Error("Ponle un nombre");
              return menuFromMeal(day, meal.meal, name.trim(), null).then(() => onChanged("Menú guardado"));
            }}
          />
        </>
      )}

      {step === "delete" && (
        <ConfirmPanel
          title={`¿Borrar ${meal.label.toLowerCase()}?`}
          detail={`Se ${count === 1 ? "borra 1 cosa" : `borran ${things}`} y deja de contar en el día. No se puede deshacer.`}
          action={`Borrar ${meal.label.toLowerCase()}`}
          destructive
          onCancel={onClose}
          onConfirm={() => removeMeal(day, meal.meal).then(() => onChanged(`Borrado · ${meal.label}`))}
        />
      )}
    </Sheet>
  );
}
