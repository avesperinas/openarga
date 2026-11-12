import { shortDay, todayIso } from "@openarga/ui";

import type { Book, Format, Reading, Status } from "./api";

export { todayIso };

export const STATUSES: { value: Status; label: string }[] = [
  { value: "want", label: "Quiero leerlo" },
  { value: "reading", label: "Leyendo" },
  { value: "read", label: "Leído" },
  { value: "abandoned", label: "Abandonado" },
];

export const FORMATS: { value: Format; label: string }[] = [
  { value: "paper", label: "Papel" },
  { value: "ebook", label: "Ebook" },
  { value: "audio", label: "Audio" },
];

export function stars(rating: number | null): string {
  if (rating === null) return "";
  return `★ ${rating.toLocaleString("es-ES", { maximumFractionDigits: 1 })}`;
}

export function authorsOf(book: Pick<Book, "authors">): string {
  return book.authors.join(", ");
}

export function rowDetail(book: Book): string {
  const parts: string[] = [];
  if (book.status === "reading" && book.started_on) parts.push(`desde el ${shortDay(book.started_on)}`);
  if (book.status === "read" && book.finished_on) parts.push(shortDay(book.finished_on));
  if (book.status === "abandoned") parts.push("abandonado");
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
    const year = (book.finished_on ?? book.started_on ?? "").slice(0, 4) || "Sin fecha";
    byYear.set(year, [...(byYear.get(year) ?? []), book]);
  }
  const years = [...byYear.keys()].sort((a, b) => b.localeCompare(a));
  return [
    ...(reading.length ? [{ id: "reading", title: "Leyendo", books: reading }] : []),
    ...years.map((year) => ({ id: year, title: year, books: byYear.get(year)! })),
    ...(want.length ? [{ id: "want", title: "Quiero leerlos", books: want }] : []),
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
    candidate.pages ? `${candidate.pages} págs.` : "",
    candidate.language ?? "",
    SOURCE_NAMES[candidate.source] ?? candidate.source,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function failedNote(failed: { source: string; reason: string }[]): string {
  return failed.map((one) => `${SOURCE_NAMES[one.source] ?? one.source}: ${one.reason}`).join(". ");
}

export const STATUS_NAMES: Record<Status, string> = {
  want: "Quiero leerlo",
  reading: "Leyendo",
  read: "Leído",
  abandoned: "Abandonado",
};

const LANGUAGE_NAMES: Record<string, string> = {
  es: "español",
  en: "inglés",
  eu: "euskera",
  ca: "catalán",
  gl: "gallego",
  fr: "francés",
  de: "alemán",
  it: "italiano",
  pt: "portugués",
};

export function editionLine(book: Book): string {
  return [
    book.pages ? `${book.pages} páginas` : "",
    book.year?.toString() ?? "",
    book.language ? (LANGUAGE_NAMES[book.language] ?? book.language) : "",
    book.isbn13 ? `ISBN ${book.isbn13}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

export function datesLine(book: Book, today = todayIso()): string {
  const { started_on: started, finished_on: finished } = book;
  if (book.status === "want") return "Todavía sin empezar";
  if (book.status === "reading" && started) {
    const days = Math.round((Date.parse(today) - Date.parse(started)) / 86_400_000) + 1;
    return `Desde el ${shortDay(started)} · ${days === 1 ? "hoy" : `${days} días`}`;
  }
  if (started && finished) {
    const days = book.days ?? 0;
    const verb = book.status === "abandoned" ? "Dejado" : "Leído";
    return `${verb} del ${shortDay(started)} al ${shortDay(finished)} · ${days === 1 ? "en un día" : `${days} días`}`;
  }
  if (started) return `Empezado el ${shortDay(started)}`;
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

export function goalFoot(stats: { books: number; goal: number | null; goal_pace: number | null }): string {
  if (!stats.goal) return "sin objetivo";
  const base = `de ${stats.goal}`;
  if (stats.goal_pace === null) return base;
  const ahead = stats.books - stats.goal_pace;
  if (Math.abs(ahead) < 0.5) return `${base} · vas al día`;
  const count = Math.round(Math.abs(ahead));
  return `${base} · ${count} ${ahead > 0 ? "por delante" : "por detrás"}`;
}

export function shareItems(shares: { id: string; name: string; books: number }[]) {
  return shares.map((share) => ({ key: share.id, name: share.name, value: share.books }));
}

export function ratingRows(ratings: Record<string, number>): { label: string; value: string }[] {
  return Object.entries(ratings)
    .sort(([a], [b]) => Number(b) - Number(a))
    .map(([rating, count]) => ({ label: stars(Number(rating)), value: count === 1 ? "1 libro" : `${count} libros` }));
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
