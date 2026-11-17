import { type Translate, dates, todayIso as zonedToday } from "@openarga/ui";

import type { Task } from "./api";

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

export const todayIso = (now: Date = new Date()): string => zonedToday(now);

const utcDay = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00Z`);
const said = (options: Intl.DateTimeFormatOptions, iso: string) =>
  dates({ ...options, timeZone: "UTC" }).format(utcDay(iso)).replace(".", "");

export function addDays(iso: string, days: number): string {
  return new Date(utc(iso) + days * 86_400_000).toISOString().slice(0, 10);
}

export function daysBetween(from: string, to: string): number {
  return Math.round((utc(to) - utc(from)) / 86_400_000);
}

export function longDate(iso: string): string {
  return said({ weekday: "long", day: "numeric", month: "long" }, iso);
}

export const clock = (time: string) => time.slice(0, 5);

export function whenLabel(
  t: Translate,
  task: Pick<Task, "due_on" | "due_time">,
  today: string,
): string | null {
  if (!task.due_on) return null;
  const days = daysBetween(today, task.due_on);
  const [y] = parts(task.due_on);
  let when: string;
  if (days === 0) when = t("when.today");
  else if (days === 1) when = t("when.tomorrow");
  else if (days === -1) when = t("when.yesterday");
  else if (days < 0 && days >= -14) when = t("when.days_ago", { count: -days });
  else if (days > 1 && days <= 6) when = said({ weekday: "short", day: "numeric" }, task.due_on);
  else if (y === parts(today)[0]) when = said({ day: "numeric", month: "short" }, task.due_on);
  else when = said({ day: "numeric", month: "short", year: "numeric" }, task.due_on);
  return task.due_time ? `${when} · ${clock(task.due_time)}` : when;
}

export type Group = "overdue" | "today" | "tomorrow" | "week" | "later" | "someday";

export const GROUPS: Group[] = ["overdue", "today", "tomorrow", "week", "later", "someday"];

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
  t: Translate,
  tasks: T[],
  today: string,
): { id: Group; label: string; tasks: T[] }[] {
  return GROUPS.map((id) => ({
    id,
    label: t(`group.${id}`),
    tasks: tasks.filter((task) => groupOf(task, today) === id),
  })).filter((group) => group.tasks.length > 0);
}

export function quickDates(
  t: Translate,
  today: string,
): { key: string; label: string; value: string | null }[] {
  const day = weekday(today);
  const saturday = addDays(today, ((6 - day + 7) % 7) || 7);
  const monday = addDays(today, ((1 - day + 7) % 7) || 7);
  return [
    { key: "none", label: t("quick.none"), value: null },
    { key: "today", label: t("quick.today"), value: today },
    { key: "tomorrow", label: t("quick.tomorrow"), value: addDays(today, 1) },
    { key: "saturday", label: t("quick.saturday"), value: saturday },
    { key: "monday", label: t("quick.monday"), value: monday },
  ];
}

export function count(t: Translate, key: string, n: number): string {
  return n === 1 ? t(`${key}_one`) : t(`${key}_many`, { count: n });
}

export const HUES = [1, 2, 3, 4, 5, 6, 7, 8];

export function todayRing(t: Translate, pending: Task[], done: Task[], today: string) {
  const doneToday = done.filter((task) => task.done_at !== null && todayIso(new Date(task.done_at)) === today).length;
  const due = pending.filter((task) => task.status === "today" || task.status === "overdue").length;
  const overdue = pending.filter((task) => task.status === "overdue").length;
  const total = doneToday + due;
  const left = [count(t, "ring.pending", pending.length)];
  if (overdue > 0) left.unshift(count(t, "ring.overdue", overdue));
  return {
    share: total > 0 ? doneToday / total : null,
    value: total > 0 ? `${doneToday}/${total}` : "0",
    label: total > 0 ? t("ring.done_today") : t("ring.nothing_today"),
    detail: left.join(" · "),
    tone: overdue > 0 ? ("warning" as const) : undefined,
  };
}
