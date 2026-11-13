import type { Locale, Translate, TrendPoint } from "@openarga/ui";

import type { BodyPoint, FigureSeries, HeartBucket } from "./api";
import { decimal, unitName } from "./words";

export function minuteLabel(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}

export function heartSeries(buckets: HeartBucket[], t: Translate): { key: string; name: string; values: number[] }[] {
  return [
    { key: "max", name: t("heart.max"), values: buckets.map((one) => one.max) },
    { key: "avg", name: t("heart.average"), values: buckets.map((one) => one.avg) },
    { key: "min", name: t("heart.min"), values: buckets.map((one) => one.min) },
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

export function heartSummary(
  series: FigureSeries,
  lowerIsBest: boolean,
  t: Translate,
  locale: Locale,
): HeartSummary | null {
  const points = [...series.points].sort((a, b) => a.day.localeCompare(b.day));
  const last = points.at(-1);
  if (!last) return null;
  const end = dayTime(last.day);
  const digits = series.figure.digits;
  const text = (value: number | null) =>
    value === null ? "—" : `${decimal(value, locale, digits)} ${unitName(t, series.figure.unit)}`;
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
      gap === null
        ? undefined
        : t("heart.since_then", { change: `${gap > 0 ? "+" : gap < 0 ? "−" : ""}${decimal(Math.abs(gap), locale, digits)}` }),
    tone: "neutral",
    best: text(best.value),
    bestLabel: lowerIsBest ? t("heart.your_lowest") : t("heart.your_highest"),
    bestDay: new Date(`${best.day}T12:00:00`).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" }),
  };
}
