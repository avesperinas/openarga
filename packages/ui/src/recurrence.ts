import type { Vars } from "./i18n";
import { say } from "./words";

export type Freq = "daily" | "weekly" | "monthly" | "yearly";
export type Weekday = "MO" | "TU" | "WE" | "TH" | "FR" | "SA" | "SU";

export const WEEKDAYS: readonly Weekday[] = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];

export interface RecurrenceDay {
  weekday: Weekday;
  pos?: number;
}

export interface RecurrenceRule {
  freq: Freq;
  interval: number;
  byDay: RecurrenceDay[];
  byMonthDay: number[];
  byMonth: number[];
  count?: number;
  until?: string;
}

const word = (key: string, vars?: Vars): string => say(`recurrence.${key}`, vars);

export const dayName = (weekday: Weekday, form: "one" | "many" | "short" = "one"): string =>
  word(`day.${weekday}.${form}`);

export const monthName = (month: number): string => word(`month.${month}`);

export const ordinal = (pos: number): string => word(`ordinal.${pos}`);

const WORKWEEK: Weekday[] = ["MO", "TU", "WE", "TH", "FR"];

export function rule(freq: Freq, rest: Partial<RecurrenceRule> = {}): RecurrenceRule {
  return { freq, interval: 1, byDay: [], byMonthDay: [], byMonth: [], ...rest };
}

const posKey = (pos: number | undefined) => (pos === undefined ? 0 : pos > 0 ? pos : 10 - pos);

function orderDays(days: RecurrenceDay[]): RecurrenceDay[] {
  return [...days].sort(
    (a, b) => WEEKDAYS.indexOf(a.weekday) - WEEKDAYS.indexOf(b.weekday) || posKey(a.pos) - posKey(b.pos),
  );
}

function orderMonthDays(days: number[]): number[] {
  const key = (d: number) => (d > 0 ? d : 100 - d);
  return [...days].sort((a, b) => key(a) - key(b));
}

const untilText = (until: string) => until.replace(/[-:]/g, "");

