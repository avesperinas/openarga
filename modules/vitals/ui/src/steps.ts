import type { Locale, Translate } from "@openarga/ui";

import type { StepsDay } from "./api";

export type Grain = "week" | "month" | "year";

export const steps = (value: number, t: Translate, locale: Locale) =>
  t("steps.count", { count: Math.round(value).toLocaleString(locale) });
export const count = (value: number, locale: Locale) => Math.round(value).toLocaleString(locale);

export function startOf(day: string, grain: Grain): string {
  if (grain === "year") return `${day.slice(0, 4)}-01-01`;
  if (grain === "month") return `${day.slice(0, 7)}-01`;
  const date = new Date(`${day}T12:00:00Z`);
  const back = (date.getUTCDay() + 6) % 7;
  return new Date(date.getTime() - back * 86_400_000).toISOString().slice(0, 10);
}

export const SHOWN: Record<Grain, number> = { week: 26, month: Infinity, year: Infinity };

export function perBucket(
  days: StepsDay[],
  grain: Grain,
  last = SHOWN[grain],
): { start: string; mean: number; days: number }[] {
  const groups = new Map<string, number[]>();
  for (const one of days) {
    const key = startOf(one.day, grain);
    groups.set(key, [...(groups.get(key) ?? []), one.steps]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(Number.isFinite(last) ? -last : 0)
    .map(([start, values]) => ({
      start,
      mean: values.reduce((sum, value) => sum + value, 0) / values.length,
      days: values.length,
    }));
}

export function bucketLabel(start: string, grain: Grain, locale: Locale): string {
  const date = new Date(`${start}T12:00:00Z`);
  if (grain === "year") return start.slice(0, 4);
  return grain === "month"
    ? date.toLocaleDateString(locale, { month: "short", year: "2-digit" })
    : date.toLocaleDateString(locale, { day: "numeric", month: "short" });
}

export function stepsTone(value: number | null | undefined, goal: number | null): "positive" | "warning" | "negative" | "neutral" {
  if (value === null || value === undefined || !goal) return "neutral";
  if (value >= goal) return "positive";
  return value >= goal / 2 ? "warning" : "negative";
}

export const CALENDAR_GOAL = 10_000;

export const weekdays = (t: Translate) => t("weekday.letters").split(",");

export function yearsOf(days: StepsDay[]): string[] {
  return [...new Set(days.map((one) => one.day.slice(0, 4)))].sort().reverse();
}

export function yearEnd(year: string, today: string): string {
  return today.startsWith(year) ? today : `${year}-12-31`;
}
