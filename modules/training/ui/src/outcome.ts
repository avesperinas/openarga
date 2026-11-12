import type { Locale, Translate } from "@openarga/ui";

import { amount } from "./labels";

import type { LastTime, LoggedSet } from "./api";

export type Direction = "up" | "flat" | "down" | "first";

export interface Comparison {
  text: string;
  direction: Direction;
}

function loadOf(set: LoggedSet, bodyweight: boolean): number {
  return (bodyweight ? set.added_load : set.weight) ?? 0;
}

function strength(set: LoggedSet, bodyweight: boolean): number {
  const load = loadOf(set, bodyweight);
  const reps = set.reps ?? 0;
  return load > 0 ? load * (1 + reps / 30) : reps;
}

export function bestSet(sets: LoggedSet[], bodyweight: boolean): LoggedSet | null {
  let best: LoggedSet | null = null;
  for (const set of sets) {
    if (!set.completed || !set.reps) continue;
    const value = strength(set, bodyweight);
    const current = best ? strength(best, bodyweight) : -1;
    if (!best || value > current || (value === current && set.reps > (best.reps ?? 0))) best = set;
  }
  return best;
}

function signed(value: number, unit: string, locale: Locale): string {
  const sign = value > 0 ? "+" : "−";
  return `${sign}${amount(Math.abs(value), locale)} ${unit}`;
}

export function compare(
  sets: LoggedSet[],
  last: LastTime | undefined,
  bodyweight: boolean,
  day: string,
  t: Translate,
  locale: Locale,
): Comparison | null {
  const today = bestSet(sets, bodyweight);
  if (!today) return null;
  const before = last && last.day <= day ? bestSet(last.sets, bodyweight) : null;
  if (!before) return { text: t("compare.first"), direction: "first" };

  const now = strength(today, bodyweight);
  const then = strength(before, bodyweight);
  const direction: Direction = now > then ? "up" : now < then ? "down" : "flat";
  const load = loadOf(today, bodyweight) - loadOf(before, bodyweight);
  if (load !== 0) return { text: signed(load, "kg", locale), direction };
  const reps = (today.reps ?? 0) - (before.reps ?? 0);
  if (reps === 0) return { text: t("compare.same"), direction: "flat" };
  return { text: signed(reps, t(Math.abs(reps) === 1 ? "compare.rep" : "compare.reps"), locale), direction };
}
