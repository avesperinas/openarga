import { dates } from "@openarga/ui";

import { capital, isoDay, monthTitle, parseDay, say } from "./format";

export type View = "worth" | "invest" | "spending" | "flow";
export type PeriodKind = "month" | "quarter" | "year" | "last12" | "range" | "all";
export type Scope = "all" | "individual" | "shared";
export type Basic = "all" | "basic" | "other";

export interface AnalysisState {
  view: View;
  kind: PeriodKind;
  at: string;
  from: string;
  to: string;
  home: boolean;
  whole: boolean;
  cycle: boolean;
  percent: boolean;
  rent: boolean;
  scope: Scope;
  basic: Basic;
  groups: string[];
  accounts: string[];
}

export const VIEWS: View[] = ["worth", "invest", "spending", "flow"];

export const PERIODS: PeriodKind[] = ["month", "quarter", "year", "last12", "range", "all"];

export const viewName = (view: View): string => say(`view.${view}`);
export const periodName = (kind: PeriodKind): string => say(`period.${kind}`);

function monthKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function parseMonth(key: string): { year: number; month: number } {
  const [y, m] = key.split("-").map(Number);
  return { year: y ?? 2000, month: m ?? 1 };
}

export function defaults(today = new Date()): AnalysisState {
  const at = monthKey(today);
  return {
    view: "worth",
    kind: "month",
    at,
    from: isoDay(new Date(today.getFullYear(), today.getMonth(), 1)),
    to: isoDay(today),
    home: false,
    whole: false,
    cycle: true,
    percent: false,
    rent: true,
    scope: "all",
    basic: "all",
    groups: [],
    accounts: [],
  };
}

export function bounds(s: AnalysisState, first: number, today = new Date()): { from: string; to: string } {
  const { year, month } = parseMonth(s.at);
  const last = (y: number, m: number) => isoDay(new Date(y, m, 0));
  const start = (y: number, m: number) => isoDay(new Date(y, m - 1, 1));
  switch (s.kind) {
    case "month":
      return { from: start(year, month), to: last(year, month) };
    case "quarter": {
      const q = Math.floor((month - 1) / 3) * 3 + 1;
      return { from: start(year, q), to: last(year, q + 2) };
    }
    case "year":
      return { from: `${year}-01-01`, to: `${year}-12-31` };
    case "last12": {
      const begin = new Date(year, month - 12, 1);
      return { from: isoDay(begin), to: last(year, month) };
    }
    case "range":
      return s.from <= s.to ? { from: s.from, to: s.to } : { from: s.to, to: s.from };
    case "all":
      return { from: `${first}-01-01`, to: isoDay(today) };
  }
}

export function step(s: AnalysisState, by: -1 | 1): AnalysisState {
  const { year, month } = parseMonth(s.at);
  const size = s.kind === "quarter" ? 3 : s.kind === "year" ? 12 : 1;
  if (s.kind === "range" || s.kind === "all") return s;
  return { ...s, at: monthKey(new Date(year, month - 1 + by * size, 1)) };
}

export function atEnd(s: AnalysisState, today = new Date()): boolean {
  if (s.kind === "range" || s.kind === "all") return true;
  const next = bounds(step(s, 1), today.getFullYear(), today);
  return next.from > isoDay(today);
}

export function periodTitle(s: AnalysisState, first: number, today = new Date()): string {
  const { year, month } = parseMonth(s.at);
  const short = (y: number, m: number) => capital(dates({ month: "short", year: "numeric" }).format(new Date(y, m - 1, 1))).replace(".", "");
  switch (s.kind) {
    case "month":
      return monthTitle(year, month);
    case "quarter":
      return say("period.quarter_title", { quarter: Math.floor((month - 1) / 3) + 1, year });
    case "year":
      return String(year);
    case "last12": {
      const begin = new Date(year, month - 12, 1);
      return `${short(begin.getFullYear(), begin.getMonth() + 1)} – ${short(year, month)}`;
    }
    case "range": {
      const { from, to } = bounds(s, first, today);
      return `${dates().format(parseDay(from))} – ${dates().format(parseDay(to))}`;
    }
    case "all":
      return say("period.since", { year: first });
  }
}

