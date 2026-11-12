import type { Locale, Translate } from "@openarga/ui";

import type { DayKind, Implement, Pattern } from "./api";

export interface Option<T extends string> {
  value: T;
  label: string;
}

const options = <T extends string>(t: Translate, prefix: string, values: readonly T[]): Option<T>[] =>
  values.map((value) => ({ value, label: t(`${prefix}.${value}`) }));

const KIND_VALUES: readonly DayKind[] = ["push", "pull", "leg", "full", "other"];

export const kinds = (t: Translate) => options(t, "kind", KIND_VALUES);

export const HUE_OF_KIND: Record<DayKind, number> = { push: 4, pull: 2, leg: 1, full: 5, other: 8 };

export const ICON_OF_KIND = {
  push: "push",
  pull: "pull",
  leg: "leg",
  full: "kettlebell",
  other: "dumbbell",
} as const satisfies Record<DayKind, string>;

const IMPLEMENT_VALUES: readonly Implement[] = ["barbell", "dumbbell", "smith", "machine", "cable", "bodyweight"];

export const implementsOf = (t: Translate) => options(t, "implement", IMPLEMENT_VALUES);

const PATTERN_VALUES: readonly Pattern[] = [
  "horizontal_push",
  "vertical_push",
  "horizontal_pull",
  "vertical_pull",
  "knee_dominant",
  "hip_dominant",
  "isolation",
];

export const patterns = (t: Translate) => options(t, "pattern", PATTERN_VALUES);

export const regions = (t: Translate) => options(t, "region", ["upper", "lower", "core"] as const);

export type MuscleLevel = "primary" | "secondary";

export const LEVEL_ORDER: { value: MuscleLevel }[] = [{ value: "primary" }, { value: "secondary" }];

export function muscleName(t: Translate, muscle: { id: string; name: string }): string {
  const key = `muscle.${muscle.id}`;
  const found = t(key);
  return found === key ? muscle.name : found;
}

export const muscleLevels = (t: Translate) => options(t, "muscle_level", ["primary", "secondary"] as const);

export const decimal = (value: number, digits: number, locale: Locale): string =>
  new Intl.NumberFormat(locale, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);

export const plural = (t: Translate, key: string, count: number, vars: Record<string, string | number> = {}) =>
  t(`${key}.${count === 1 ? "one" : "other"}`, { count, ...vars });

export const amount = (value: number, locale: Locale): string =>
  new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value);

export const labelOf = <T extends string>(options: { value: T; label: string }[], value: T): string =>
  options.find((option) => option.value === value)?.label ?? value;

export function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

export function shortDate(day: string, locale: Locale): string {
  const [year, month, date] = day.split("-").map(Number) as [number, number, number];
  return new Date(year, month - 1, date).toLocaleDateString(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

export function longDate(day: string, locale: Locale): string {
  const [year, month, date] = day.split("-").map(Number) as [number, number, number];
  return new Date(year, month - 1, date).toLocaleDateString(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export const describeTarget = (slot: { target_sets: number; rep_min: number; rep_max: number }) =>
  slot.rep_min === slot.rep_max
    ? `${slot.target_sets} × ${slot.rep_min}`
    : `${slot.target_sets} × ${slot.rep_min}–${slot.rep_max}`;
