import type { RecurrenceRule, Weekday } from "@openarga/ui";

import type { AssessmentKind, Kind, Modality, ServerRule, Session, Verdict } from "./api";
import { currentLocale, intl, t } from "./lang";

export const KINDS: { value: Kind; readonly label: string }[] = (
  ["master", "degree", "course", "certification", "language", "other"] as const
).map((value) => ({
  value,
  get label() {
    return t(`kind.${value}`);
  },
}));

export const MODALITIES: { value: Modality; readonly label: string }[] = (["in_person", "online", "hybrid"] as const).map(
  (value) => ({
    value,
    get label() {
      return t(`modality.${value}`);
    },
  }),
);

export const ASSESSMENT_KINDS: { value: AssessmentKind; readonly label: string }[] = (
  ["assignment", "exam", "practical", "participation", "other"] as const
).map((value) => ({
  value,
  get label() {
    return t(`assessment.${value}`);
  },
}));

export const labelOf = <T extends string>(list: { value: T; label: string }[], value: T): string =>
  list.find((item) => item.value === value)?.label ?? value;

export const decimal = (text: string) => (currentLocale() === "es" ? text.replace(".", ",") : text);

export function grade(value: number | null | undefined, scale = 10): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const places = scale >= 100 ? 0 : 1;
  const text = value.toFixed(places);
  return decimal(text.endsWith(".0") ? text.slice(0, -2) : text);
}

export function needed(value: number, scale = 10): string {
  const step = scale >= 100 ? 1 : 10;
  return grade(Math.ceil(Math.round(value * step * 1e4) / 1e4) / step, scale);
}

export function percent(value: number): string {
  const text = value.toFixed(1);
  return decimal(text.endsWith(".0") ? text.slice(0, -2) : text) + " %";
}

export function parseNumber(text: string): number | null {
  const clean = text.trim().replace(",", ".");
  if (!clean) return null;
  const value = Number(clean);
  return Number.isFinite(value) ? value : null;
}

export const plural = (count: number, key: string): string =>
  t(`${key}.${count === 1 ? "one" : "other"}`, { count });

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${decimal((bytes / 1024 / 1024).toFixed(1))} MB`;
}

const formatted = (iso: string, options: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat(intl(), options).format(day(iso));

export function day(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number) as [number, number, number];
  return new Date(y, m - 1, d);
}

export function isoDate(date: Date): string {
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${m}-${d}`;
}

export function todayIso(now = new Date()): string {
  return isoDate(now);
}

export const weekdayShort = (iso: string) => formatted(iso, { weekday: "narrow" });
export const weekdayName = (iso: string) => formatted(iso, { weekday: "long" });

const thisYear = (iso: string, now: Date) => day(iso).getFullYear() === now.getFullYear();

export const dateLong = (iso: string, now = new Date()): string =>
  formatted(iso, { day: "numeric", month: "long", ...(thisYear(iso, now) ? {} : { year: "numeric" }) });

export const dateShort = (iso: string, now = new Date()): string =>
  formatted(iso, { day: "numeric", month: "short", ...(thisYear(iso, now) ? {} : { year: "numeric" }) });

export function dayTitle(iso: string, now = new Date()): string {
  const name = weekdayName(iso);
  return `${name[0]!.toUpperCase()}${name.slice(1)}, ${dateLong(iso, now)}`;
}

export function period(from: string | null, to: string | null): string | null {
  const one = (iso: string) => {
    return formatted(iso, { month: "short", year: "numeric" });
  };
  if (from && to) return `${one(from)} – ${one(to)}`;
  if (from) return t("period.from", { date: one(from) });
  if (to) return t("period.until", { date: one(to) });
  return null;
}

export function clock(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return date.toLocaleTimeString(intl(), { hour: "2-digit", minute: "2-digit" });
}

export function span(start: string, end: string): string {
  return `${clock(start)} – ${clock(end)}`;
}

export const hhmm = (value: string | null): string => (value ? value.slice(0, 5) : "");

export function daysUntil(iso: string, now = new Date()): number {
  const target = day(iso);
  const base = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target.getTime() - base.getTime()) / 86_400_000);
}

export function countdown(daysLeft: number): string {
  if (daysLeft === 0) return t("countdown.today");
  if (daysLeft === 1) return t("countdown.tomorrow");
  if (daysLeft === -1) return t("countdown.yesterday");
  if (daysLeft < 0) return t("countdown.overdue", { days: -daysLeft });
  if (daysLeft < 14) return t("countdown.days", { days: daysLeft });
  return t("countdown.weeks", { weeks: Math.round(daysLeft / 7) });
}

export function urgency(daysLeft: number): "overdue" | "soon" | "week" | "later" {
  if (daysLeft < 0) return "overdue";
  if (daysLeft <= 2) return "soon";
  if (daysLeft <= 7) return "week";
  return "later";
}

export function localIso(date: Date): string {
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const abs = Math.abs(offset);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${isoDate(date)}T${pad(date.getHours())}:${pad(date.getMinutes())}:00` +
    `${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`
  );
}

export function atTime(isoDay: string, time: string): Date {
  const date = day(isoDay);
  const [h, m] = time.split(":").map(Number) as [number, number];
  date.setHours(h, m, 0, 0);
  return date;
}

export function sessionMoment(session: Pick<Session, "starts_at" | "ends_at">, now = new Date()) {
  const start = new Date(session.starts_at);
  const end = new Date(session.ends_at);
  if (now >= start && now < end) return "now";
  if (now >= end) return "past";
  return "future";
}

export type StatusTone = "positive" | "warning" | "negative" | "neutral";

export function verdictTone(verdict: Verdict): StatusTone {
  switch (verdict) {
    case "passed":
    case "secured":
      return "positive";
    case "failed":
    case "impossible":
    case "below_minimum":
      return "negative";
    case "in_progress":
      return "warning";
    default:
      return "neutral";
  }
}

export function verdictLabel(verdict: Verdict): string {
  return t(`verdict.${verdict}`);
}

export function ruleToServer(rule: RecurrenceRule): ServerRule {
  return {
    freq: rule.freq,
    interval: rule.interval,
    by_day: rule.byDay.map((d) => (d.pos ? { weekday: d.weekday, pos: d.pos } : { weekday: d.weekday })),
    by_month_day: rule.byMonthDay,
    by_month: rule.byMonth,
    count: rule.count ?? null,
    until: rule.until ? rule.until.slice(0, 10) : null,
  };
}

export function ruleFromServer(rule: ServerRule): RecurrenceRule {
  return {
    freq: rule.freq,
    interval: rule.interval,
    byDay: rule.by_day.map((d) => ({ weekday: d.weekday as Weekday, ...(d.pos ? { pos: d.pos } : {}) })),
    byMonthDay: rule.by_month_day,
    byMonth: rule.by_month,
    ...(rule.count ? { count: rule.count } : {}),
    ...(rule.until ? { until: rule.until.slice(0, 10) } : {}),
  };
}

export const WEEK: Weekday[] = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];
