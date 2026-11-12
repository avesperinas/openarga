import { capital, isoDay, monthName } from "./format";

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

export const VIEWS: { value: View; label: string; slug: string }[] = [
  { value: "worth", label: "Patrimonio", slug: "patrimonio" },
  { value: "invest", label: "Inversión", slug: "inversion" },
  { value: "spending", label: "Gasto", slug: "gasto" },
  { value: "flow", label: "Flujo", slug: "flujo" },
];

export const PERIODS: { value: PeriodKind; label: string; slug: string }[] = [
  { value: "month", label: "Mes", slug: "mes" },
  { value: "quarter", label: "Trimestre", slug: "trimestre" },
  { value: "year", label: "Año", slug: "ano" },
  { value: "last12", label: "12 meses", slug: "12-meses" },
  { value: "range", label: "Rango", slug: "rango" },
  { value: "all", label: "Todo", slug: "todo" },
];

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

const QUARTERS = ["1.er", "2.º", "3.er", "4.º"];

export function periodTitle(s: AnalysisState, first: number, today = new Date()): string {
  const { year, month } = parseMonth(s.at);
  const short = (y: number, m: number) => `${capital(monthName(m)).slice(0, 3)} ${y}`;
  switch (s.kind) {
    case "month":
      return `${capital(monthName(month))} ${year}`;
    case "quarter":
      return `${QUARTERS[Math.floor((month - 1) / 3)]} trimestre ${year}`;
    case "year":
      return String(year);
    case "last12": {
      const begin = new Date(year, month - 12, 1);
      return `${short(begin.getFullYear(), begin.getMonth() + 1)} – ${short(year, month)}`;
    }
    case "range": {
      const { from, to } = bounds(s, first, today);
      return `${from.split("-").reverse().join("/")} – ${to.split("-").reverse().join("/")}`;
    }
    case "all":
      return `Desde ${first}`;
  }
}

export function previousLabel(kind: PeriodKind): string {
  switch (kind) {
    case "month":
      return "el mes anterior";
    case "quarter":
      return "el trimestre anterior";
    case "year":
      return "el año anterior";
    case "last12":
      return "los 12 meses anteriores";
    default:
      return "el periodo anterior";
  }
}

const VIEW_SLUG = new Map(VIEWS.map((v) => [v.slug, v.value]));
const PERIOD_SLUG = new Map(PERIODS.map((p) => [p.slug, p.value]));

export function toSearch(s: AnalysisState, today = new Date()): string {
  const d = defaults(today);
  const p = new URLSearchParams();
  if (s.view !== d.view) p.set("vista", VIEWS.find((v) => v.value === s.view)?.slug ?? s.view);
  if (s.kind !== d.kind) p.set("periodo", PERIODS.find((one) => one.value === s.kind)?.slug ?? s.kind);
  if (s.kind === "range") {
    p.set("desde", s.from);
    p.set("hasta", s.to);
  } else if (s.kind !== "all" && s.at !== d.at) p.set("mes", s.at);
  if (s.home) p.set("vivienda", "si");
  if (s.whole) p.set("comun", "todo");
  if (!s.cycle) p.set("ciclo", "mes");
  if (s.percent) p.set("en", "porcentaje");
  if (!s.rent) p.set("alquiler", "gasto");
  if (s.scope !== "all") p.set("gasto", s.scope === "individual" ? "individual" : "comun");
  if (s.basic !== "all") p.set("tipo", s.basic === "basic" ? "basico" : "no-basico");
  for (const g of s.groups) p.append("producto", g);
  for (const a of s.accounts) p.append("cuenta", a);
  const text = p.toString();
  return text ? `?${text}` : "";
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

export function fromSearch(search: string, today = new Date()): AnalysisState {
  const p = new URLSearchParams(search);
  const d = defaults(today);
  const from = p.get("desde") ?? "";
  const to = p.get("hasta") ?? "";
  const at = p.get("mes") ?? "";
  const gasto = p.get("gasto");
  const tipo = p.get("tipo");
  return {
    view: VIEW_SLUG.get(p.get("vista") ?? "") ?? d.view,
    kind: PERIOD_SLUG.get(p.get("periodo") ?? "") ?? d.kind,
    at: MONTH.test(at) ? at : d.at,
    from: DAY.test(from) ? from : d.from,
    to: DAY.test(to) ? to : d.to,
    home: p.get("vivienda") === "si",
    whole: p.get("comun") === "todo",
    cycle: p.get("ciclo") !== "mes",
    percent: p.get("en") === "porcentaje",
    rent: p.get("alquiler") !== "gasto",
    scope: gasto === "individual" ? "individual" : gasto === "comun" ? "shared" : "all",
    basic: tipo === "basico" ? "basic" : tipo === "no-basico" ? "other" : "all",
    groups: p.getAll("producto").filter(Boolean),
    accounts: p.getAll("cuenta").filter(Boolean),
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
  const name = monthName(month).slice(0, 3);
  return withYear ? `${name} ${String(year).slice(2)}` : name;
}

export function crossesYears(labels: string[]): boolean {
  return new Set(labels.map((l) => l.slice(0, 4))).size > 1;
}

export function change(now: number, before: number | null | undefined): number | null {
  if (before === null || before === undefined || before === 0) return null;
  return (now - before) / Math.abs(before);
}