function parseUntil(text: string): string {
  if (text.endsWith("Z")) throw new Error("UNTIL es hora de pared, sin zona");
  const date = `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
  if (!text.includes("T")) return date;
  const t = text.slice(9);
  return `${date}T${t.slice(0, 2)}:${t.slice(2, 4)}:${t.slice(4, 6)}`;
}

export function toRRule(value: RecurrenceRule): string {
  const parts = [`FREQ=${value.freq.toUpperCase()}`];
  if (value.interval !== 1) parts.push(`INTERVAL=${value.interval}`);
  if (value.byMonth.length) parts.push(`BYMONTH=${[...value.byMonth].sort((a, b) => a - b).join(",")}`);
  if (value.byMonthDay.length) parts.push(`BYMONTHDAY=${orderMonthDays(value.byMonthDay).join(",")}`);
  if (value.byDay.length) {
    parts.push(`BYDAY=${orderDays(value.byDay).map((d) => `${d.pos ?? ""}${d.weekday}`).join(",")}`);
  }
  if (value.count !== undefined) parts.push(`COUNT=${value.count}`);
  if (value.until !== undefined) parts.push(`UNTIL=${untilText(value.until)}`);
  return parts.join(";");
}

export function fromRRule(text: string): RecurrenceRule {
  const fields = new Map<string, string>();
  for (const part of text.trim().replace(/^RRULE:/, "").split(";")) {
    if (!part) continue;
    const [key, value] = part.split("=");
    if (key === undefined || value === undefined) throw new Error(`parte sin valor: ${part}`);
    fields.set(key.toUpperCase(), value);
  }
  const freq = fields.get("FREQ")?.toLowerCase();
  if (freq !== "daily" && freq !== "weekly" && freq !== "monthly" && freq !== "yearly") {
    throw new Error(`frecuencia desconocida: ${fields.get("FREQ")}`);
  }
  const list = (key: string) => (fields.get(key) ?? "").split(",").filter(Boolean);
  const byDay = list("BYDAY").map((item): RecurrenceDay => {
    const weekday = item.slice(-2).toUpperCase() as Weekday;
    if (!WEEKDAYS.includes(weekday)) throw new Error(`unknown day: ${item}`);
    const pos = item.slice(0, -2);
    return pos ? { weekday, pos: Number(pos) } : { weekday };
  });
  const out = rule(freq, {
    interval: Number(fields.get("INTERVAL") ?? "1"),
    byDay: orderDays(byDay),
    byMonthDay: orderMonthDays(list("BYMONTHDAY").map(Number)),
    byMonth: list("BYMONTH").map(Number).sort((a, b) => a - b),
  });
  const count = fields.get("COUNT");
  const until = fields.get("UNTIL");
  if (count !== undefined) out.count = Number(count);
  if (until !== undefined) out.until = parseUntil(until);
  return out;
}

function join(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return items.slice(0, -1).join(", ") + word("and") + items[items.length - 1];
}

function monthDayPhrase(days: number[]): string {
  const ordered = orderMonthDays(days);
  if (ordered.every((d) => d > 0)) {
    return ordered.length === 1
      ? word("month_day.one", { day: ordered[0]! })
      : word("month_day.many", { days: join(ordered.map(String)) });
  }
  return join(ordered.map((d) => (d > 0 ? word("month_day.one", { day: d }) : word("month_day.from_end", { ordinal: ordinal(d) }))));
}

function positioned(days: RecurrenceDay[]): string {
  return join(orderDays(days).map((d) => word("positioned", { ordinal: ordinal(d.pos ?? 1), day: dayName(d.weekday) })));
}

export function describe(value: RecurrenceRule): string {
  let parts = [value.interval === 1 ? word(`every.${value.freq}`) : word(`every_n.${value.freq}`, { n: value.interval })];
  const weekdays = orderDays(value.byDay).map((d) => d.weekday);

  if (value.freq === "weekly" && weekdays.length) {
    if (value.interval === 1 && weekdays.join() === WORKWEEK.join()) {
      parts = [word("workweek")];
    } else if (weekdays.length === 1) {
      parts.push(word("weekly.one", { day: dayName(weekdays[0]!) }));
    } else {
      parts.push(join(weekdays.map((d) => dayName(d))));
    }
  } else if (value.freq === "monthly") {
    if (value.byMonthDay.length) parts.push(monthDayPhrase(value.byMonthDay));
    else if (value.byDay.length && value.byDay[0]!.pos !== undefined) parts.push(positioned(value.byDay));
    else if (value.byDay.length) parts.push(word("monthly.weekdays", { days: join(weekdays.map((d) => dayName(d, "many"))) }));
  } else if (value.freq === "yearly" && value.byMonth.length) {
    const months = join([...value.byMonth].sort((a, b) => a - b).map(monthName));
    if (value.byMonthDay.length) {
      const ordered = orderMonthDays(value.byMonthDay);
      parts.push(
        ordered.length === 1 && ordered[0]! > 0
          ? word("yearly.date", { day: ordered[0]!, month: months })
          : word("yearly.of", { what: monthDayPhrase(value.byMonthDay), months }),
      );
    } else if (value.byDay.length) {
      parts.push(word("yearly.of", { what: positioned(value.byDay), months }));
    } else {
      parts.push(word("yearly.in", { months }));
    }
  }

  if (value.count !== undefined) parts.push(value.count === 1 ? word("count.one") : word("count.many", { count: value.count }));
  if (value.until !== undefined) {
    const [year, month, day] = value.until.slice(0, 10).split("-").map(Number);
    parts.push(word("until", { date: word("date", { day: day!, month: monthName(month!), year: year! }) }));
  }
  return parts.join(", ");
}

export function weekdayOf(isoDate: string): Weekday {
  const [y, m, d] = isoDate.split("-").map(Number);
  const js = new Date(Date.UTC(y!, m! - 1, d!)).getUTCDay();
  return WEEKDAYS[(js + 6) % 7]!;
}

export function positionOf(isoDate: string): number {
  const [y, m, d] = isoDate.split("-").map(Number);
  const daysInMonth = new Date(Date.UTC(y!, m!, 0)).getUTCDate();
  return d! + 7 > daysInMonth ? -1 : Math.ceil(d! / 7);
}

export interface QuickRule {
  key: string;
  label: string;
  rule: RecurrenceRule;
}

export function quickRules(isoDate: string): QuickRule[] {
  const weekday = weekdayOf(isoDate);
  const [, month, day] = isoDate.split("-").map(Number);
  const pos = positionOf(isoDate);
  const options: RecurrenceRule[] = [
    rule("daily"),
    rule("weekly", { byDay: [{ weekday }] }),
    rule("weekly", { byDay: WORKWEEK.map((w) => ({ weekday: w })) }),
    rule("monthly", { byMonthDay: [day!] }),
    rule("monthly", { byDay: [{ weekday, pos }] }),
    rule("yearly", { byMonth: [month!], byMonthDay: [day!] }),
  ];
  const seen = new Set<string>();
  return options.flatMap((option) => {
    const key = toRRule(option);
    if (seen.has(key)) return [];
    seen.add(key);
    const label = describe(option);
    return [{ key, label: label.charAt(0).toUpperCase() + label.slice(1), rule: option }];
  });
}
