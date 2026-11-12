const LOCALE = "es-ES";

const GROUPED = { useGrouping: "always" } as unknown as Intl.NumberFormatOptions;

export function figureChars(value: number | string, unit?: string): number {
  const shown = typeof value === "number" ? compact(value) : value;
  return Math.max(2, shown.length + (unit ? Math.ceil(unit.length * 0.6) : 0));
}

export function compact(value: number, maximumFractionDigits = 1): string {
  if (!Number.isFinite(value)) return "—";
  if (Math.abs(value) < 10000) {
    return new Intl.NumberFormat(LOCALE, { ...GROUPED, maximumFractionDigits }).format(value);
  }
  return new Intl.NumberFormat(LOCALE, {
    notation: "compact",
    maximumFractionDigits,
  }).format(value);
}

export const plain = (value: number, maximumFractionDigits = 0): string =>
  Number.isFinite(value)
    ? new Intl.NumberFormat(LOCALE, { ...GROUPED, maximumFractionDigits }).format(value)
    : "—";

export function signed(value: number, maximumFractionDigits = 1): string {
  if (!Number.isFinite(value)) return "—";
  const formatted = new Intl.NumberFormat(LOCALE, {
    maximumFractionDigits,
    signDisplay: "exceptZero",
  }).format(value);
  return formatted;
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

const ZONE = "Europe/Madrid";

const capitalised = (text: string) => text.charAt(0).toLocaleUpperCase(LOCALE) + text.slice(1);

export function todayIso(now = new Date()): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: ZONE }).format(now);
}

const SHORT_DAY = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short", timeZone: "UTC" });

export function shortDay(day: string): string {
  return SHORT_DAY.format(new Date(`${day}T00:00:00Z`)).replace(".", "");
}

const LONG_DAY = new Intl.DateTimeFormat(LOCALE, { weekday: "long", day: "numeric", month: "long", timeZone: ZONE });

export function longDay(instant: string | Date): string {
  return capitalised(LONG_DAY.format(new Date(instant)));
}

const CLOCK = new Intl.DateTimeFormat(LOCALE, { hour: "2-digit", minute: "2-digit", timeZone: ZONE });

export const clock = (instant: string | Date): string => CLOCK.format(new Date(instant));

export function money(value: number, currency = "EUR", cents: boolean | "auto" = "auto"): string {
  if (!Number.isFinite(value)) return "—";
  const digits = cents === "auto" ? (Number.isInteger(value) ? 0 : 2) : cents ? 2 : 0;
  return new Intl.NumberFormat(LOCALE, {
    style: "currency",
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}
