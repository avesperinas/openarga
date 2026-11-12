import type { TrendPoint } from "@openarga/ui";

import type { BodyPoint, FigureSeries, HeartBucket } from "./api";

export function minuteLabel(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}

export function heartSeries(buckets: HeartBucket[]): { key: string; name: string; values: number[] }[] {
  return [
    { key: "max", name: "Máximo", values: buckets.map((one) => one.max) },
    { key: "avg", name: "Media", values: buckets.map((one) => one.avg) },
    { key: "min", name: "Mínimo", values: buckets.map((one) => one.min) },
  ];
}

export interface HeartSummary {
  points: TrendPoint[];
  now: string;
  month: string;
  change: string | undefined;
  tone: "neutral";
  best: string;
  bestLabel: string;
  bestDay: string | undefined;
}

const DAY_MS = 86_400_000;
const dayTime = (day: string) => Date.parse(`${day}T12:00:00Z`);

function meanBetween(points: BodyPoint[], first: number, last: number): number | null {
  const inside = points.filter((one) => dayTime(one.day) > first && dayTime(one.day) <= last);
  return inside.length ? inside.reduce((sum, one) => sum + one.value, 0) / inside.length : null;
}

export function heartSummary(series: FigureSeries, lowerIsBest: boolean): HeartSummary | null {
  const points = [...series.points].sort((a, b) => a.day.localeCompare(b.day));
  const last = points.at(-1);
  if (!last) return null;
  const end = dayTime(last.day);
  const digits = series.figure.digits;
  const text = (value: number | null) =>
    value === null ? "—" : `${value.toLocaleString("es-ES", { maximumFractionDigits: digits })} ${series.figure.unit}`;
  const now = meanBetween(points, end - 7 * DAY_MS, end);
  const before = meanBetween(points, end - 37 * DAY_MS, end - 30 * DAY_MS);
  const recent = points.filter((one) => dayTime(one.day) > end - 90 * DAY_MS);
  const best = points.reduce((top, one) => ((lowerIsBest ? one.value < top.value : one.value > top.value) ? one : top), last);
  const gap = now !== null && before !== null ? now - before : null;
  return {
    points: recent.map((one) => ({
      day: one.day,
      value: one.value,
      average: meanBetween(points, dayTime(one.day) - 7 * DAY_MS, dayTime(one.day)),
    })),
    now: text(now),
    month: text(before),
    change:
      gap === null ? undefined : `${gap > 0 ? "+" : gap < 0 ? "−" : ""}${Math.abs(gap).toLocaleString("es-ES", { maximumFractionDigits: digits })} desde entonces`,
    tone: "neutral",
    best: text(best.value),
    bestLabel: lowerIsBest ? "Tu más baja" : "Tu más alta",
    bestDay: best.day.split("-").reverse().join("/"),
  };
}
