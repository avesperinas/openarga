import type { RecurrenceRule, Weekday } from "@openarga/ui";

import type { AssessmentKind, Kind, Modality, ServerRule, Session, Verdict } from "./api";

export const KINDS: { value: Kind; label: string }[] = [
  { value: "master", label: "Máster" },
  { value: "degree", label: "Grado" },
  { value: "course", label: "Curso" },
  { value: "certification", label: "Certificación" },
  { value: "language", label: "Idioma" },
  { value: "other", label: "Otro" },
];

export const MODALITIES: { value: Modality; label: string }[] = [
  { value: "in_person", label: "Presencial" },
  { value: "online", label: "En línea" },
  { value: "hybrid", label: "Mixta" },
];

export const ASSESSMENT_KINDS: { value: AssessmentKind; label: string }[] = [
  { value: "assignment", label: "Entrega" },
  { value: "exam", label: "Examen" },
  { value: "practical", label: "Práctica" },
  { value: "participation", label: "Participación" },
  { value: "other", label: "Otro" },
];

export const labelOf = <T extends string>(list: { value: T; label: string }[], value: T): string =>
  list.find((item) => item.value === value)?.label ?? value;

export function grade(value: number | null | undefined, scale = 10): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const places = scale >= 100 ? 0 : 1;
  const text = value.toFixed(places).replace(".", ",");
  return text.endsWith(",0") ? text.slice(0, -2) : text;
}

export function needed(value: number, scale = 10): string {
  const step = scale >= 100 ? 1 : 10;
  return grade(Math.ceil(Math.round(value * step * 1e4) / 1e4) / step, scale);
}

export function percent(value: number): string {
  const text = value.toFixed(1).replace(".", ",");
  return (text.endsWith(",0") ? text.slice(0, -2) : text) + " %";
}

export function parseNumber(text: string): number | null {
  const clean = text.trim().replace(",", ".");
  if (!clean) return null;
  const value = Number(clean);
  return Number.isFinite(value) ? value : null;
}

export function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}

const WEEKDAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
const WEEKDAY_SHORT = ["D", "L", "M", "X", "J", "V", "S"];
const MONTHS = [
  "enero",
  "febrero",
  "marzo",
  "abril",
  "mayo",
  "junio",
  "julio",
  "agosto",
  "septiembre",
  "octubre",
  "noviembre",
  "diciembre",
];
const MONTHS_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"];

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

export const weekdayShort = (iso: string) => WEEKDAY_SHORT[day(iso).getDay()]!;
export const weekdayName = (iso: string) => WEEKDAYS[day(iso).getDay()]!;

export function dateLong(iso: string, now = new Date()): string {
  const date = day(iso);
  const base = `${date.getDate()} de ${MONTHS[date.getMonth()]}`;
  return date.getFullYear() === now.getFullYear() ? base : `${base} de ${date.getFullYear()}`;
}

export function dateShort(iso: string, now = new Date()): string {
  const date = day(iso);
  const base = `${date.getDate()} ${MONTHS_SHORT[date.getMonth()]}`;
  return date.getFullYear() === now.getFullYear() ? base : `${base} ${date.getFullYear()}`;
}

export function dayTitle(iso: string, now = new Date()): string {
  const name = weekdayName(iso);
  return `${name[0]!.toUpperCase()}${name.slice(1)}, ${dateLong(iso, now)}`;
}

export function period(from: string | null, to: string | null): string | null {
  const one = (iso: string) => {
    const date = day(iso);
    return `${MONTHS_SHORT[date.getMonth()]} ${date.getFullYear()}`;
  };
  if (from && to) return `${one(from)} – ${one(to)}`;
  if (from) return `desde ${one(from)}`;
  if (to) return `hasta ${one(to)}`;
  return null;
}

export function clock(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
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
  if (daysLeft === 0) return "Hoy";
  if (daysLeft === 1) return "Mañana";
  if (daysLeft === -1) return "Venció ayer";
  if (daysLeft < 0) return `Venció hace ${-daysLeft} días`;
  if (daysLeft < 14) return `En ${daysLeft} días`;
  const weeks = Math.round(daysLeft / 7);
  return `En ${weeks} semanas`;
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
  return {
    empty: "Sin evaluables",
    not_started: "Sin notas",
    in_progress: "En juego",
    secured: "Asegurada",
    impossible: "Imposible",
    passed: "Aprobada",
    failed: "Suspensa",
    below_minimum: "Bajo el mínimo",
  }[verdict];
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
