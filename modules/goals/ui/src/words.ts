import type { Task } from "./api";

const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const LONG_MONTHS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
const WEEKDAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
const SHORT_WEEKDAYS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];

function parts(iso: string): [number, number, number] {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return [y!, m!, d!];
}

function utc(iso: string): number {
  const [y, m, d] = parts(iso);
  return Date.UTC(y, m - 1, d);
}

function weekday(iso: string): number {
  return new Date(utc(iso)).getUTCDay();
}

export const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export function todayIso(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Madrid" }).format(now);
}

export function addDays(iso: string, days: number): string {
  return new Date(utc(iso) + days * 86_400_000).toISOString().slice(0, 10);
}

export function daysBetween(from: string, to: string): number {
  return Math.round((utc(to) - utc(from)) / 86_400_000);
}

export function longDate(iso: string): string {
  const [, m, d] = parts(iso);
  return `${WEEKDAYS[weekday(iso)]}, ${d} de ${LONG_MONTHS[m - 1]}`;
}

export const clock = (time: string) => time.slice(0, 5);

export function whenLabel(task: Pick<Task, "due_on" | "due_time">, today: string): string | null {
  if (!task.due_on) return null;
  const days = daysBetween(today, task.due_on);
  const [y, m, d] = parts(task.due_on);
  let said: string;
  if (days === 0) said = "hoy";
  else if (days === 1) said = "mañana";
  else if (days === -1) said = "ayer";
  else if (days < 0 && days >= -14) said = `hace ${-days} días`;
  else if (days > 1 && days <= 6) said = `${SHORT_WEEKDAYS[weekday(task.due_on)]} ${d}`;
  else said = y === parts(today)[0] ? `${d} ${MONTHS[m - 1]}` : `${d} ${MONTHS[m - 1]} ${y}`;
  return task.due_time ? `${said} · ${clock(task.due_time)}` : said;
}

export type Group = "overdue" | "today" | "tomorrow" | "week" | "later" | "someday";

export const GROUPS: { id: Group; label: string }[] = [
  { id: "overdue", label: "Vencidas" },
  { id: "today", label: "Hoy" },
  { id: "tomorrow", label: "Mañana" },
  { id: "week", label: "Próximos 7 días" },
  { id: "later", label: "Más adelante" },
  { id: "someday", label: "Sin fecha" },
];

export function groupOf(task: Pick<Task, "status" | "due_on">, today: string): Group {
  if (task.status === "overdue") return "overdue";
  if (!task.due_on) return "someday";
  const days = daysBetween(today, task.due_on);
  if (days <= 0) return "today";
  if (days === 1) return "tomorrow";
  if (days <= 7) return "week";
  return "later";
}

export function grouped<T extends Pick<Task, "status" | "due_on">>(
  tasks: T[],
  today: string,
): { id: Group; label: string; tasks: T[] }[] {
  return GROUPS.map((group) => ({
    ...group,
    tasks: tasks.filter((task) => groupOf(task, today) === group.id),
  })).filter((group) => group.tasks.length > 0);
}

export function quickDates(today: string): { key: string; label: string; value: string | null }[] {
  const day = weekday(today);
  const saturday = addDays(today, ((6 - day + 7) % 7) || 7);
  const monday = addDays(today, ((1 - day + 7) % 7) || 7);
  return [
    { key: "none", label: "Sin fecha", value: null },
    { key: "today", label: "Hoy", value: today },
    { key: "tomorrow", label: "Mañana", value: addDays(today, 1) },
    { key: "saturday", label: "El sábado", value: saturday },
    { key: "monday", label: "El lunes", value: monday },
  ];
}

export function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

export const HUES: { value: number; label: string }[] = [
  { value: 1, label: "Azul" },
  { value: 2, label: "Verde" },
  { value: 3, label: "Ámbar" },
  { value: 4, label: "Rojo" },
  { value: 5, label: "Violeta" },
  { value: 6, label: "Turquesa" },
  { value: 7, label: "Rosa" },
  { value: 8, label: "Gris" },
];
