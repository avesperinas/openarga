import type { Movement, Status } from "./api";
import { capital, isoDay, monthName } from "./format";

export type Period =
  | { kind: "month"; year: number; month: number }
  | { kind: "year"; year: number }
  | { kind: "range"; from: string; to: string };

export function thisMonth(today = new Date()): Period {
  return { kind: "month", year: today.getFullYear(), month: today.getMonth() + 1 };
}

export function bounds(p: Period): { from: string; to: string } {
  if (p.kind === "month") {
    return { from: isoDay(new Date(p.year, p.month - 1, 1)), to: isoDay(new Date(p.year, p.month, 0)) };
  }
  if (p.kind === "year") return { from: `${p.year}-01-01`, to: `${p.year}-12-31` };
  return { from: p.from, to: p.to };
}

export function step(p: Period, by: -1 | 1): Period {
  if (p.kind === "month") {
    const d = new Date(p.year, p.month - 1 + by, 1);
    return { kind: "month", year: d.getFullYear(), month: d.getMonth() + 1 };
  }
  if (p.kind === "year") return { kind: "year", year: p.year + by };
  return p;
}

export function periodTitle(p: Period): string {
  if (p.kind === "month") return `${capital(monthName(p.month))} ${p.year}`;
  if (p.kind === "year") return String(p.year);
  return `${p.from.split("-").reverse().join("/")} – ${p.to.split("-").reverse().join("/")}`;
}

export type What = "income" | "expense" | "transfer" | "other";

export interface Filters {
  text: string;
  categories: string[];
  accounts: string[];
  accountTypes: string[];
  institutions: string[];
  what: What[];
  ownership: ("individual" | "shared")[];
  statuses: Status[];
  min: number | null;
  max: number | null;
}

export const NO_FILTERS: Filters = {
  text: "",
  categories: [],
  accounts: [],
  accountTypes: [],
  institutions: [],
  what: [],
  ownership: [],
  statuses: [],
  min: null,
  max: null,
};

export function activeCount(f: Filters): number {
  return (
    f.categories.length +
    f.accounts.length +
    f.accountTypes.length +
    f.institutions.length +
    f.what.length +
    f.ownership.length +
    f.statuses.length +
    (f.min !== null ? 1 : 0) +
    (f.max !== null ? 1 : 0)
  );
}

function whatOf(m: Movement): What {
  if (m.kind === "transfer") return "transfer";
  if (m.kind === "income") return "income";
  if (m.kind === "expense" || m.kind === "mixed") return m.amount < 0 ? "expense" : m.parts.some((p) => p.nature === "income") ? "income" : "expense";
  return "other";
}

function fold(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function matches(m: Movement, f: Filters, typeOf: (account: string) => string | undefined = () => undefined): boolean {
  if (f.text) {
    const hay = fold([m.merchant, m.text, m.counterparty ?? "", m.account_name, ...m.parts.map((p) => p.category_name)].join(" "));
    if (!fold(f.text).split(/\s+/).every((word) => hay.includes(word))) return false;
  }
  if (f.categories.length && !m.parts.some((p) => f.categories.includes(p.category))) return false;
  if (f.accounts.length && !f.accounts.includes(m.account)) return false;
  if (f.institutions.length && !f.institutions.includes(m.institution)) return false;
  if (f.accountTypes.length && !f.accountTypes.includes(typeOf(m.account) ?? "")) return false;
  if (f.what.length && !f.what.includes(whatOf(m))) return false;
  if (f.ownership.length && !m.parts.some((p) => f.ownership.includes(p.ownership))) return false;
  if (f.statuses.length && !f.statuses.includes(m.status)) return false;
  const size = Math.abs(m.amount);
  if (f.min !== null && size < f.min) return false;
  if (f.max !== null && size > f.max) return false;
  return true;
}

export interface Totals {
  income: number;
  expense: number;
  count: number;
}

export function totals(rows: Movement[], f: Filters = NO_FILTERS): Totals {
  let income = 0;
  let expense = 0;
  for (const m of rows) {
    for (const p of m.parts) {
      if (f.categories.length && !f.categories.includes(p.category)) continue;
      if (p.nature === "income") income += p.amount;
      else expense -= p.amount;
    }
  }
  return { income: round(income), expense: round(expense), count: rows.length };
}

function round(v: number): number {
  return Math.round(v * 100) / 100;
}

export interface Day {
  on: string;
  rows: Movement[];
  net: number;
}

export function byDay(rows: Movement[]): Day[] {
  const days: Day[] = [];
  for (const m of rows) {
    const last = days[days.length - 1];
    if (last && last.on === m.on) last.rows.push(m);
    else days.push({ on: m.on, rows: [m], net: 0 });
  }
  for (const d of days) {
    d.net = round(d.rows.filter((m) => m.kind !== "transfer").reduce((sum, m) => sum + m.amount, 0));
  }
  return days;
}

export function fromLink(search: string): { period: Period; filters: Filters } | null {
  const p = new URLSearchParams(search);
  if (p.get("status") === "pending") {
    return { period: { kind: "year", year: new Date().getFullYear() }, filters: { ...NO_FILTERS, statuses: ["ask", "pending"] } };
  }
  const from = p.get("desde") ?? "";
  const to = p.get("hasta") ?? "";
  const day = /^\d{4}-\d{2}-\d{2}$/;
  if (!day.test(from) || !day.test(to) || from > to) return null;
  const category = p.get("categoria");
  const filters = category ? { ...NO_FILTERS, categories: [category] } : NO_FILTERS;
  const [fy, fm, fd] = from.split("-").map(Number);
  const [ty, tm, td] = to.split("-").map(Number);
  const lastDay = new Date(ty ?? 2000, tm ?? 1, 0).getDate();
  if (fy === ty && fm === tm && fd === 1 && td === lastDay) {
    return { period: { kind: "month", year: fy ?? 2000, month: fm ?? 1 }, filters };
  }
  const end = new Date(ty ?? 2000, (tm ?? 1) - 1, td ?? 1);
  const yearBefore = new Date(end.getFullYear() - 1, end.getMonth(), end.getDate() + 1);
  const start = new Date(fy ?? 2000, (fm ?? 1) - 1, fd ?? 1);
  return { period: { kind: "range", from: isoDay(start < yearBefore ? yearBefore : start), to }, filters };
}
