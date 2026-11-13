import { type CoverageItem, type Translate, type TrendPoint, dates } from "@openarga/ui";

import type { Micro, Trend, Week } from "./api";
import { amount, plural } from "./words";

const KCAL_PER_GRAM: Record<string, number> = { saturated_fat: 9, sugars: 4, added_sugars: 4, fat: 9, carbs: 4, protein: 4 };

export function microShare(micro: Micro, kcal: number | null): number | null {
  const reference = micro.reference;
  if (!reference || micro.value === null || reference.value <= 0) return null;
  if (reference.kind === "energy_share") {
    const perGram = KCAL_PER_GRAM[micro.key];
    if (!perGram || !kcal) return null;
    return (micro.value * perGram) / kcal / reference.value;
  }
  return micro.value / reference.value;
}

export function microValue(micro: Micro, kcal: number | null, t: Translate): string {
  const digits = (value: number) => (value >= 10 ? 0 : 1);
  if (micro.value === null) return t("micro.no_data");
  const reference = micro.reference;
  if (!reference) return `${amount(micro.value, digits(micro.value))} ${micro.unit}`;
  if (reference.kind === "energy_share") {
    const perGram = KCAL_PER_GRAM[micro.key];
    const pct = perGram && kcal ? (micro.value * perGram * 100) / kcal : null;
    return pct === null
      ? `${amount(micro.value, 1)} ${micro.unit}`
      : t("micro.kcal_share", { pct: amount(pct, 0), max: amount(reference.value * 100, 0) });
  }
  return t("micro.of", {
    value: amount(micro.value, digits(micro.value)),
    reference: amount(reference.value, digits(reference.value)),
    unit: micro.unit,
  });
}

export type CoverageGroup = { key: "low" | "near" | "ok" | "caution"; title: string; items: CoverageItem[] };

export function coverageGroups(
  week: Week,
  trend: Trend | null,
  t: Translate,
  open?: (key: string) => void,
): CoverageGroup[] {
  const kcal = week.averages.kcal ?? null;
  const groups: Record<CoverageGroup["key"], CoverageItem[]> = { low: [], near: [], ok: [], caution: [] };
  for (const micro of week.micros) {
    if (!micro.reference) continue;
    const share = microShare(micro, kcal);
    if (share === null) continue;
    const kind = micro.reference.kind === "min" ? "min" : "max";
    const item: CoverageItem = {
      key: micro.key,
      label: micro.name,
      share,
      value: microValue(micro, kcal, t),
      kind,
      partial: micro.partial,
      trend: trend?.nutrients[micro.key],
      onOpen: open ? () => open(micro.key) : undefined,
    };
    if (kind === "max") groups[share > 0.9 ? "caution" : "ok"].push(item);
    else if (micro.partial) groups[share < 1 ? "near" : "ok"].push(item);
    else groups[share < 0.8 ? "low" : share < 1 ? "near" : "ok"].push(item);
  }
  const byShare = (a: CoverageItem, b: CoverageItem) =>
    Number(Boolean(a.partial)) - Number(Boolean(b.partial)) || (a.share ?? 0) - (b.share ?? 0);
  return (
    [
      { key: "low", title: t("coverage.low"), items: groups.low.sort(byShare) },
      { key: "near", title: t("coverage.near"), items: groups.near.sort(byShare) },
      { key: "ok", title: t("coverage.ok"), items: groups.ok.sort(byShare) },
      { key: "caution", title: t("coverage.caution"), items: groups.caution.sort((a, b) => (b.share ?? 0) - (a.share ?? 0)) },
    ] as CoverageGroup[]
  ).filter((group) => group.items.length > 0);
}

export function kcalTrend(trend: Trend, weeks: number): TrendPoint[] {
  const days = trend.days.slice(-weeks * 7).filter((one) => one.complete && one.kcal !== null);
  return days.map((one, index) => {
    const window = days.slice(Math.max(0, index - 6), index + 1).map((day) => day.kcal ?? 0);
    return {
      day: one.day,
      value: Math.round(one.kcal ?? 0),
      average: window.length >= 3 ? Math.round(window.reduce((sum, value) => sum + value, 0) / window.length) : null,
    };
  });
}

export function energyLine(
  average: number | null,
  low: number | null,
  high: number | null,
  week: Week,
  t: Translate,
): string {
  const parts: string[] = [];
  const aim = low !== null && high !== null ? (low + high) / 2 : (high ?? low);
  if (average !== null && aim) {
    const ratio = average / aim;
    if (ratio >= 0.9 && ratio <= 1.1) parts.push(t("energy.on_aim"));
    else parts.push(t(ratio < 1 ? "energy.less" : "energy.more", { pct: amount(Math.abs(ratio - 1) * 100, 0) }));
  }
  const spend = week.expenditure;
  if (spend?.kcal && average !== null) {
    const rounded = Math.round(spend.kcal / 50) * 50;
    const change = spend.weight_change_kg_week;
    const way =
      change === null || Math.abs(change) < 0.05
        ? t("energy.keep")
        : t(change < 0 ? "energy.lose" : "energy.gain", { kg: amount(Math.abs(change), 1) });
    parts.push(t("energy.spend", { kcal: amount(rounded, 0), way }));
  }
  return parts.join(" ");
}

export function daysNear(week: Week, aim: number | null): { near: number; of: number } {
  const days = week.days.filter((one) => one.kcal !== null);
  if (!aim) return { near: 0, of: days.length };
  return { near: days.filter((one) => (one.kcal ?? 0) >= aim * 0.9 && (one.kcal ?? 0) <= aim * 1.1).length, of: days.length };
}

export function windowLine(week: Week, t: Translate): string {
  const short = dates({ day: "numeric", month: "short" });
  const first = short.format(new Date(`${week.first}T12:00:00`));
  const last = short.format(new Date(`${week.last}T12:00:00`));
  const counted = week.counted;
  const days = counted?.days ?? week.days_logged;
  const said = plural(t, counted?.complete ? "window.complete" : "window.logged", days);
  return `${first} – ${last} · ${said}`;
}
