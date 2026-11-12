import type { DayMark, IconName } from "@openarga/ui";

import type { AgendaEvent, Area, Category, Kind, Period, Place, Planned, When, Wish, Zone } from "./api";

export const KINDS: { value: Kind; label: string; plural: string; icon: IconName; hue: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 }[] = [
  { value: "eat", label: "Restaurante", plural: "Restaurantes", icon: "food", hue: 4 },
  { value: "plan", label: "Plan", plural: "Planes", icon: "calendar", hue: 1 },
  { value: "getaway", label: "Escapada", plural: "Escapadas", icon: "mountain", hue: 2 },
  { value: "trip", label: "Viaje", plural: "Viajes", icon: "plane", hue: 6 },
];

export const kindOf = (kind: Kind) => KINDS.find((one) => one.value === kind)!;

export type WishTab = "outings" | "eat" | "trips";

export const WISH_TABS: { value: WishTab; label: string }[] = [
  { value: "outings", label: "Excursiones" },
  { value: "eat", label: "Restaurantes" },
  { value: "trips", label: "Viajes" },
];

const TAB_KINDS: Record<WishTab, Kind[]> = {
  outings: ["getaway", "plan"],
  eat: ["eat"],
  trips: ["trip"],
};

export const NEW_KIND: Record<WishTab, Kind> = { outings: "getaway", eat: "eat", trips: "trip" };

export const inTab = (wish: Wish, tab: WishTab) => TAB_KINDS[tab].includes(wish.kind);

export function placeLine(place: Place | null | undefined): string | undefined {
  if (!place) return undefined;
  const parts = [place.town, place.country].filter(
    (part): part is string => Boolean(part) && part !== place.name,
  );
  if (parts.length === 0) return place.name;
  return parts.join(", ");
}

export function wishLine(wish: Wish): string | undefined {
  const line = placeOrText(wish);
  if (wish.space_id) return line ? `${line} · Compartida` : "Compartida";
  return line;
}

function placeOrText(wish: Wish): string | undefined {
  const where = wish.place ? placeLine(wish.place) : undefined;
  if (where && wish.place && where !== wish.place.name) return `${wish.place.name} · ${where}`;
  if (where) return where;
  return wish.body?.split("\n")[0]?.slice(0, 80) || undefined;
}

export interface WishGroup {
  id: string;
  title: string;
  layout: "cards" | "rows";
  wishes: Wish[];
}

export function cardLine(wish: Wish): string | undefined {
  const where = placeLine(wish.place);
  if (where && where !== wish.name) return where;
  return wish.body?.split("\n")[0]?.slice(0, 80) || undefined;
}

export function groups(wishes: Wish[], tab: WishTab): WishGroup[] {
  const of = (kind: Kind) => wishes.filter((one) => one.kind === kind);
  const all: Record<WishTab, WishGroup[]> = {
    outings: [
      { id: "getaway", title: "Escapadas", layout: "cards", wishes: of("getaway") },
      { id: "plan", title: "Planes cerca", layout: "rows", wishes: of("plan") },
    ],
    eat: [{ id: "eat", title: "Restaurantes", layout: "rows", wishes: of("eat") }],
    trips: [{ id: "trip", title: "Viajes", layout: "cards", wishes: of("trip") }],
  };
  return all[tab].filter((group) => group.wishes.length > 0);
}

const DAY = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "long", year: "numeric" });

export function doneLine(wish: Wish): string | undefined {
  if (!wish.done_at) return undefined;
  return `Hecha el ${DAY.format(new Date(wish.done_at))}`;
}

export const PLACEHOLDERS: Record<Kind, { name: string; body: string; place: string }> = {
  eat: { name: "Asador en la Ribera", body: "Qué pedir, quién lo recomendó…", place: "Un bar, un restaurante, una calle" },
  plan: { name: "Subir a San Cristóbal", body: "Cuándo, con quién, qué hace falta…", place: "Dónde es" },
  getaway: { name: "Selva de Irati", body: "Ir en noviembre, con el hayedo rojo…", place: "Un pueblo, un parque, una sierra" },
  trip: { name: "Japón", body: "Cuándo, qué ver…", place: "Un país o una ciudad (opcional)" },
};

export const CATEGORIES: { value: Category; label: string; icon: IconName; hue: 1 | 2 | 3 | 4 | 5 }[] = [
  { value: "eat", label: "Comer", icon: "food", hue: 4 },
  { value: "stage", label: "Escena", icon: "music", hue: 5 },
  { value: "culture", label: "Cultura", icon: "landmark", hue: 1 },
  { value: "festival", label: "Fiestas", icon: "party", hue: 3 },
  { value: "outdoors", label: "Fuera", icon: "mountain", hue: 2 },
];

export const categoryOf = (category: Category) => CATEGORIES.find((one) => one.value === category)!;

export const PERIODS: { value: Period; label: string }[] = [
  { value: "weekend", label: "Finde" },
  { value: "week", label: "Semana" },
  { value: "month", label: "Mes" },
  { value: "year", label: "Año" },
];

const WEEKDAY = new Intl.DateTimeFormat("es-ES", { weekday: "long", timeZone: "UTC" });
const DAY_MONTH = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "long", timeZone: "UTC" });
const SHORT_DAY = new Intl.DateTimeFormat("es-ES", { weekday: "short", day: "numeric", timeZone: "UTC" });

