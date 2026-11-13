import type { Locale, Translate, TrendTileProps } from "@openarga/ui";

import type { BodyOverview, BodySection, CheckupChanges, Figure, Kpis } from "./api";
import { figureAbout, figureFoot, figureName, figureValue } from "./body";
import { analyteName } from "./labs";
import { fixed } from "./words";

const NOT_MOVING = new Set(["headphone_db", "environment_db", "headphone_noise_events", "environment_noise_events", "high_heart_rate_events", "low_heart_rate_events"]);

export interface Moving {
  figure: Figure;
  recent: number;
  before: number;
  z: number;
  direction: "up" | "down";
}

const mean = (values: number[]) => values.reduce((sum, one) => sum + one, 0) / values.length;

export function moving(overview: BodyOverview | null, limit = 4): Moving[] {
  if (!overview) return [];
  const found: Moving[] = [];
  for (const section of overview.sections) {
    if (section.id === "history") continue;
    for (const figure of section.figures) {
      if (figure.historic || NOT_MOVING.has(figure.id)) continue;
      const weeks = figure.weeks ?? [];
      if (weeks.filter((one) => one !== null).length < 12) continue;
      const recent = weeks.slice(-4).filter((one): one is number => one !== null);
      const before = weeks.slice(0, -4).filter((one): one is number => one !== null);
      if (recent.length < 2 || before.length < 8) continue;
      const base = mean(before);
      const spread = Math.sqrt(mean(before.map((one) => (one - base) ** 2)));
      if (spread <= 0) continue;
      const now = mean(recent);
      const z = (now - base) / spread;
      if (Math.abs(z) < 1) continue;
      found.push({ figure, recent: now, before: base, z, direction: z > 0 ? "up" : "down" });
    }
  }
  return found.sort((a, b) => Math.abs(b.z) - Math.abs(a.z)).slice(0, limit);
}

export function movingLine(one: Moving, t: Translate, locale: Locale): string {
  return t(one.direction === "up" ? "moving.up" : "moving.down", {
    now: figureValue(one.figure, one.recent, t, locale),
    before: figureValue(one.figure, one.before, t, locale),
  });
}

export function weightMoving(kpis: Kpis | null, t: Translate, locale: Locale): { line: string; direction: "up" | "down" } | null {
  const change = kpis?.weight.change_90 ?? null;
  if (change === null || Math.abs(change) < 0.5) return null;
  const shown = `${change > 0 ? "+" : "−"}${fixed(Math.abs(change), locale, 1)} kg`;
  return { line: t("moving.weight", { change: shown }), direction: change > 0 ? "up" : "down" };
}

export function ageLabel(day: string, t: Translate, now: Date = new Date()): string {
  const then = new Date(`${day}T12:00:00`);
  const days = Math.max(0, Math.round((now.getTime() - then.getTime()) / 86_400_000));
  if (days === 0) return t("age.today");
  if (days < 31) return days === 1 ? t("age.yesterday") : t("age.days", { count: days });
  const months = Math.round(days / 30.44);
  if (months < 1) return t("age.days", { count: days });
  return months === 1 ? t("age.month") : t("age.months", { count: months });
}

export function outChips(
  changes: CheckupChanges | null,
  t: Translate,
  now: Date = new Date(),
): { id: string; name: string }[] {
  const checkup = changes?.checkup;
  if (!checkup) return [];
  const days = (now.getTime() - new Date(`${checkup.day}T12:00:00`).getTime()) / 86_400_000;
  if (days > 365) return [];
  return (changes?.changes ?? [])
    .filter((one) => one.out)
    .map((one) => ({ id: one.analyte.id, name: analyteName(t, one.analyte) }));
}

export function tilesOf(
  section: BodySection,
  open: (id: string) => void,
  t: Translate,
  locale: Locale,
): (TrendTileProps & { key: string })[] {
  return section.figures
    .filter((figure) => !figure.historic)
    .map((figure) => {
      const weeks = figure.weeks ?? [];
      const changed = figure.changed_on ? weekIndex(figure.changed_on, weeks.length) : undefined;
      return {
        key: figure.id,
        label: figureName(t, figure),
        value: figure.latest ? figureValue(figure, figure.latest.value, t, locale) : "—",
        foot: figureFoot(figure, t, locale) || undefined,
        weeks,
        changedAt: changed,
        info: figureAbout(t, figure),
        onOpen: () => open(figure.id),
      };
    });
}

export function weekIndex(day: string, count: number, now: Date = new Date()): number | undefined {
  const monday = new Date(now);
  monday.setHours(12, 0, 0, 0);
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  const first = new Date(monday);
  first.setDate(monday.getDate() - 7 * (count - 1));
  const at = Math.floor((new Date(`${day}T12:00:00`).getTime() - first.getTime()) / (7 * 86_400_000));
  return at >= 0 && at < count ? at : undefined;
}

export function weeklyOf(days: { day: string; value: number }[], count = 26, now: Date = new Date()): (number | null)[] {
  const sums = new Array<number>(count).fill(0);
  const seen = new Array<number>(count).fill(0);
  for (const one of days) {
    const at = weekIndex(one.day, count, now);
    if (at === undefined) continue;
    sums[at] = (sums[at] ?? 0) + one.value;
    seen[at] = (seen[at] ?? 0) + 1;
  }
  return sums.map((sum, index) => ((seen[index] ?? 0) > 0 ? sum / (seen[index] ?? 1) : null));
}
