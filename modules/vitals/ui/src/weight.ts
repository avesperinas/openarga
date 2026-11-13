import type { Locale, Translate } from "@openarga/ui";

import type { Against, Day, Goal, Source } from "./api";

export type Period = "3m" | "1y" | "all";

export const periods = (t: Translate): { id: Period; label: string }[] =>
  (["3m", "1y", "all"] as const).map((id) => ({ id, label: t(`period.${id}`) }));

export function monthsBefore(day: string, months: number): string {
  const [year = 1970, month = 1, date = 1] = day.split("-").map(Number);
  const back = new Date(Date.UTC(year, month - 1 - months, date));
  return back.toISOString().slice(0, 10);
}

export function inPeriod(days: Day[], period: Period): Day[] {
  const last = days[days.length - 1];
  if (!last || period === "all") return days;
  const from = monthsBefore(last.day, period === "3m" ? 3 : 12);
  return days.filter((one) => one.day > from);
}

export function extremes(days: Day[]): { min: Day; max: Day } | null {
  if (days.length === 0) return null;
  let min = days[0]!;
  let max = days[0]!;
  for (const one of days) {
    if (one.kg < min.kg) min = one;
    if (one.kg > max.kg) max = one;
  }
  return { min, max };
}

export const kg = (value: number, locale: Locale) =>
  `${value.toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} kg`;

export const signedKg = (value: number, locale: Locale) =>
  `${value.toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" })} kg`;

export function goodWay(against: Against | null): "down" | "up" | "stay" | null {
  if (against === "above") return "down";
  if (against === "below") return "up";
  if (against === "inside") return "stay";
  return null;
}

export function changeTone(change: number | null, against: Against | null): "positive" | "negative" | "neutral" {
  const way = goodWay(against);
  if (change === null || way === null || Math.abs(change) < 0.05) return "neutral";
  if (way === "stay") return Math.abs(change) <= 1 ? "positive" : "negative";
  return (way === "down") === change < 0 ? "positive" : "negative";
}

export function bandFoot(value: number, goal: Goal, against: Against | null, t: Translate, locale: Locale): string {
  if (against === "above" && goal.weight_max_kg !== null) {
    return t("goal.above", { amount: kg(value - goal.weight_max_kg, locale) });
  }
  if (against === "below" && goal.weight_min_kg !== null) {
    return t("goal.below", { amount: kg(goal.weight_min_kg - value, locale) });
  }
  if (against === "inside") return t("goal.inside");
  return t("goal.none");
}

export function bandLabel(goal: Goal, t: Translate, locale: Locale): string {
  const { weight_min_kg: low, weight_max_kg: high } = goal;
  if (low !== null && high !== null) return t("goal.between", { low: kg(low, locale), high: kg(high, locale) });
  if (high !== null) return t("goal.up_to", { high: kg(high, locale) });
  if (low !== null) return t("goal.from", { low: kg(low, locale) });
  return t("goal.none");
}

export const sourceName = (t: Translate, source: Source) => t(`source.${source}`);

export function dayLabel(day: string, locale: Locale, withYear = true): string {
  return new Date(`${day}T12:00:00Z`).toLocaleDateString(locale, {
    weekday: withYear ? undefined : "short",
    day: "numeric",
    month: "short",
    year: withYear ? "numeric" : undefined,
  });
}

export function today(timeZone: string, now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone }).format(now);
}

export function parseKg(text: string): number | null {
  const value = Number(text.trim().replace(",", "."));
  return Number.isFinite(value) && value >= 20 && value <= 400 ? value : null;
}