const at = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00Z`);
const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export function longDay(iso: string): string {
  return capital(`${WEEKDAY.format(at(iso))}, ${DAY_MONTH.format(at(iso))}`);
}

export function dayTitle(iso: string, withMonth = false): string {
  const date = at(iso);
  return capital(withMonth ? `${WEEKDAY.format(date)} ${DAY_MONTH.format(date)}` : `${WEEKDAY.format(date)} ${date.getUTCDate()}`);
}

export function shortDay(iso: string): string {
  return capital(SHORT_DAY.format(at(iso)).replace(".", "").replace(",", ""));
}

export function span(event: Pick<AgendaEvent, "starts_on" | "ends_on">): string {
  const first = at(event.starts_on);
  const last = at(event.ends_on);
  if (event.starts_on === event.ends_on) return DAY_MONTH.format(first);
  if (first.getUTCMonth() === last.getUTCMonth()) return `${first.getUTCDate()} – ${DAY_MONTH.format(last)}`;
  return `${DAY_MONTH.format(first)} – ${DAY_MONTH.format(last)}`;
}

export const isoDay = (date: Date) => date.toISOString().slice(0, 10);

export interface AgendaDay {
  day: string;
  events: AgendaEvent[];
}

export function arrange(events: AgendaEvent[], from: string, today: string): { now: AgendaEvent[]; days: AgendaDay[] } {
  const now = events.filter((one) => one.starts_on < today && one.ends_on >= today);
  const rest = events.filter((one) => !now.includes(one));
  const days = new Map<string, AgendaEvent[]>();
  for (const event of rest) {
    const day = event.starts_on < from ? from : event.starts_on;
    days.set(day, [...(days.get(day) ?? []), event]);
  }
  return {
    now,
    days: [...days.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([day, found]) => ({ day, events: found })),
  };
}

export function until(event: Pick<AgendaEvent, "starts_on" | "ends_on">): string | undefined {
  if (event.ends_on === event.starts_on) return undefined;
  return `hasta el ${WEEKDAY.format(at(event.ends_on))} ${at(event.ends_on).getUTCDate()}`;
}

export function eventLine(event: AgendaEvent): string | undefined {
  const where = [event.venue, event.town].filter(Boolean).join(" · ");
  return [where, until(event)].filter(Boolean).join(" · ") || undefined;
}

const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

export const monthName = (month: number) => MONTHS[(month - 1 + 12) % 12]!;

export function since(iso: string, now = new Date()): string {
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "hoy";
  if (days === 1) return "ayer";
  return `hace ${days} días`;
}

export const WHENS: { value: When; label: string }[] = [
  { value: "weekend", label: "Finde" },
  { value: "week", label: "Semana" },
  { value: "month", label: "Mes" },
  { value: "quarter", label: "3 meses" },
  { value: "year", label: "Año" },
];

export type ZoneFilter = "all" | Zone;

export const zones = (area: Area | null): { value: ZoneFilter; label: string }[] => [
  { value: "all", label: "Todo" },
  { value: "near", label: area?.near ?? "Cerca" },
  { value: "region", label: area ? `Resto de ${area.region}` : "Resto" },
];

const MONTH_YEAR = new Intl.DateTimeFormat("es-ES", { month: "long", year: "numeric", timeZone: "UTC" });

export const monthTitle = (iso: string) => capital(MONTH_YEAR.format(at(iso)));

export function marksOf(events: AgendaEvent[]): Record<string, DayMark[]> {
  const marks: Record<string, DayMark[]> = {};
  for (const event of events) {
    const category = categoryOf(event.category);
    const last = at(event.ends_on).getTime();
    for (let day = at(event.starts_on).getTime(), n = 0; day <= last && n < 62; day += 86_400_000, n++) {
      const iso = new Date(day).toISOString().slice(0, 10);
      (marks[iso] ??= []).push({ kind: `hue-${category.hue}`, label: event.title });
    }
  }
  return marks;
}

export const onDay = (events: AgendaEvent[], day: string) =>
  events.filter((one) => one.starts_on <= day && one.ends_on >= day);

export const PLANNED_PHASE: Record<Planned["phase"], string> = {
  idea: "Idea",
  plan: "Plan",
  upcoming: "Confirmado",
  ongoing: "En curso",
};

const SHORT = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", timeZone: "UTC" });

export function plannedLine(trip: Pick<Planned, "starts_on" | "ends_on" | "detail">): string {
  const day = (iso: string) => SHORT.format(new Date(`${iso}T00:00:00Z`));
  const dates = trip.starts_on && trip.ends_on ? `${day(trip.starts_on)} – ${day(trip.ends_on)}` : "";
  return [dates, trip.detail].filter(Boolean).join(" · ");
}

export function freshSince(param: string | null, today: string): { since: string; fromNotice: boolean } {
  if (param && /^\d{4}-\d{2}-\d{2}$/.test(param) && param <= today) return { since: param, fromNotice: true };
  const week = new Date(`${today}T12:00:00Z`);
  week.setUTCDate(week.getUTCDate() - 6);
  return { since: week.toISOString().slice(0, 10), fromNotice: false };
}

export function freshTitle(since: string, fromNotice: boolean, today: string): string {
  if (!fromNotice) return "Lo nuevo esta semana";
  if (since === today) return "Lo nuevo de hoy";
  return `Lo nuevo desde el ${dayTitle(since).toLowerCase()}`;
}
