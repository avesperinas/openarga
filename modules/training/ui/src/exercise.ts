import type { Locale, Translate } from "@openarga/ui";

import type { Machine, VariantPoint } from "./api";
import { amount } from "./labels";

const counted = (points: VariantPoint[]) => points.filter((point) => point.status === "counted");

export function recordIds(points: VariantPoint[]): Set<string> {
  const out = new Set<string>();
  let best: number | null = null;
  for (const point of counted(points)) {
    if (best !== null && point.e1rm > best) out.add(point.id);
    best = best === null ? point.e1rm : Math.max(best, point.e1rm);
  }
  return out;
}

const RECENT = 8;

export function normalRange(points: VariantPoint[]): { low: number; high: number } | null {
  const values = counted(points)
    .slice(-RECENT)
    .map((point) => point.e1rm)
    .sort((a, b) => a - b);
  if (values.length < 4) return null;
  const at = (share: number) => {
    const position = (values.length - 1) * share;
    const below = Math.floor(position);
    const above = Math.ceil(position);
    return values[below]! + (values[above]! - values[below]!) * (position - below);
  };
  return { low: at(0.25), high: at(0.75) };
}

export function recordStreak(points: VariantPoint[]): number {
  const records = recordIds(points);
  const list = counted(points);
  let streak = 0;
  for (let index = list.length - 1; index >= 0 && records.has(list[index]!.id); index--) streak++;
  return streak;
}

export function advice(machine: Machine, increment: number, external: boolean, t: Translate, locale: Locale): string[] {
  const list = counted(machine.points);
  const last = list[list.length - 1];
  const best = machine.best;
  if (!last || !best) return [];
  const out: string[] = [];

  const streak = recordStreak(machine.points);
  if (streak >= 2) out.push(t("advice.streak", { count: streak }));
  else if (machine.without_pr >= 3) out.push(t("advice.stalled", { count: machine.without_pr }));

  if (external) {
    const step = increment > 0 ? increment : 2.5;
    let load = Math.ceil(best.e1rm / (1 + last.reps / 30) / step) * step;
    if (load * (1 + last.reps / 30) <= best.e1rm) load += step;
    out.push(t("advice.next_load", { reps: last.reps, load: amount(load, locale) }));
  } else {
    const reps = Math.floor(30 * (best.e1rm / last.load - 1)) + 1;
    if (reps <= 15) out.push(t("advice.next_reps", { reps }));
  }
  return out;
}
