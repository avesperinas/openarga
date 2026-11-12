import type { StatTone } from "@openarga/ui";

import type { Baseline, Load, SleepGroup, Workout } from "./api";

const number = (value: number, digits = 0) =>
  value.toLocaleString("es-ES", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function minutesLabel(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${String(Math.round(minutes - hours * 60)).padStart(2, "0")}`;
}

export function baselineValue(baseline: Baseline, value: number | null): string {
  if (value === null) return "—";
  if (baseline.unit === "min") return minutesLabel(value);
  const shown = number(value, baseline.digits);
  if (baseline.unit === "%") return `${shown} %`;
  if (baseline.unit === "°C") return `${value > 0 ? "+" : ""}${shown} °C`;
  return `${shown} ${baseline.unit}`;
}

const SAID: Record<NonNullable<Baseline["status"]>, string> = {
  below: "por debajo de tu normal",
  inside: "en tu normal",
  above: "por encima de tu normal",
};

export function baselineTile(baseline: Baseline): { value: string; foot: string; tone: StatTone } {
  const value = baselineValue(baseline, baseline.value);
  if (baseline.value === null) return { value, foot: "sin dato de hoy ni de ayer", tone: "neutral" };
  if (baseline.status === null || baseline.low === null || baseline.high === null) {
    return { value, foot: `aún sin tu normal (${baseline.days} de 14 días)`, tone: "neutral" };
  }
  const range = `${baselineValue(baseline, baseline.low)} – ${baselineValue(baseline, baseline.high)}`;
  return {
    value,
    foot: `${SAID[baseline.status]} · ${range}`,
    tone: baseline.status === "inside" ? "neutral" : "warning",
  };
}

export function clock(iso: string): string {
  const moment = new Date(iso);
  return `${String(moment.getHours()).padStart(2, "0")}:${String(moment.getMinutes()).padStart(2, "0")}`;
}

const WEEKDAYS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

export function whenLabel(iso: string): string {
  const moment = new Date(iso);
  return `${WEEKDAYS[moment.getDay()]} ${moment.getDate()}, ${clock(iso)}`;
}

export function workoutLine(workout: Workout): string {
  return [
    whenLabel(workout.start),
    minutesLabel(workout.minutes),
    workout.heart.avg != null ? `media ${Math.round(workout.heart.avg)} lpm` : null,
    workout.heart.max != null ? `máx. ${Math.round(workout.heart.max)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function elapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

export function groupLine(group: SleepGroup): string {
  if (group.nights === 0) return "sin noches";
  return [
    group.asleep != null ? minutesLabel(group.asleep) : null,
    group.deep != null ? `profundo ${minutesLabel(group.deep)}` : null,
    group.hrv != null ? `VFC ${number(group.hrv)} ms` : null,
    `${group.nights} ${group.nights === 1 ? "noche" : "noches"}`,
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

export function byName(workouts: Workout[], now: Date, days = 30): { name: string; count: number; minutes: number }[] {
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
  const others = sorted.slice(5).reduce((sum, one) => ({ name: "Otros", count: sum.count + one.count, minutes: sum.minutes + one.minutes }), {
    name: "Otros",
    count: 0,
    minutes: 0,
  });
  return [...sorted.slice(0, 5), others];
}

const SHORT = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short" });

export function byWeek(workouts: Workout[], now: Date): { start: string; label: string; items: Workout[] }[] {
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
    const label = start === current ? "Esta semana" : `${SHORT.format(monday)} – ${SHORT.format(sunday)}`;
    return { start, label: `${label} · ${items.length}`, items };
  });
}
