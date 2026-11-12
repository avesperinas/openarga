import type { DayKind, Implement, Pattern } from "./api";

export const KINDS: { value: DayKind; label: string }[] = [
  { value: "push", label: "Empuje" },
  { value: "pull", label: "Tirón" },
  { value: "leg", label: "Pierna" },
  { value: "full", label: "Cuerpo entero" },
  { value: "other", label: "Otro" },
];

export const HUE_OF_KIND: Record<DayKind, number> = { push: 4, pull: 2, leg: 1, full: 5, other: 8 };

export const ICON_OF_KIND = {
  push: "push",
  pull: "pull",
  leg: "leg",
  full: "kettlebell",
  other: "dumbbell",
} as const satisfies Record<DayKind, string>;

export const IMPLEMENTS: { value: Implement; label: string }[] = [
  { value: "barbell", label: "Barra" },
  { value: "dumbbell", label: "Mancuernas" },
  { value: "smith", label: "Smith" },
  { value: "machine", label: "Máquina" },
  { value: "cable", label: "Polea" },
  { value: "bodyweight", label: "Peso corporal" },
];

export const PATTERNS: { value: Pattern; label: string }[] = [
  { value: "horizontal_push", label: "Empuje horizontal" },
  { value: "vertical_push", label: "Empuje vertical" },
  { value: "horizontal_pull", label: "Tirón horizontal" },
  { value: "vertical_pull", label: "Tirón vertical" },
  { value: "knee_dominant", label: "Dominante de rodilla" },
  { value: "hip_dominant", label: "Dominante de cadera" },
  { value: "isolation", label: "Aislamiento" },
];

export const REGIONS: { value: string; label: string }[] = [
  { value: "upper", label: "Tren superior" },
  { value: "lower", label: "Tren inferior" },
  { value: "core", label: "Core" },
];

export const MUSCLE_LEVELS: { value: "primary" | "secondary"; label: string }[] = [
  { value: "primary", label: "principal" },
  { value: "secondary", label: "secundario" },
];

export const labelOf = <T extends string>(options: { value: T; label: string }[], value: T): string =>
  options.find((option) => option.value === value)?.label ?? value;

export function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

export function shortDate(day: string): string {
  const [year, month, date] = day.split("-").map(Number) as [number, number, number];
  return new Date(year, month - 1, date).toLocaleDateString("es-ES", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

export function longDate(day: string): string {
  const [year, month, date] = day.split("-").map(Number) as [number, number, number];
  return new Date(year, month - 1, date).toLocaleDateString("es-ES", {
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
