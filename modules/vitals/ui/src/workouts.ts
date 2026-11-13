import type { Locale, StatTone, Translate } from "@openarga/ui";

import type { Baseline, Load, SleepGroup, Workout } from "./api";

import { plural, unitName } from "./words";

const number = (value: number, locale: Locale, digits = 0) =>
  value.toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function minutesLabel(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${String(Math.round(minutes - hours * 60)).padStart(2, "0")}`;
}

export function baselineValue(baseline: Baseline, value: number | null, t: Translate, locale: Locale): string {
  if (value === null) return "—";
  if (baseline.unit === "min") return minutesLabel(value);
  const shown = number(value, locale, baseline.digits);
  if (baseline.unit === "%") return `${shown} %`;
  if (baseline.unit === "°C") return `${value > 0 ? "+" : ""}${shown} °C`;
  return `${shown} ${unitName(t, baseline.unit)}`;
}

export function baselineTile(baseline: Baseline, t: Translate, locale: Locale): { value: string; foot: string; tone: StatTone } {
  const value = baselineValue(baseline, baseline.value, t, locale);
  if (baseline.value === null) return { value, foot: t("baseline.no_data"), tone: "neutral" };
  if (baseline.status === null || baseline.low === null || baseline.high === null) {
    return { value, foot: t("baseline.not_yet", { days: baseline.days }), tone: "neutral" };
  }
  const range = `${baselineValue(baseline, baseline.low, t, locale)} – ${baselineValue(baseline, baseline.high, t, locale)}`;
  return {
    value,
    foot: `${t(`baseline.${baseline.status}`)} · ${range}`,
    tone: baseline.status === "inside" ? "neutral" : "warning",
  };
}

export function clock(iso: string): string {
  const moment = new Date(iso);
  return `${String(moment.getHours()).padStart(2, "0")}:${String(moment.getMinutes()).padStart(2, "0")}`;
}

export function whenLabel(iso: string, locale: Locale): string {
  const moment = new Date(iso);
  const weekday = moment.toLocaleDateString(locale, { weekday: "short" }).replace(".", "");
  return `${weekday} ${moment.getDate()}, ${clock(iso)}`;
}

export function workoutLine(workout: Workout, t: Translate, locale: Locale): string {
  return [
    whenLabel(workout.start, locale),
    minutesLabel(workout.minutes),
    workout.heart.avg != null ? t("workout.average", { value: Math.round(workout.heart.avg) }) : null,
    workout.heart.max != null ? t("workout.max", { value: Math.round(workout.heart.max) }) : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function elapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

export function groupLine(group: SleepGroup, t: Translate, locale: Locale): string {
  if (group.nights === 0) return t("group.no_nights");
  return [
    group.asleep != null ? minutesLabel(group.asleep) : null,
    group.deep != null ? t("group.deep", { value: minutesLabel(group.deep) }) : null,
    group.hrv != null ? t("group.hrv", { value: number(group.hrv, locale) }) : null,
    plural(t, "group.nights", group.nights),
  ]
    .filter(Boolean)
    .join(" · ");
}

export function zoneWeeks(load: Load): number[][] {
  return [0, 1, 2, 3, 4].map((zone) => load.weeks.map((week) => Math.round(week.zones?.[zone] ?? 0)));
}

export function rollingMean(load: Load): (number | null)[] {
  return load.weeks.map((_, index) => {
    const before = load.weeks.slice(Math.max(0, index - 4), index);
    if (before.length < 4) return null;
    return Math.round(before.reduce((sum, week) => sum + week.load, 0) / 4);
  });
}

export function fromFirstLoad(load: Load): Load {
  const first = load.weeks.findIndex((week) => week.load > 0);
  return first <= 0 ? load : { ...load, weeks: load.weeks.slice(first) };
}

export function zoneShares(load: Load, weeks = 4): { minutes: number[]; shares: number[] } {
  const recent = load.weeks.slice(-weeks);
  const minutes = [0, 1, 2, 3, 4].map((zone) => Math.round(recent.reduce((sum, week) => sum + (week.zones?.[zone] ?? 0), 0)));
  const total = minutes.reduce((sum, one) => sum + one, 0);
  return { minutes, shares: minutes.map((one) => (total > 0 ? one / total : 0)) };
}

export function byName(
  workouts: Workout[],
  now: Date,
  t: Translate,
  days = 30,
): { name: string; count: number; minutes: number }[] {
  const since = now.getTime() - days * 86_400_000;
  const groups = new Map<string, { name: string; count: number; minutes: number }>();
  for (const one of workouts) {
    if (Date.parse(one.start) < since) continue;
    const row = groups.get(one.name) ?? { name: one.name, count: 0, minutes: 0 };
    row.count += 1;
    row.minutes += one.minutes;
    groups.set(one.name, row);
  }
  const sorted = [...groups.values()].sort((a, b) => b.minutes - a.minutes);
  if (sorted.length <= 6) return sorted;
  const other = t("workout.others");
  const others = sorted.slice(5).reduce((sum, one) => ({ name: other, count: sum.count + one.count, minutes: sum.minutes + one.minutes }), {
    name: other,
    count: 0,
    minutes: 0,
  });
  return [...sorted.slice(0, 5), others];
}

export function byWeek(
  workouts: Workout[],
  now: Date,
  t: Translate,
  locale: Locale,
): { start: string; label: string; items: Workout[] }[] {
  const short = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" });
  const mondayOf = (date: Date) => {
    const monday = new Date(date);
    monday.setHours(12, 0, 0, 0);
    monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
    return monday;
  };
  const key = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const current = key(mondayOf(now));
  const groups = new Map<string, Workout[]>();
  for (const one of [...workouts].sort((a, b) => b.start.localeCompare(a.start))) {
    const monday = key(mondayOf(new Date(one.start)));
    groups.set(monday, [...(groups.get(monday) ?? []), one]);
  }
  return [...groups.entries()].map(([start, items]) => {
    const monday = new Date(`${start}T12:00:00`);
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    const label = start === current ? t("workout.this_week") : `${short.format(monday)} – ${short.format(sunday)}`;
    return { start, label: `${label} · ${items.length}`, items };
  });
}