export function previousLabel(kind: PeriodKind): string {
  switch (kind) {
    case "month":
    case "quarter":
    case "year":
    case "last12":
      return say(`previous.${kind}`);
    default:
      return say("previous.other");
  }
}

const isView = (value: string | null): value is View => VIEWS.includes(value as View);
const isPeriod = (value: string | null): value is PeriodKind => PERIODS.includes(value as PeriodKind);

export function toSearch(s: AnalysisState, today = new Date()): string {
  const d = defaults(today);
  const p = new URLSearchParams();
  if (s.view !== d.view) p.set("view", s.view);
  if (s.kind !== d.kind) p.set("period", s.kind);
  if (s.kind === "range") {
    p.set("from", s.from);
    p.set("to", s.to);
  } else if (s.kind !== "all" && s.at !== d.at) p.set("month", s.at);
  if (s.home) p.set("home", "yes");
  if (s.whole) p.set("shared", "whole");
  if (!s.cycle) p.set("cycle", "month");
  if (s.percent) p.set("as", "percent");
  if (!s.rent) p.set("rent", "expense");
  if (s.scope !== "all") p.set("spending", s.scope);
  if (s.basic !== "all") p.set("kind", s.basic);
  for (const g of s.groups) p.append("product", g);
  for (const a of s.accounts) p.append("account", a);
  const text = p.toString();
  return text ? `?${text}` : "";
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

export function fromSearch(search: string, today = new Date()): AnalysisState {
  const p = new URLSearchParams(search);
  const d = defaults(today);
  const from = p.get("from") ?? "";
  const to = p.get("to") ?? "";
  const at = p.get("month") ?? "";
  const spending = p.get("spending");
  const kind = p.get("kind");
  const view = p.get("view");
  const period = p.get("period");
  return {
    view: isView(view) ? view : d.view,
    kind: isPeriod(period) ? period : d.kind,
    at: MONTH.test(at) ? at : d.at,
    from: DAY.test(from) ? from : d.from,
    to: DAY.test(to) ? to : d.to,
    home: p.get("home") === "yes",
    whole: p.get("shared") === "whole",
    cycle: p.get("cycle") !== "month",
    percent: p.get("as") === "percent",
    rent: p.get("rent") !== "expense",
    scope: spending === "individual" || spending === "shared" ? spending : "all",
    basic: kind === "basic" || kind === "other" ? kind : "all",
    groups: p.getAll("product").filter(Boolean),
    accounts: p.getAll("account").filter(Boolean),
  };
}

export function pickable(
  accounts: { key: string; name: string; group: string; asset_class: string }[],
  view: View,
  home: boolean,
  groups: string[],
): { groups: string[]; accounts: { value: string; label: string }[] } {
  const inView = accounts.filter(
    (a) =>
      (home || a.asset_class !== "real_estate") &&
      (view !== "invest" || a.asset_class === "investment" || a.asset_class === "real_estate"),
  );
  return {
    groups: [...new Set(inView.map((a) => a.group))],
    accounts: inView.filter((a) => !groups.length || groups.includes(a.group)).map((a) => ({ value: a.key, label: a.name })),
  };
}

export function axisMonth(label: string, withYear: boolean): string {
  const { year, month } = parseMonth(label);
  const name = dates({ month: "short", timeZone: "UTC" }).format(new Date(Date.UTC(2000, month - 1, 1))).replace(".", "");
  return withYear ? `${name} ${String(year).slice(2)}` : name;
}

export function crossesYears(labels: string[]): boolean {
  return new Set(labels.map((l) => l.slice(0, 4))).size > 1;
}

export function change(now: number, before: number | null | undefined): number | null {
  if (before === null || before === undefined || before === 0) return null;
  return (now - before) / Math.abs(before);
}
