import { addDays, dayKey, dayRange, dayStart, formatMonth, isoWeek, mondayOf } from "@openarga/ui";

export type View = "day" | "three" | "week" | "month" | "agenda";

export const VIEWS: { value: View; label: string; short: string; slug: string; key: string }[] = [
  { value: "day", label: "Día", short: "Día", slug: "dia", key: "d" },
  { value: "three", label: "3 días", short: "3 días", slug: "3dias", key: "3" },
  { value: "week", label: "Semana", short: "Semana", slug: "semana", key: "w" },
  { value: "month", label: "Mes", short: "Mes", slug: "mes", key: "m" },
  { value: "agenda", label: "Agenda", short: "Agenda", slug: "agenda", key: "a" },
];

export const ROOT = "/planner";
export const AGENDA_DAYS = 60;

export interface Place {
  view: View;
  day: string;
}

export function defaultView(width: number): View {
  return width < 720 ? "three" : "week";
}

export function parsePlace(pathname: string, width: number, today: string): Place {
  const parts = pathname.replace(/^\/planner\/?/, "").split("/").filter(Boolean);
  const found = VIEWS.find((v) => v.slug === parts[0]);
  const day = parts[1] && /^\d{4}-\d{2}(-\d{2})?$/.test(parts[1]) ? (parts[1].length === 7 ? `${parts[1]}-01` : parts[1]) : today;
  return { view: found?.value ?? defaultView(width), day };
}

export function pathOf(place: Place, today: string): string {
  const slug = VIEWS.find((v) => v.value === place.view)!.slug;
  if (place.view === "agenda" && place.day === today) return `${ROOT}/agenda`;
  const day = place.view === "month" && place.day.endsWith("-01") ? place.day.slice(0, 7) : place.day;
  return `${ROOT}/${slug}/${day}`;
}

export function visibleDays(place: Place): string[] {
  switch (place.view) {
    case "day":
      return [place.day];
    case "three":
      return dayRange(place.day, 3);
    case "week":
      return dayRange(mondayOf(place.day), 7);
    case "month":
      return dayRange(mondayOf(place.day), 42);
    case "agenda":
      return dayRange(place.day, AGENDA_DAYS);
  }
}

export function monthOf(place: Place): string {
  return addDays(mondayOf(place.day), 21).slice(0, 7);
}

export function scroll(place: Place, weeks: number): Place {
  return { ...place, day: addDays(mondayOf(place.day), 7 * weeks) };
}

export function step(place: Place, direction: number): Place {
  switch (place.view) {
    case "day":
      return { ...place, day: addDays(place.day, direction) };
    case "three":
      return { ...place, day: addDays(place.day, direction) };
    case "week":
      return { ...place, day: addDays(mondayOf(place.day), 7 * direction) };
    case "month": {
      const date = dayStart(`${monthOf(place)}-01`);
      date.setMonth(date.getMonth() + direction);
      return { ...place, day: dayKey(date) };
    }
    case "agenda":
      return { ...place, day: addDays(place.day, 30 * direction) };
  }
}

export function switchView(place: Place, view: View, today: string): Place {
  if (view === "month") return { view, day: `${place.day.slice(0, 7)}-01` };
  if (place.view === "month") {
    const month = monthOf(place);
    return { view, day: today.slice(0, 7) === month ? today : `${month}-01` };
  }
  return { view, day: place.day };
}

const monthShort = new Intl.DateTimeFormat("es-ES", { month: "short" });
const monthLong = new Intl.DateTimeFormat("es-ES", { month: "long" });
const dayLong = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "long" });

const cap = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export function titleOf(place: Place): { title: string; week?: number } {
  const days = visibleDays(place);
  if (place.view === "month") return { title: formatMonth(`${monthOf(place)}-01`) };
  if (place.view === "day") {
    const date = dayStart(place.day);
    return { title: cap(dayLong.format(date)), week: isoWeek(place.day) };
  }
  if (place.view === "agenda") return { title: "Agenda" };
  const first = dayStart(days[0]!);
  const last = dayStart(days[days.length - 1]!);
  const week = place.view === "week" ? isoWeek(days[0]!) : undefined;
  if (first.getMonth() === last.getMonth()) {
    return { title: `${cap(monthLong.format(first))} ${first.getFullYear()}`, week };
  }
  const a = monthShort.format(first).replace(".", "");
  const b = monthShort.format(last).replace(".", "");
  const sameYear = first.getFullYear() === last.getFullYear();
  const from = sameYear ? cap(a) : `${cap(a)} ${first.getFullYear()}`;
  return { title: `${from} – ${b} ${last.getFullYear()}`, week };
}

export function fetchWindow(place: Place): { from: Date; to: Date } {
  const days = visibleDays(place);
  if (place.view === "month") {
    const from = dayStart(`${addDays(days[0]!, -7).slice(0, 7)}-01`);
    const to = dayStart(`${addDays(days[days.length - 1]!, 7).slice(0, 7)}-01`);
    to.setMonth(to.getMonth() + 1);
    return { from, to };
  }
  const pad = place.view === "agenda" ? 1 : days.length;
  return {
    from: dayStart(addDays(days[0]!, -pad)),
    to: dayStart(addDays(days[days.length - 1]!, pad + 1)),
  };
}
