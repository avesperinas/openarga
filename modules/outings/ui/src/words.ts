import type { DayMark, IconName } from "@openarga/ui";

import type { AgendaEvent, Area, Category, Kind, Period, Place, Planned, When, Wish, Zone } from "./api";
import { currentLocale, intl, t } from "./lang";

const KIND_LOOK: { value: Kind; icon: IconName; hue: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 }[] = [
  { value: "eat", icon: "food", hue: 4 },
  { value: "plan", icon: "calendar", hue: 1 },
  { value: "getaway", icon: "mountain", hue: 2 },
  { value: "trip", icon: "plane", hue: 6 },
];

export const kinds = () =>
  KIND_LOOK.map((one) => ({ ...one, label: t(`kind.${one.value}`), plural: t(`kind.${one.value}.plural`) }));

export const kindOf = (kind: Kind) => kinds().find((one) => one.value === kind)!;

export type WishTab = "outings" | "eat" | "trips";

export const wishTabs = (): { value: WishTab; label: string }[] => [
  { value: "outings", label: t("tab.outings") },
  { value: "eat", label: t("tab.eat") },
  { value: "trips", label: t("tab.trips") },
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
  if (wish.space_id) return line ? `${line} · ${t("wish.shared")}` : t("wish.shared");
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
      { id: "getaway", title: t("kind.getaway.plural"), layout: "cards", wishes: of("getaway") },
      { id: "plan", title: t("group.plans_near"), layout: "rows", wishes: of("plan") },
    ],
    eat: [{ id: "eat", title: t("kind.eat.plural"), layout: "rows", wishes: of("eat") }],
    trips: [{ id: "trip", title: t("kind.trip.plural"), layout: "cards", wishes: of("trip") }],
  };
  return all[tab].filter((group) => group.wishes.length > 0);
}

const format = (options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(intl(), { timeZone: "UTC", ...options });
const WEEKDAY = { format: (date: Date) => format({ weekday: "long" }).format(date) };
const DAY_MONTH = { format: (date: Date) => format({ day: "numeric", month: "long" }).format(date) };
const SHORT_DAY = { format: (date: Date) => format({ weekday: "short", day: "numeric" }).format(date) };

export function doneLine(wish: Wish): string | undefined {
  if (!wish.done_at) return undefined;
  const day = new Intl.DateTimeFormat(intl(), { day: "numeric", month: "long", year: "numeric" }).format(new Date(wish.done_at));
  return t("wish.done_on", { day });
}

export const placeholders = (kind: Kind): { name: string; body: string; place: string } => ({
  name: t(`placeholder.${kind}.name`),
  body: t(`placeholder.${kind}.body`),
  place: t(`placeholder.${kind}.place`),
});

const CATEGORY_LOOK: { value: Category; icon: IconName; hue: 1 | 2 | 3 | 4 | 5 }[] = [
  { value: "eat", icon: "food", hue: 4 },
  { value: "stage", icon: "music", hue: 5 },
  { value: "culture", icon: "landmark", hue: 1 },
  { value: "festival", icon: "party", hue: 3 },
  { value: "outdoors", icon: "mountain", hue: 2 },
];

export const categories = () => CATEGORY_LOOK.map((one) => ({ ...one, label: t(`category.${one.value}`) }));

export const categoryOf = (category: Category) => categories().find((one) => one.value === category)!;

export const periods = (): { value: Period; label: string }[] =>
  (["weekend", "week", "month", "year"] as const).map((value) => ({ value, label: t(`when.${value}`) }));

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
  return t("event.until", { day: `${WEEKDAY.format(at(event.ends_on))} ${at(event.ends_on).getUTCDate()}` });
}

export function eventLine(event: AgendaEvent): string | undefined {
  const where = [event.venue, event.town].filter(Boolean).join(" · ");
  return [where, until(event)].filter(Boolean).join(" · ") || undefined;
}

export const monthName = (month: number) =>
  format({ month: "long" }).format(new Date(Date.UTC(2000, (month - 1 + 12) % 12, 1)));

export function since(iso: string, now = new Date()): string {
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return t("since.today");
  if (days === 1) return t("since.yesterday");
  return t("since.days", { days });
}

export const WHEN_VALUES: When[] = ["weekend", "week", "month", "quarter", "year"];

export const whens = (): { value: When; label: string }[] => WHEN_VALUES.map((value) => ({ value, label: t(`when.${value}`) }));

export type ZoneFilter = "all" | Zone;

export const zones = (area: Area | null): { value: ZoneFilter; label: string }[] => [
  { value: "all", label: t("filter.all") },
  { value: "near", label: area?.near ?? t("zone.near") },
  { value: "region", label: area ? t("zone.rest_of", { region: area.region }) : t("zone.rest") },
];

export const monthTitle = (iso: string) => capital(format({ month: "long", year: "numeric" }).format(at(iso)));

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

export const plannedPhase = (phase: Planned["phase"]) => t(`phase.${phase}`);

export function plannedLine(trip: Pick<Planned, "starts_on" | "ends_on" | "detail">): string {
  const day = (iso: string) => format({ day: "numeric", month: "short" }).format(new Date(`${iso}T00:00:00Z`));
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
  if (!fromNotice) return t("fresh.week");
  if (since === today) return t("fresh.today");
  const day = dayTitle(since);
  return t("fresh.since", { day: currentLocale() === "en" ? day : day.toLowerCase() });
}
