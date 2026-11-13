import { shortDay, todayIso } from "@openarga/ui";

import type { Book, Format, Reading, Status } from "./api";
import { intl, t } from "./lang";

export { todayIso };

const STATUS_VALUES: Status[] = ["want", "reading", "read", "abandoned"];
const FORMAT_VALUES: Format[] = ["paper", "ebook", "audio"];

export const statuses = (): { value: Status; label: string }[] =>
  STATUS_VALUES.map((value) => ({ value, label: t(`status.${value}`) }));

export const formats = (): { value: Format; label: string }[] =>
  FORMAT_VALUES.map((value) => ({ value, label: t(`format.${value}`) }));

export const statusName = (status: Status) => t(`status.${status}`);

export function stars(rating: number | null): string {
  if (rating === null) return "";
  return `★ ${rating.toLocaleString(intl(), { maximumFractionDigits: 1 })}`;
}

export function authorsOf(book: Pick<Book, "authors">): string {
  return book.authors.join(", ");
}

export function rowDetail(book: Book): string {
  const parts: string[] = [];
  if (book.status === "reading" && book.started_on) parts.push(t("row.since", { day: shortDay(book.started_on) }));
  if (book.status === "read" && book.finished_on) parts.push(shortDay(book.finished_on));
  if (book.status === "abandoned") parts.push(t("row.abandoned"));
  if (book.rating !== null) parts.push(stars(book.rating));
  return parts.join(" · ");
}

export interface Shelf {
  id: string;
  title: string;
  books: Book[];
}

export function shelves(books: Book[]): Shelf[] {
  const reading = books.filter((book) => book.status === "reading");
  const want = books.filter((book) => book.status === "want");
  const byYear = new Map<string, Book[]>();
  for (const book of books) {
    if (book.status !== "read" && book.status !== "abandoned") continue;
    const year = (book.finished_on ?? book.started_on ?? "").slice(0, 4) || t("shelf.no_date");
    byYear.set(year, [...(byYear.get(year) ?? []), book]);
  }
  const years = [...byYear.keys()].sort((a, b) => b.localeCompare(a));
  return [
    ...(reading.length ? [{ id: "reading", title: t("shelf.reading"), books: reading }] : []),
    ...years.map((year) => ({ id: year, title: year, books: byYear.get(year)! })),
    ...(want.length ? [{ id: "want", title: t("shelf.want"), books: want }] : []),
  ];
}

export function withStatus(reading: Reading, status: Status, today: string): Reading {
  const started = reading.started_on ?? today;
  switch (status) {
    case "want":
      return { ...reading, status, started_on: null, finished_on: null };
    case "reading":
      return { ...reading, status, started_on: started, finished_on: null };
    case "read":
      return { ...reading, status, started_on: started, finished_on: reading.finished_on ?? today };
    case "abandoned":
      return { ...reading, status, started_on: started };
  }
}

export function splitAuthors(text: string): string[] {
  return text
    .split(",")
    .map((name) => name.trim())
    .filter(Boolean);
}

const SOURCE_NAMES: Record<string, string> = { openlibrary: "Open Library", google_books: "Google Books" };

export function candidateDetail(
  candidate: { year: number | null; pages: number | null; language: string | null; source: string; authors: string[] },
  withAuthors = false,
): string {
  return [
    withAuthors ? candidate.authors.join(", ") : "",
    candidate.year?.toString() ?? "",
    candidate.pages ? t("edition.pages_short", { pages: candidate.pages }) : "",
    candidate.language ?? "",
    SOURCE_NAMES[candidate.source] ?? candidate.source,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function failedNote(failed: { source: string; reason: string }[]): string {
  return failed.map((one) => `${SOURCE_NAMES[one.source] ?? one.source}: ${one.reason}`).join(". ");
}

const languageName = (code: string): string => {
  try {
    return new Intl.DisplayNames([intl()], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
};

export function editionLine(book: Book): string {
  return [
    book.pages ? t("edition.pages", { pages: book.pages }) : "",
    book.year?.toString() ?? "",
    book.language ? languageName(book.language).toLocaleLowerCase(intl()) : "",
    book.isbn13 ? `ISBN ${book.isbn13}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

export function datesLine(book: Book, today = todayIso()): string {
  const { started_on: started, finished_on: finished } = book;
  if (book.status === "want") return t("dates.not_started");
  if (book.status === "reading" && started) {
    const days = Math.round((Date.parse(today) - Date.parse(started)) / 86_400_000) + 1;
    return t("dates.reading", { day: shortDay(started), span: days === 1 ? t("dates.today") : t("dates.days", { days }) });
  }
  if (started && finished) {
    const days = book.days ?? 0;
    const key = book.status === "abandoned" ? "dates.abandoned" : "dates.read";
    const span = days === 1 ? t("dates.one_day") : t("dates.days", { days });
    return t(key, { start: shortDay(started), end: shortDay(finished), span });
  }
  if (started) return t("dates.started", { day: shortDay(started) });
  return "";
}

export interface Filters {
  genre: string;
  format: string;
  rating: string;
}

export const NO_FILTERS: Filters = { genre: "all", format: "all", rating: "all" };

export function filtered(books: Book[], filters: Filters): Book[] {
  return books.filter(
    (book) =>
      (filters.genre === "all" || book.genre === filters.genre) &&
      (filters.format === "all" || book.format === filters.format) &&
      (filters.rating === "all" || (book.rating !== null && book.rating >= Number(filters.rating))),
  );
}

type GoalStats = { books: number; goal: number | null; goal_pace: number | null };

export function goalPace(stats: GoalStats): string {
  if (!stats.goal || stats.goal_pace === null) return "";
  const ahead = stats.books - stats.goal_pace;
  if (Math.abs(ahead) < 0.5) return t("goal.on_pace");
  return t(ahead > 0 ? "goal.ahead" : "goal.behind", { count: Math.round(Math.abs(ahead)) });
}

export function goalFoot(stats: GoalStats): string {
  if (!stats.goal) return t("goal.none");
  return [t("goal.of", { goal: stats.goal }), goalPace(stats)].filter(Boolean).join(" · ");
}

export function shareItems(shares: { id: string; name: string; books: number }[]) {
  return shares.map((share) => ({ key: share.id, name: share.name, value: share.books }));
}

export function ratingRows(ratings: Record<string, number>): { label: string; value: string }[] {
  return Object.entries(ratings)
    .sort(([a], [b]) => Number(b) - Number(a))
    .map(([rating, count]) => ({ label: stars(Number(rating)), value: count === 1 ? t("books.one") : t("books.other", { count }) }));
}

export function yearDays(year: number, pages: Record<string, number>, end: string): { day: string; value: number }[] {
  const days = [];
  for (let time = Date.UTC(year, 0, 1); ; time += 86_400_000) {
    const day = new Date(time).toISOString().slice(0, 10);
    if (day > end || !day.startsWith(String(year))) break;
    days.push({ day, value: pages[day] ?? 0 });
  }
  return days;
}
