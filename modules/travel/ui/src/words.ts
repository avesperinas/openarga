import type { IconName } from "@openarga/ui";

import type { Category, Kind, Mode, Phase, PlaceCategory } from "./api";
import { currentZone, intl, plural, t } from "./lang";

function labels<K extends string>(keys: K[], prefix: string): Record<K, string> {
  const found = {} as Record<K, string>;
  for (const key of keys) Object.defineProperty(found, key, { enumerable: true, get: () => t(`${prefix}.${key}`) });
  return found;
}

export const MODES: Record<Mode, { readonly label: string; icon: IconName }> = {
  plane: { get label() { return t("mode.plane"); }, icon: "plane" },
  train: { get label() { return t("mode.train"); }, icon: "train" },
  car: { get label() { return t("mode.car"); }, icon: "car" },
  bus: { get label() { return t("mode.bus"); }, icon: "bus" },
  boat: { get label() { return t("mode.boat"); }, icon: "boat" },
};

export const PHASES: Record<Phase, string> = labels(["plan", "upcoming", "ongoing", "done"], "phase");

export const KINDS: Record<Kind, { readonly label: string; icon: IconName }> = {
  activity: { get label() { return t("kind.activity"); }, icon: "pin" },
  transport: { get label() { return t("kind.transport"); }, icon: "car" },
  meal: { get label() { return t("kind.meal"); }, icon: "basket" },
  accommodation: { get label() { return t("kind.accommodation"); }, icon: "home" },
  free_time: { get label() { return t("kind.free_time"); }, icon: "sun" },
  other: { get label() { return t("kind.other"); }, icon: "note" },
};

export const PLACE_CATEGORIES: Record<PlaceCategory, { readonly label: string; icon: IconName; hue: Hue }> = {
  restaurant: { get label() { return t("place.restaurant"); }, icon: "food", hue: 4 },
  cafe: { get label() { return t("place.cafe"); }, icon: "cup", hue: 3 },
  market: { get label() { return t("place.market"); }, icon: "basket", hue: 3 },
  nightlife: { get label() { return t("place.nightlife"); }, icon: "party", hue: 7 },
  beach: { get label() { return t("place.beach"); }, icon: "umbrella", hue: 6 },
  nature: { get label() { return t("place.nature"); }, icon: "mountain", hue: 2 },
  viewpoint: { get label() { return t("place.viewpoint"); }, icon: "binoculars", hue: 5 },
  culture: { get label() { return t("place.culture"); }, icon: "landmark", hue: 1 },
  castle: { get label() { return t("place.castle"); }, icon: "castle", hue: 8 },
  town: { get label() { return t("place.town"); }, icon: "home", hue: 2 },
  shopping: { get label() { return t("place.shopping"); }, icon: "bag", hue: 7 },
  parking: { get label() { return t("place.parking"); }, icon: "parking", hue: 1 },
  lodging: { get label() { return t("place.lodging"); }, icon: "bed", hue: 5 },
  other: { get label() { return t("place.other"); }, icon: "pin", hue: 8 },
};

export type Hue = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

const DAY_HUES: Hue[] = [1, 2, 3, 4, 5, 6, 7];

export const dayHue = (number: number): Hue => DAY_HUES[(Math.max(1, number) - 1) % DAY_HUES.length]!;

export const categoryOf = (place: { category?: PlaceCategory | null } | null | undefined) =>
  PLACE_CATEGORIES[place?.category ?? "other"];

export function mapsLink(lat: number, lon: number, name: string, apple = isApple()): string {
  const point = `${lat.toFixed(6)},${lon.toFixed(6)}`;
  return apple
    ? `https://maps.apple.com/?ll=${point}&q=${encodeURIComponent(name)}`
    : `https://www.google.com/maps/search/?api=1&query=${point}`;
}

function isApple(): boolean {
  if (typeof navigator === "undefined") return false;
  return /iPhone|iPad|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
}

export function hours(starts: string | null, ends: string | null = null): string {
  if (!starts) return "";
  const a = starts.slice(0, 5);
  return ends ? `${a}–${ends.slice(0, 5)}` : a;
}

export const CATEGORIES: Record<Category, string> = labels(["transport", "lodging", "other"], "spend");

