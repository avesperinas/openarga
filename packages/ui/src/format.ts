import { currency as defaultCurrency, dates, locale, numbers, timeZone, zonedDates } from "./regional";

const GROUPED = { useGrouping: "always" } as unknown as Intl.NumberFormatOptions;

export function figureChars(value: number | string, unit?: string): number {
  const shown = typeof value === "number" ? compact(value) : value;
  return Math.max(2, shown.length + (unit ? Math.ceil(unit.length * 0.6) : 0));
}

export function compact(value: number, maximumFractionDigits = 1): string {
  if (!Number.isFinite(value)) return "—";
  if (Math.abs(value) < 10000) {
    return numbers({ ...GROUPED, maximumFractionDigits }).format(value);
  }
  return numbers({ notation: "compact", maximumFractionDigits }).format(value);
}

export const plain = (value: number, maximumFractionDigits = 0): string =>
  Number.isFinite(value)
    ? numbers({ ...GROUPED, maximumFractionDigits }).format(value)
    : "—";

export function signed(value: number, maximumFractionDigits = 1): string {
  if (!Number.isFinite(value)) return "—";
  return numbers({ maximumFractionDigits, signDisplay: "exceptZero" }).format(value);
}

export const percent = (value: number, maximumFractionDigits = 0): string =>
  Number.isFinite(value) ? `${signed(value, maximumFractionDigits)}%` : "—";

export const change = (current: number, previous: number): number | null =>
  previous === 0 ? null : ((current - previous) / Math.abs(previous)) * 100;

export const ratio = (value: number, target: number): number =>
  target <= 0 ? 0 : Math.max(0, Math.min(1, value / target));

export function duration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

const capitalised = (text: string) => text.charAt(0).toLocaleUpperCase(locale()) + text.slice(1);

export function todayIso(now = new Date()): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: timeZone() }).format(now);
}

export function shortDay(day: string): string {
  return dates({ day: "numeric", month: "short", timeZone: "UTC" })
    .format(new Date(`${day}T00:00:00Z`))
    .replace(".", "");
}

export function longDay(instant: string | Date): string {
  return capitalised(zonedDates({ weekday: "long", day: "numeric", month: "long" }).format(new Date(instant)));
}

export const clock = (instant: string | Date): string =>
  zonedDates({ hour: "2-digit", minute: "2-digit" }).format(new Date(instant));

export function money(value: number, currency = defaultCurrency(), cents: boolean | "auto" = "auto"): string {
  if (!Number.isFinite(value)) return "—";
  const digits = cents === "auto" ? (Number.isInteger(value) ? 0 : 2) : cents ? 2 : 0;
  return numbers({
    style: "currency",
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}
