import { BodyMaps, LevelChips, amountColor, nextLevel } from "@openarga/ui";

import type { Catalogue, Muscles } from "./api";
import { MUSCLE_LEVELS, REGIONS } from "./labels";

type Level = (typeof MUSCLE_LEVELS)[number]["value"];

export const toLevels = (muscles: Record<string, number>): Record<string, Level> =>
  Object.fromEntries(Object.entries(muscles).map(([id, c]) => [id, c >= 1 ? "primary" : "secondary"]));

export const fromLevels = (levels: Record<string, Level>): Muscles =>
  Object.fromEntries(Object.entries(levels).map(([id, level]) => [id, level === "primary" ? 1 : 0.5]));

export const hasPrimary = (muscles: Record<string, number>) => Object.values(muscles).some((c) => c >= 1);

export function onePrimary(previous: Record<string, Level>, next: Record<string, Level>): Record<string, Level> {
  const promoted = Object.keys(next).find((id) => next[id] === "primary" && previous[id] !== "primary");
  if (!promoted) return next;
  return Object.fromEntries(
    Object.entries(next).map(([id, level]) => [id, id !== promoted && level === "primary" ? "secondary" : level]),
  );
}

export function describeMuscles(muscles: Record<string, number>, catalogue: Catalogue): string {
  const name = (id: string) => catalogue.muscles.find((muscle) => muscle.id === id)?.name ?? id;
  const primary = Object.entries(muscles).filter(([, c]) => c >= 1).map(([id]) => name(id));
  const secondary = Object.entries(muscles).filter(([, c]) => c < 1).map(([id]) => name(id));
  return [primary.join(", "), secondary.join(", ")].filter(Boolean).join(" · ");
}

export function cycleMuscle(value: Record<string, number>, muscle: string): Muscles {
  const levels = toLevels(value);
  const next = nextLevel(MUSCLE_LEVELS, levels[muscle]);
  const changed = { ...levels };
  if (next) changed[muscle] = next;
  else delete changed[muscle];
  return fromLevels(onePrimary(levels, changed));
}

export function pickedColors(value: Record<string, number>): Record<string, string | undefined> {
  return Object.fromEntries(
    Object.entries(value).map(([id, c]) => [id, c >= 1 ? "var(--accent)" : amountColor(0.15, "var(--accent)")]),
  );
}

export interface MusclePickerProps {
  catalogue: Catalogue;
  value: Record<string, number>;
  onChange: (muscles: Muscles) => void;
}

export function MusclePicker({ catalogue, value, onChange }: MusclePickerProps) {
  const levels = toLevels(value);
  return (
    <div className="training-field">
      <span className="training-field-label">Músculos</span>
      <p className="training-field-hint">
        Toca el músculo en el cuerpo o en la lista. Un toque, principal: solo uno, el que mide su
        fuerza y se lleva sus series. Dos, secundario. Tres, ninguno.
      </p>
      <BodyMaps
        compact
        label="Qué trabaja"
        colors={pickedColors(value)}
        names={Object.fromEntries(
          catalogue.muscles.map((muscle) => {
            const level = levels[muscle.id];
            return [muscle.id, level ? `${muscle.name}: ${level === "primary" ? "principal" : "secundario"}` : muscle.name];
          }),
        )}
        onSelect={(muscle) => onChange(cycleMuscle(value, muscle))}
      />
      {REGIONS.map((region) => {
        const options = catalogue.muscles
          .filter((muscle) => muscle.region === region.value)
          .map((muscle) => ({ value: muscle.id, label: muscle.name }));
        if (options.length === 0) return null;
        const own = Object.fromEntries(Object.entries(levels).filter(([id]) => options.some((o) => o.value === id)));
        return (
          <div key={region.value} className="training-muscle-region">
            <span className="training-field-hint">{region.label}</span>
            <LevelChips
              label={`Músculos · ${region.label}`}
              options={options}
              levels={MUSCLE_LEVELS}
              value={own}
              onChange={(next) => {
                const others = Object.fromEntries(
                  Object.entries(levels).filter(([id]) => !options.some((o) => o.value === id)),
                );
                onChange(fromLevels(onePrimary(levels, { ...others, ...next })));
              }}
            />
          </div>
        );
      })}
    </div>
  );
}
