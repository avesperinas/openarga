import type { GoalTone } from "@openarga/ui";

import type { Goal } from "./api";
import { daysBetween } from "./words";

const LOCALE = "es-ES";
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

const UNIT_WORDS: Record<string, string> = {
  EUR: "€",
  steps: "pasos",
  count: "",
  points: "pts",
  percent: "%",
};

export function unitWord(unit: string | null | undefined): string {
  if (!unit) return "";
  return UNIT_WORDS[unit] ?? unit;
}

function decimalsFor(value: number, unit: string | null | undefined): number {
  if (unit === "kg") return 1;
  if (unit === "EUR") return Math.abs(value) >= 100 ? 0 : 2;
  if (unit === "steps" || unit === "kcal") return 0;
  if (Math.abs(value) >= 100) return 0;
  return Number.isInteger(value) ? 0 : 1;
}

export function figure(value: number | null | undefined, unit?: string | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const decimals = decimalsFor(value, unit);
  const number = new Intl.NumberFormat(LOCALE, {
    minimumFractionDigits: unit === "kg" ? 1 : 0,
    maximumFractionDigits: decimals,
    useGrouping: true,
  }).format(value);
  const word = unitWord(unit);
  return word ? `${number} ${word}` : number;
}

export function shortDate(iso: string, today: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const [thisYear] = today.split("-").map(Number);
  return y === thisYear ? `${d} ${MONTHS[m! - 1]}` : `${d} ${MONTHS[m! - 1]} ${y}`;
}

const unitOf = (goal: Goal) => goal.metric?.unit ?? null;

export function frequency(goal: Goal): string {
  if (goal.period === "week") return "a la semana";
  const days = goal.days_per_week ?? 7;
  return days === 7 ? "cada día" : `${days} ${days === 1 ? "día" : "días"} por semana`;
}

export function condition(goal: Goal): string | null {
  if (goal.target === null) return null;
  const word = goal.direction === "at_least" ? "al menos" : "como mucho";
  return `${word} ${figure(goal.target, unitOf(goal))}`;
}

export function subtitle(goal: Goal, today: string, withCategory = true): string {
  const parts: (string | null)[] = [withCategory ? goal.category : null];
  if (goal.kind === "periodic") {
    const wants = condition(goal);
    parts.push(wants ? `${wants} ${frequency(goal)}` : frequency(goal));
    if (goal.metric) parts.push(goal.metric.label.toLocaleLowerCase(LOCALE));
  } else {
    if (goal.target === null) parts.push("hito");
    else if (goal.metric) parts.push(goal.metric.label.toLocaleLowerCase(LOCALE));
    if (goal.due_on) parts.push(shortDate(goal.due_on, today));
  }
  return parts.filter(Boolean).join(" · ");
}

export interface Standing {
  tone: GoalTone;
  text: string;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export function standing(goal: Goal): Standing {
  if (goal.status === "achieved") return { tone: "positive", text: "Cumplida" };
  if (goal.status === "missed") return { tone: "negative", text: "No cumplida" };
  if (goal.status === "abandoned") return { tone: "neutral", text: "Abandonada" };
  if (goal.kind === "periodic") {
    const unit = goal.streak_unit === "weeks" ? ["semana", "semanas"] : ["día", "días"];
    const text = goal.streak
      ? `Racha de ${plural(goal.streak, unit[0]!, unit[1]!)}`
      : goal.constancy !== null
        ? `${Math.round(goal.constancy * 100)} % en 4 semanas`
        : "Empieza hoy";
    return { tone: goal.week_met ? "positive" : "neutral", text };
  }
  if (goal.target === null) return { tone: "neutral", text: "Hito" };
  if (goal.pace === "ahead") return { tone: "positive", text: "Por delante" };
  if (goal.pace === "behind") return { tone: "negative", text: "Por detrás" };
  if (goal.pace === "on_track") return { tone: "neutral", text: "En ritmo" };
  return { tone: "neutral", text: "Sin datos" };
}

export function against(goal: Goal, today: string): string | null {
  if (goal.kind !== "dated" || goal.target === null) return null;
  const unit = unitOf(goal);
  const parts = [
    goal.start !== null && goal.start !== goal.target
      ? `de ${figure(goal.start, null)} a ${figure(goal.target, unit)}`
      : `objetivo ${figure(goal.target, unit)}`,
  ];
  if (goal.status === "active") {
    if (goal.projection !== null) parts.push(`llegas a ${figure(goal.projection, unit)}`);
    else if (goal.last_day && daysBetween(goal.last_day, today) > 28) parts.push("sin datos nuevos");
  }
  return parts.join(" · ");
}

export function weekLabel(goal: Goal): string {
  if (goal.period === "week") {
    return `${figure(goal.week_count ?? 0, null)} de ${figure(goal.week_target, unitOf(goal))} esta semana`;
  }
  return `${goal.week_count ?? 0} de ${goal.week_target ?? 7} esta semana`;
}

export function current(goal: Goal): string | null {
  if (goal.kind !== "dated" || goal.target === null) return null;
  const value = goal.status === "active" ? goal.current : goal.closed_value;
  return value === null ? null : figure(value, unitOf(goal));
}

export type GoalView = "category" | "date";

export interface GoalGroup {
  id: string;
  label: string;
  hue: number | null;
  goals: Goal[];
}

export function byDate(goals: Goal[]): GoalGroup[] {
  const periodic = goals.filter((goal) => goal.kind === "periodic");
  const dated = goals
    .filter((goal) => goal.kind === "dated")
    .sort((a, b) => (a.due_on ?? "").localeCompare(b.due_on ?? ""));
  return [
    { id: "periodic", label: "Cada día y cada semana", hue: null, goals: periodic },
    { id: "dated", label: "Con fecha", hue: null, goals: dated },
  ].filter((group) => group.goals.length > 0);
}

export function byCategory(
  goals: Goal[],
  categories: { id: string; name: string; hue: number }[],
): GoalGroup[] {
  const order = (list: Goal[]) => [
    ...list.filter((goal) => goal.kind === "periodic"),
    ...list.filter((goal) => goal.kind === "dated").sort((a, b) => (a.due_on ?? "").localeCompare(b.due_on ?? "")),
  ];
  const groups: GoalGroup[] = categories.map((category) => ({
    id: category.id,
    label: category.name,
    hue: category.hue,
    goals: order(goals.filter((goal) => goal.category_id === category.id)),
  }));
  groups.push({
    id: "none",
    label: "Sin categoría",
    hue: null,
    goals: order(goals.filter((goal) => !goal.category_id)),
  });
  return groups.filter((group) => group.goals.length > 0);
}
