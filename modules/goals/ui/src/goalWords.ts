import { type GoalTone, type Translate, dates, numbers, regional } from "@openarga/ui";

import type { Goal } from "./api";
import { daysBetween } from "./words";

const UNIT_WORDS: Record<string, string> = { EUR: "€", count: "", percent: "%" };
const SAID_UNITS = new Set(["steps", "points"]);

export function unitWord(t: Translate, unit: string | null | undefined): string {
  if (!unit) return "";
  if (SAID_UNITS.has(unit)) return t(`unit.${unit}`);
  return UNIT_WORDS[unit] ?? unit;
}

function decimalsFor(value: number, unit: string | null | undefined): number {
  if (unit === "kg") return 1;
  if (unit === "EUR") return Math.abs(value) >= 100 ? 0 : 2;
  if (unit === "steps" || unit === "kcal") return 0;
  if (Math.abs(value) >= 100) return 0;
  return Number.isInteger(value) ? 0 : 1;
}

export function figure(t: Translate, value: number | null | undefined, unit?: string | null): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const decimals = decimalsFor(value, unit);
  const number = numbers({
    minimumFractionDigits: unit === "kg" ? 1 : 0,
    maximumFractionDigits: decimals,
    useGrouping: true,
  }).format(value);
  const word = unitWord(t, unit);
  return word ? `${number} ${word}` : number;
}

export function shortDate(iso: string, today: string): string {
  const sameYear = iso.slice(0, 4) === today.slice(0, 4);
  const options: Intl.DateTimeFormatOptions = sameYear
    ? { day: "numeric", month: "short", timeZone: "UTC" }
    : { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" };
  return dates(options).format(new Date(`${iso.slice(0, 10)}T00:00:00Z`)).replace(".", "");
}

const unitOf = (goal: Goal) => goal.metric?.unit ?? null;

export function frequency(t: Translate, goal: Goal): string {
  if (goal.period === "week") return t("frequency.week");
  const days = goal.days_per_week ?? 7;
  if (days === 7) return t("frequency.daily");
  return days === 1 ? t("frequency.days_one") : t("frequency.days_many", { count: days });
}

export function condition(t: Translate, goal: Goal): string | null {
  if (goal.target === null) return null;
  const value = figure(t, goal.target, unitOf(goal));
  return goal.direction === "at_least" ? t("condition.at_least", { value }) : t("condition.at_most", { value });
}

export function subtitle(t: Translate, goal: Goal, today: string, withCategory = true): string {
  const lower = (text: string) => text.toLocaleLowerCase(regional().locale);
  const parts: (string | null)[] = [withCategory ? goal.category : null];
  if (goal.kind === "periodic") {
    const wants = condition(t, goal);
    parts.push(wants ? `${wants} ${frequency(t, goal)}` : frequency(t, goal));
    if (goal.metric) parts.push(lower(goal.metric.label));
  } else {
    if (goal.target === null) parts.push(t("standing.milestone_word"));
    else if (goal.metric) parts.push(lower(goal.metric.label));
    if (goal.due_on) parts.push(shortDate(goal.due_on, today));
  }
  return parts.filter(Boolean).join(" · ");
}

export interface Standing {
  tone: GoalTone;
  text: string;
}

export function standing(t: Translate, goal: Goal): Standing {
  if (goal.status === "achieved") return { tone: "positive", text: t("standing.achieved") };
  if (goal.status === "missed") return { tone: "negative", text: t("standing.missed") };
  if (goal.status === "abandoned") return { tone: "neutral", text: t("standing.abandoned") };
  if (goal.kind === "periodic") {
    const unit = goal.streak_unit === "weeks" ? "weeks" : "days";
    const text = goal.streak
      ? goal.streak === 1
        ? t(`standing.streak_${unit}_one`)
        : t(`standing.streak_${unit}_many`, { count: goal.streak })
      : goal.constancy !== null
        ? t("standing.constancy", { value: Math.round(goal.constancy * 100) })
        : t("standing.starts_today");
    return { tone: goal.week_met ? "positive" : "neutral", text };
  }
  if (goal.target === null) return { tone: "neutral", text: t("standing.milestone") };
  if (goal.pace === "ahead") return { tone: "positive", text: t("standing.ahead") };
  if (goal.pace === "behind") return { tone: "negative", text: t("standing.behind") };
  if (goal.pace === "on_track") return { tone: "neutral", text: t("standing.on_track") };
  return { tone: "neutral", text: t("standing.no_data") };
}

export function against(t: Translate, goal: Goal, today: string): string | null {
  if (goal.kind !== "dated" || goal.target === null) return null;
  const unit = unitOf(goal);
  const parts = [
    goal.start !== null && goal.start !== goal.target
      ? t("against.from_to", { start: figure(t, goal.start, null), target: figure(t, goal.target, unit) })
      : t("against.target", { target: figure(t, goal.target, unit) }),
  ];
  if (goal.status === "active") {
    if (goal.projection !== null) parts.push(t("against.lands", { value: figure(t, goal.projection, unit) }));
    else if (goal.last_day && daysBetween(goal.last_day, today) > 28) parts.push(t("against.stale"));
  }
  return parts.join(" · ");
}

export function weekLabel(t: Translate, goal: Goal): string {
  if (goal.period === "week") {
    return t("week.of", {
      count: figure(t, goal.week_count ?? 0, null),
      target: figure(t, goal.week_target, unitOf(goal)),
    });
  }
  return t("week.of", { count: goal.week_count ?? 0, target: goal.week_target ?? 7 });
}

export function current(t: Translate, goal: Goal): string | null {
  if (goal.kind !== "dated" || goal.target === null) return null;
  const value = goal.status === "active" ? goal.current : goal.closed_value;
  return value === null ? null : figure(t, value, unitOf(goal));
}

export type GoalView = "category" | "date";

export interface GoalGroup {
  id: string;
  label: string;
  hue: number | null;
  goals: Goal[];
}

export function byDate(t: Translate, goals: Goal[]): GoalGroup[] {
  const periodic = goals.filter((goal) => goal.kind === "periodic");
  const dated = goals
    .filter((goal) => goal.kind === "dated")
    .sort((a, b) => (a.due_on ?? "").localeCompare(b.due_on ?? ""));
  return [
    { id: "periodic", label: t("group.periodic"), hue: null, goals: periodic },
    { id: "dated", label: t("group.dated"), hue: null, goals: dated },
  ].filter((group) => group.goals.length > 0);
}

export function byCategory(
  t: Translate,
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
    label: t("group.no_category"),
    hue: null,
    goals: order(goals.filter((goal) => !goal.category_id)),
  });
  return groups.filter((group) => group.goals.length > 0);
}

export const tickable = (goal: Goal) => goal.kind === "periodic" && goal.period === "day";

export function goalFigures(t: Translate, goals: Goal[]) {
  const periodic = goals.filter((goal) => tickable(goal));
  const done = periodic.filter((goal) => goal.today_met).length;
  const behind = goals.filter((goal) => goal.pace === "behind").length;
  const best = goals.reduce<Goal | null>((top, goal) => ((goal.streak ?? 0) > (top?.streak ?? 0) ? goal : top), null);
  return [
    { label: t("goals.figure_done_today"), value: periodic.length ? `${done}/${periodic.length}` : "–", lit: periodic.length > 0 && done === periodic.length },
    { label: t("goals.figure_behind"), value: behind, muted: behind === 0 },
    {
      label: best?.streak ? t(`goals.figure_streak_${best.streak_unit === "weeks" ? "weeks" : "days"}`) : t("goals.figure_streak"),
      value: best?.streak ?? 0,
    },
  ];
}
