import { createApi } from "@openarga/app";

export { Unauthorised, problemOf, signIn } from "@openarga/app";

export const api = createApi("library");
const { get, send } = api;

export type Status = "want" | "reading" | "read" | "abandoned";
export type Format = "paper" | "ebook" | "audio";

export interface Genre {
  id: string;
  name: string;
}

export interface Reading {
  status: Status;
  started_on: string | null;
  finished_on: string | null;
  rating: number | null;
  format: Format;
  genre: string;
  note: string | null;
}

export interface Edition {
  title: string;
  subtitle?: string | null;
  authors: string[];
  pages?: number | null;
  language?: string | null;
  year?: number | null;
  isbn?: string | null;
}

export interface Book extends Reading {
  id: string;
  edition: "catalog" | "manual";
  edition_id: string;
  title: string;
  subtitle: string | null;
  authors: string[];
  pages: number | null;
  language: string | null;
  year: number | null;
  isbn13: string | null;
  has_cover: boolean;
  source: string;
  days: number | null;
}

export interface Candidate {
  source: "openlibrary" | "google_books";
  source_ref: string;
  title: string;
  subtitle: string | null;
  authors: string[];
  isbn13: string | null;
  pages: number | null;
  language: string | null;
  year: number | null;
  subjects: string[];
  cover_ref: string | null;
}

export interface FoundCandidate extends Candidate {
  genre_hint: string;
  known_id: string | null;
}

export function asCandidate(found: FoundCandidate): Candidate {
  const { source, source_ref, title, subtitle, authors, isbn13, pages, language, year, subjects, cover_ref } = found;
  return { source, source_ref, title, subtitle, authors, isbn13, pages, language, year, subjects, cover_ref };
}

export interface Search {
  candidates: FoundCandidate[];
  failed: { source: string; reason: string }[];
}

export const readGenres = () => get<Genre[]>("/genres");
export const readBooks = () => get<Book[]>("/books");

export const searchCatalog = (query: string) => get<Search>(`/catalog/search?q=${encodeURIComponent(query)}`);
export const addFromCatalog = (candidate: Candidate, reading: Reading) =>
  send<Book>("/books/catalog", "POST", { candidate, reading });

export const coverUrl = (book: Pick<Book, "id" | "edition_id">) =>
  `${api.base}/books/${book.id}/cover?e=${book.edition_id}`;

export const resolveBook = (id: string, candidate: Candidate) =>
  send<Book>(`/books/${id}/resolve`, "PUT", { candidate });
export const readBook = (id: string) => get<Book>(`/books/${id}`);

export interface Share {
  id: string;
  name: string;
  books: number;
  pages: number;
}

export interface Highlight {
  id: string;
  title: string;
  pages: number | null;
  days: number | null;
}

export interface YearStats {
  year: number;
  years: number[];
  books: number;
  pages: number;
  goal: number | null;
  goal_pace: number | null;
  average_rating: number | null;
  pages_per_day: number;
  months: { month: number; label: string; books: number; pages: number }[];
  days: Record<string, number>;
  genres: Share[];
  formats: Share[];
  languages: Share[];
  authors: Share[];
  ratings: Record<string, number>;
  longest: Highlight | null;
  fastest: Highlight | null;
}

export const readStats = (year?: number) => get<YearStats>(`/stats${year ? `?year=${year}` : ""}`);
export const setGoal = (year: number, books: number) => send<YearStats>(`/goals/${year}`, "PUT", { books });

export const addBook = (edition: Edition, reading: Reading) => send<Book>("/books", "POST", { edition, reading });
export const saveReading = (id: string, reading: Reading) => send<Book>(`/books/${id}`, "PUT", reading);
export const saveEdition = (id: string, edition: Edition) => send<Book>(`/books/${id}/edition`, "PUT", edition);

export const readVersion = api.readVersion;
