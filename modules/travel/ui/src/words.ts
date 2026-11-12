import type { IconName } from "@openarga/ui";

import type { Category, Kind, Mode, Phase, PlaceCategory } from "./api";

export const MODES: Record<Mode, { label: string; icon: IconName }> = {
  plane: { label: "Avión", icon: "plane" },
  train: { label: "Tren", icon: "train" },
  car: { label: "Coche", icon: "car" },
  bus: { label: "Bus", icon: "bus" },
  boat: { label: "Barco", icon: "boat" },
};

export const PHASES: Record<Phase, string> = {
  plan: "Plan",
  upcoming: "Confirmado",
  ongoing: "En curso",
  done: "Hecho",
};

export const KINDS: Record<Kind, { label: string; icon: IconName }> = {
  activity: { label: "Visita", icon: "pin" },
  transport: { label: "Transporte", icon: "car" },
  meal: { label: "Comida", icon: "basket" },
  accommodation: { label: "Alojamiento", icon: "home" },
  free_time: { label: "Libre", icon: "sun" },
  other: { label: "Otro", icon: "note" },
};

export const PLACE_CATEGORIES: Record<PlaceCategory, { label: string; icon: IconName; hue: Hue }> = {
  restaurant: { label: "Restaurante", icon: "food", hue: 4 },
  cafe: { label: "Cafetería", icon: "cup", hue: 3 },
  market: { label: "Shopping", icon: "basket", hue: 3 },
  nightlife: { label: "Bares y noche", icon: "party", hue: 7 },
  beach: { label: "Playa", icon: "umbrella", hue: 6 },
  nature: { label: "Naturaleza", icon: "mountain", hue: 2 },
  viewpoint: { label: "Mirador", icon: "binoculars", hue: 5 },
  culture: { label: "Museos y cultura", icon: "landmark", hue: 1 },
  castle: { label: "Castillos y ruinas", icon: "castle", hue: 8 },
  town: { label: "Pueblo o ciudad", icon: "home", hue: 2 },
  shopping: { label: "Compras", icon: "bag", hue: 7 },
  parking: { label: "Aparcamiento", icon: "parking", hue: 1 },
  lodging: { label: "Alojamiento", icon: "bed", hue: 5 },
  other: { label: "Otro", icon: "pin", hue: 8 },
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

export const CATEGORIES: Record<Category, string> = {
  transport: "Transporte",
  lodging: "Alojamiento",
  other: "Gastos",
};

const DAY = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", timeZone: "UTC" });
const DAY_YEAR = new Intl.DateTimeFormat("es-ES", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const WEEKDAY = new Intl.DateTimeFormat("es-ES", {
  weekday: "short",
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});

const at = (day: string) => new Date(`${day}T00:00:00Z`);
const tidy = (text: string) => text.replace(/\./g, "");

export function dateRange(starts: string, ends: string): string {
  const a = at(starts);
  const b = at(ends);
  if (starts === ends) return tidy(DAY_YEAR.format(a));
  if (a.getUTCFullYear() !== b.getUTCFullYear()) {
    return `${tidy(DAY_YEAR.format(a))} – ${tidy(DAY_YEAR.format(b))}`;
  }
  if (a.getUTCMonth() === b.getUTCMonth()) {
    return `${a.getUTCDate()}–${tidy(DAY_YEAR.format(b))}`;
  }
  return `${tidy(DAY.format(a))} – ${tidy(DAY_YEAR.format(b))}`;
}

export const dayLabel = (day: string) => tidy(WEEKDAY.format(at(day)));

export function nights(count: number): string {
  return count === 1 ? "1 noche" : `${count} noches`;
}

export function trips(count: number): string {
  return count === 1 ? "1 viaje" : `${count} viajes`;
}

const EUROS = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const EUROS_CENTS = new Intl.NumberFormat("es-ES", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const WHOLE = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 });

export const euros = (value: number) => EUROS.format(value);
export const eurosExact = (value: number) => EUROS_CENTS.format(value);
export const whole = (value: number) => WHOLE.format(value);
export const km = (value: number) => `${WHOLE.format(value)} km`;

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

export function todayIso(now: Date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function distance(metres: number): string {
  if (metres < 1000) return `${Math.round(metres / 10) * 10} m`;
  return `${(metres / 1000).toLocaleString("es-ES", { maximumFractionDigits: 1 })} km`;
}

export function duration(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  const rest = minutes % 60;
  return rest ? `${Math.floor(minutes / 60)} h ${rest} min` : `${minutes / 60} h`;
}

export const MONTHS_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

export function daysRange(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  if (min !== null && max !== null && min !== max) return `${min}–${max} días`;
  const one = (min ?? max)!;
  return `${one} día${one === 1 ? "" : "s"}`;
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
    .map(([a, b]) => (a === b ? MONTHS_SHORT[a - 1] : `${MONTHS_SHORT[a - 1]}–${MONTHS_SHORT[b - 1]}`))
    .join(", ");
}

export function paidLine(expense: { amount?: number | null; currency?: string; fx_rate?: number | null }): string | null {
  if (expense.amount == null || !expense.currency || (expense.currency === "EUR" && expense.fx_rate == null)) return null;
  const amount = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2 }).format(expense.amount);
  return `${amount} ${expense.currency}`;
}
