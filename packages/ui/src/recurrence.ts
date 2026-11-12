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

export const DAY_NAMES: Record<Weekday, { one: string; many: string; short: string }> = {
  MO: { one: "lunes", many: "lunes", short: "L" },
  TU: { one: "martes", many: "martes", short: "M" },
  WE: { one: "miércoles", many: "miércoles", short: "X" },
  TH: { one: "jueves", many: "jueves", short: "J" },
  FR: { one: "viernes", many: "viernes", short: "V" },
  SA: { one: "sábado", many: "sábados", short: "S" },
  SU: { one: "domingo", many: "domingos", short: "D" },
};

export const MONTH_NAMES = [
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
] as const;

export const ORDINALS: Record<number, string> = {
  1: "primer",
  2: "segundo",
  3: "tercer",
  4: "cuarto",
  5: "quinto",
  [-1]: "último",
  [-2]: "penúltimo",
  [-3]: "antepenúltimo",
};

const UNITS: Record<Freq, { one: string; many: string }> = {
  daily: { one: "cada día", many: "días" },
  weekly: { one: "cada semana", many: "semanas" },
  monthly: { one: "cada mes", many: "meses" },
  yearly: { one: "cada año", many: "años" },
};

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
    if (!WEEKDAYS.includes(weekday)) throw new Error(`día desconocido: ${item}`);
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
  return `${items.slice(0, -1).join(", ")} y ${items[items.length - 1]}`;
}

function monthDayPhrase(days: number[]): string {
  const ordered = orderMonthDays(days);
  if (ordered.every((d) => d > 0)) {
    return ordered.length === 1 ? `el día ${ordered[0]}` : `los días ${join(ordered.map(String))}`;
  }
  return join(ordered.map((d) => (d > 0 ? `el día ${d}` : `el ${ORDINALS[d]} día`)));
}

function positioned(days: RecurrenceDay[]): string {
  return join(orderDays(days).map((d) => `el ${ORDINALS[d.pos ?? 1]} ${DAY_NAMES[d.weekday].one}`));
}

export function describe(value: RecurrenceRule): string {
  const unit = UNITS[value.freq];
  let parts = [value.interval === 1 ? unit.one : `cada ${value.interval} ${unit.many}`];
  const weekdays = orderDays(value.byDay).map((d) => d.weekday);

  if (value.freq === "weekly" && weekdays.length) {
    if (value.interval === 1 && weekdays.join() === WORKWEEK.join()) {
      parts = ["de lunes a viernes"];
    } else if (weekdays.length === 1) {
      parts.push(`el ${DAY_NAMES[weekdays[0]!].one}`);
    } else {
      parts.push(join(weekdays.map((d) => DAY_NAMES[d].one)));
    }
  } else if (value.freq === "monthly") {
    if (value.byMonthDay.length) parts.push(monthDayPhrase(value.byMonthDay));
    else if (value.byDay.length && value.byDay[0]!.pos !== undefined) parts.push(positioned(value.byDay));
    else if (value.byDay.length) parts.push(`los ${join(weekdays.map((d) => DAY_NAMES[d].many))}`);
  } else if (value.freq === "yearly" && value.byMonth.length) {
    const months = join([...value.byMonth].sort((a, b) => a - b).map((m) => MONTH_NAMES[m - 1]!));
    if (value.byMonthDay.length) {
      const ordered = orderMonthDays(value.byMonthDay);
      parts.push(
        ordered.length === 1 && ordered[0]! > 0
          ? `el ${ordered[0]} de ${months}`
          : `${monthDayPhrase(value.byMonthDay)} de ${months}`,
      );
    } else if (value.byDay.length) {
      parts.push(`${positioned(value.byDay)} de ${months}`);
    } else {
      parts.push(`en ${months}`);
    }
  }

  if (value.count !== undefined) parts.push(value.count === 1 ? "una vez" : `${value.count} veces`);
  if (value.until !== undefined) {
    const [year, month, day] = value.until.slice(0, 10).split("-").map(Number);
    parts.push(`hasta el ${day} de ${MONTH_NAMES[month! - 1]} de ${year}`);
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