const DAY: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", timeZone: "UTC" };
const DAY_YEAR: Intl.DateTimeFormatOptions = { ...DAY, year: "numeric" };
const WEEKDAY: Intl.DateTimeFormatOptions = { ...DAY, weekday: "short" };
const formatted = (options: Intl.DateTimeFormatOptions, date: Date) => new Intl.DateTimeFormat(intl(), options).format(date);

const at = (day: string) => new Date(`${day}T00:00:00Z`);
const tidy = (text: string) => text.replace(/\./g, "").replace(",", "");

export function dateRange(starts: string, ends: string): string {
  const a = at(starts);
  const b = at(ends);
  if (starts === ends) return tidy(formatted(DAY_YEAR, a));
  if (a.getUTCFullYear() !== b.getUTCFullYear()) {
    return `${tidy(formatted(DAY_YEAR, a))} – ${tidy(formatted(DAY_YEAR, b))}`;
  }
  if (a.getUTCMonth() === b.getUTCMonth()) {
    const end = tidy(formatted(DAY_YEAR, b));
    return end.startsWith(String(b.getUTCDate())) ? `${a.getUTCDate()}–${end}` : `${tidy(formatted(DAY, a))} – ${end}`;
  }
  return `${tidy(formatted(DAY, a))} – ${tidy(formatted(DAY_YEAR, b))}`;
}

export const dayLabel = (day: string) => tidy(formatted(WEEKDAY, at(day)));

export const nights = (count: number): string => plural(count, "count.nights");

export const trips = (count: number): string => plural(count, "count.trips");

const number = (value: number, options: Intl.NumberFormatOptions) => new Intl.NumberFormat(intl(), options).format(value);
const MONEY = { style: "currency", currency: "EUR" } as const;

export const euros = (value: number) => number(value, { ...MONEY, maximumFractionDigits: 0 });
export const eurosExact = (value: number) =>
  number(value, { ...MONEY, minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const whole = (value: number) => number(value, { maximumFractionDigits: 0 });
export const km = (value: number) => `${whole(value)} km`;

export function flag(code: string | null): string {
  if (!code || !/^[A-Z]{2}$/.test(code)) return "";
  return String.fromCodePoint(...[...code].map((letter) => 0x1f1e6 + letter.charCodeAt(0) - 65));
}

export function where(place: { name: string; region: string | null; country: string | null }): string {
  return [place.name, place.region, place.country].filter(Boolean).join(", ");
}

export function daysBetween(from: string, to: string): number {
  return Math.round((at(to).getTime() - at(from).getTime()) / 86_400_000);
}

export function addDays(day: string, count: number): string {
  const moved = at(day);
  moved.setUTCDate(moved.getUTCDate() + count);
  return moved.toISOString().slice(0, 10);
}

export const todayIso = (now: Date = new Date(), zone: string = currentZone()): string =>
  new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);

export function distance(metres: number): string {
  if (metres < 1000) return `${Math.round(metres / 10) * 10} m`;
  return `${number(metres / 1000, { maximumFractionDigits: 1 })} km`;
}

export function duration(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  const rest = minutes % 60;
  return rest ? `${Math.floor(minutes / 60)} h ${rest} min` : `${minutes / 60} h`;
}

export const monthShort = (month: number): string =>
  tidy(new Intl.DateTimeFormat(intl(), { month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(2000, month - 1, 1))));

export function daysRange(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  if (min !== null && max !== null && min !== max) return t("count.days.range", { min, max });
  return plural((min ?? max)!, "count.days");
}

export function monthsLabel(months: number[]): string {
  const sorted = [...new Set(months)].sort((a, b) => a - b);
  const runs: [number, number][] = [];
  for (const month of sorted) {
    const last = runs.at(-1);
    if (last && last[1] === month - 1) last[1] = month;
    else runs.push([month, month]);
  }
  return runs
    .map(([a, b]) => (a === b ? monthShort(a) : `${monthShort(a)}–${monthShort(b)}`))
    .join(", ");
}

export function paidLine(expense: { amount?: number | null; currency?: string; fx_rate?: number | null }): string | null {
  if (expense.amount == null || !expense.currency || (expense.currency === "EUR" && expense.fx_rate == null)) return null;
  const amount = number(expense.amount, { maximumFractionDigits: 2 });
  return `${amount} ${expense.currency}`;
}
