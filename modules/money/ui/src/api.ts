const BASE = "/api/money";

export class Unauthorised extends Error {}

export class Refused extends Error {}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: { accept: "application/json", ...(body !== undefined ? { "content-type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (response.status === 401) throw new Unauthorised("sin sesión");
  if (response.status === 422) {
    const detail = await response.json().catch(() => null);
    throw new Refused(typeof detail?.detail === "string" ? detail.detail : "No se ha podido guardar");
  }
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export type Nature = "income" | "expense";
export type Ownership = "individual" | "shared";
export type Payer = "account" | "me" | "other";
export type Status = "transfer" | "return" | "settlement" | "manual" | "auto" | "default" | "ask" | "pending";
export type Kind = "transfer" | "return" | "settlement" | "ask" | "pending" | "income" | "expense" | "mixed";

export interface Category {
  id: string;
  name: string;
  nature: Nature;
  ownership: Ownership;
  split: "fifty_fifty" | "proportional" | null;
  not_living: boolean;
  not_basic: boolean;
}

export type CategoryIn = Pick<Category, "name" | "split" | "not_living" | "not_basic">;

export interface Kpi {
  key: "networth" | "liquid" | "cash" | "emergency" | "expense" | "basic";
  label: string;
  value: number | null;
  previous: number | null;
  target: number | null;
  detail: string | null;
  carried: string[];
}

export interface Summary {
  kpis: Kpi[];
  emergency_months: number;
}

export interface AccountRef {
  key: string;
  name: string;
  institution: string;
  type: string;
  type_label: string;
  group: string;
  asset_class: string;
  liquid?: boolean;
  movements: string;
  value: string;
  shared: boolean;
  ownership: number;
  role: string | null;
}

export interface State {
  configured: boolean;
  me: string;
  other: string;
  cutoff: string | null;
  accounts: AccountRef[];
  categories: Category[];
  account_types: { value: string; label: string }[];
  health: { account: string; ok: boolean; first: string | null; last: string | null; gap: number | null }[];
  counts: Partial<Record<Status, number>>;
  unmapped: { key: string; bank: string; name: string; iban_tail: string | null }[];
  assets: { value: string; label: string }[];
  regions: { value: string; label: string }[];
  years: number[];
  rules: number;
}

export interface FundRow {
  symbol: string;
  name: string;
  value: number;
  change: number | null;
  asset: string;
  asset_name: string;
  regions: { key: string; name: string; weight: number }[];
  classified: string;
}

export interface RuleRow {
  id: string;
  origin: string | null;
  when: string;
  then: string;
  accounts: string[];
  movements: number;
}

export interface ProductDetail {
  key: string;
  name: string;
  institution: string;
  type: string;
  type_label: string;
  group: string;
  asset_class: string;
  traits: string[];
  ownership: number;
  shared: boolean;
  role: string | null;
  movements: string;
  movements_how: string;
  source: { bank: string; name: string; iban_tail: string | null } | null;
  value_mode: string;
  value_how: string;
  value: number | null;
  value_since: string | null;
  estimated: string | null;
  contributed: number | null;
  ibans: string[];
  rules: RuleRow[];
  valuations: { on: string; value: number; source: string }[];
  photo: { on: string; typed: boolean; funds: FundRow[] } | null;
}

export interface ProductChange {
  name?: string;
  type?: string;
  institution?: string;
  ownership?: number;
  shared?: boolean;
  ibans?: string[];
  value?: string;
  source?: string;
}

export interface NewProduct {
  name: string;
  type: string;
  institution: string;
  ownership: number;
  shared: boolean;
  ibans: string[];
  source?: string;
}

export interface TypedFund {
  name: string;
  value?: string;
  weight?: string;
  symbol?: string;
}

export interface Share {
  key: string;
  name: string;
  value: number;
}

export interface Composition {
  on: string;
  total: number;
  by_asset: Share[];
  by_region: Share[];
  by_fund: (Share & { products: string[] })[];
  by_product: Share[];
  unknown_asset: number;
  unknown_region: number;
  products: { key: string; name: string; value: number; on: string | null; typed?: boolean; funds: FundRow[] }[];
}

export interface FundOption {
  symbol: string;
  name: string;
  asset: string;
  classified: string;
}

export interface Part {
  amount: number;
  category: string;
  category_name: string;
  nature: Nature;
  ownership: Ownership;
  payer: Payer | null;
  basis: string;
  equity_in: string | null;
}

export interface Movement {
  id: string;
  on: string;
  value_on: string | null;
  amount: number;
  account: string;
  account_name: string;
  institution: string;
  merchant: string;
  text: string;
  counterparty: string | null;
  counterparty_iban: string | null;
  bank_category: string | null;
  source: string;
  status: Status;
  kind: Kind;
  parts: Part[];
  transfer: { account: string | null; name: string; basis: string; fact?: string | null; on?: string } | null;
  labelled: boolean;
  before_cutoff: boolean;
  entry: { id: string; payer: string } | null;
}

export interface MovementDetail extends Movement {
  label: Record<string, unknown> | null;
  same_merchant: number;
}

export interface LabelIn {
  parts?: { amount: string; category: string; payer?: Payer | null }[];
  settlement?: boolean;
  is_return?: boolean;
  transfer_with?: string;
}

export interface SharedMonth {
  month: number;
  source: "history" | "book";
  total: number;
  mine: number;
  balance_me: number;
  paid: { account: number; me: number; other: number };
  deposits: { me: number; other: number };
  by_category: { name: string; amount: number; split: string | null }[];
}

export interface SharedEntry {
  id: string;
  fact: string;
  on: string;
  amount: number;
  description: string;
  payer: "me" | "other";
  category: string;
  category_name: string;
}

export interface Income {
  person: "me" | "other";
  from: string;
  to: string;
  salary: number;
  extra: number;
}

export type Person = "me" | "other";

export interface Space {
  id: string;
  name: string;
}

export type SharedRole = "alone" | "keeper" | "member";

export interface Shared {
  year: number;
  role: SharedRole;
  kept_at: string | null;
  has_keeper: boolean;
  common_categories: { name: string; split: string }[];
  me: string;
  other: string;
  settled: boolean;
  ratio_me: number;
  balance_me: number;
  total: number;
  by_category: { name: string; amount: number }[];
  average: { months: number; total: number | null; by_category: Record<string, number> };
  months: SharedMonth[];
  entries: SharedEntry[];
  incomes: Income[];
  income_totals: Record<Person, number>;
  space_id: string | null;
}

export interface Period {
  from: string;
  to: string;
}

export interface WorthPoint {
  on: string;
  label: string;
  total: number;
  contributed: number;
  by_group: Record<string, number>;
}

export interface WorthRow {
  key: string;
  name: string;
  institution: string;
  group: string;
  value: number;
  previous: number | null;
  since: string | null;
  estimated: string | null;
  carried: boolean;
  ownership: number;
}

export interface Worth {
  on: string;
  before: string;
  widened: boolean;
  groups: string[];
  points: WorthPoint[];
  rows: WorthRow[];
  total: number;
  previous: number | null;
  contributed: number | null;
}

export interface Product {
  key: string;
  name: string;
  institution: string;
  group: string;
  value: number;
  value_before: number;
  capital: number;
  capital_other: number | null;
  gain: number;
  simple: number | null;
  xirr: number | null;
  contributed_in_period: number;
  period_gain: number;
  period_return: number | null;
  since: string | null;
  estimated: string | null;
  carried: boolean;
  first: string | null;
  series: { label: string; value: number | null; capital: number }[];
}

export interface Investments {
  on: string;
  widened: boolean;
  rows: Product[];
  total: {
    value: number;
    value_before: number;
    capital: number;
    contributed_in_period: number;
    gain: number;
    simple: number | null;
    xirr: number | null;
    period_gain: number;
    period_return: number | null;
  };
  contributions: { labels: string[]; series: { key: string; name: string; values: number[] }[] };
}

export interface SpendingRow {
  key: string;
  name: string;
  ownership: Ownership;
  total: number;
  previous: number;
  average: number | null;
  usual: number;
  share: number;
  basic: boolean;
}

export interface Spending {
  on: string;
  previous_period: Period;
  ongoing: boolean;
  total: number;
  previous: number;
  months: number;
  closed_months: number;
  monthly: number | null;
  usual_months: number;
  individual_months: { now: number; previous: number; of: number };
  groups: { basic: number; not_basic: number; not_living: number };
  rows: SpendingRow[];
  series: { widened: boolean; labels: string[]; series: { key: string; name: string; values: number[] }[] };
}

export interface CategoryDetail {
  name: string;
  ownership: Ownership;
  history: number;
  merchants: { name: string; total: number; count: number }[];
  movements: { id: string; on: string; merchant: string; amount: number; account: string }[];
}

export type FlowKind = "income" | "you" | "member" | "common" | "account" | "expense" | "saving" | "deficit";

export interface Flow {
  segments: { from: string; to: string; kind: "month" | "cycle"; open: boolean }[];
  nodes: { id: string; name: string; column: number; kind: FlowKind }[];
  links: { source: string; target: string; value: number }[];
  totals: FlowTotals;
  previous: FlowTotals | null;
  payroll: string | null;
  payroll_moved: { in: number; out: number } | null;
  unlogged: number;
}

export interface FlowTotals {
  income: number;
  member: number;
  spent: number;
  common: number;
  invested: number;
  left: number;
  rate: number | null;
}

export interface AnalysisQuery {
  from: string;
  to: string;
  home?: boolean;
  whole?: boolean;
  cycle?: boolean;
  rent?: boolean;
  scope?: "all" | "individual" | "shared";
  kind?: "all" | "basic" | "other";
  name?: string;
  ownership?: Ownership;
  group?: string[];
  account?: string[];
}

function query(q: AnalysisQuery): string {
  const p = new URLSearchParams();
  for (const [key, value] of Object.entries(q)) {
    if (Array.isArray(value)) for (const one of value) p.append(key, one);
    else if (value !== undefined) p.set(key, String(value));
  }
  return `?${p.toString()}`;
}

const q = (id: string) => `?id=${encodeURIComponent(id)}`;

export const api = {
  state: () => call<State>("GET", "/state"),
  movements: (from: string, to: string) =>
    call<{ movements: Movement[] }>("GET", `/movements?from=${from}&to=${to}`).then((r) => r.movements),
  movement: (id: string) => call<MovementDetail>("GET", `/movement${q(id)}`),
  label: (id: string, label: LabelIn) => call<Movement>("PUT", `/label${q(id)}`, label),
  unlabel: (id: string) => call<Movement>("DELETE", `/label${q(id)}`),
  merchantRule: (id: string, category: string) =>
    call<{ merchant: string; movements: number }>("POST", `/merchant-rule${q(id)}`, { category }),
  shared: (year: number) => call<Shared>("GET", `/shared?year=${year}`),
  addEntry: (entry: { payer: "me" | "other"; on: string; amount: string; description: string; category: string }) =>
    call<{ id: string }>("POST", "/shared/entries", entry),
  removeEntry: (id: string) => call<void>("DELETE", `/shared/entries/${id}`),
  settle: (year: number, settled: boolean) => call<unknown>("PUT", `/shared/years/${year}`, { settled }),
  incomes: (year: number, incomes: Income[]) => call<unknown>("PUT", `/shared/incomes/${year}`, { incomes }),
  sharedSpace: (spaceId: string | null) => call<unknown>("PUT", "/shared/space", { space_id: spaceId }),
  spaces: async (): Promise<Space[]> => {
    const response = await fetch("/api/kernel/spaces", { headers: { accept: "application/json" } });
    if (response.status === 401) throw new Unauthorised("sin sesión");
    if (!response.ok) throw new Error(`/api/kernel/spaces: ${response.status}`);
    return (await response.json()) as Space[];
  },
  summary: () => call<Summary>("GET", "/summary"),
  settings: (emergency_months: number, emergency_account: string | null) =>
    call<unknown>("PUT", "/settings", { emergency_months, emergency_account }),
  account: (key: string, account: { name: string; type: string; ownership: number; shared: boolean }) =>
    call<unknown>("PUT", `/accounts/${encodeURIComponent(key)}`, account),
  saveCategory: (id: string, category: CategoryIn) => call<unknown>("PUT", `/categories/${id}`, category),
  addCategory: (category: CategoryIn & Pick<Category, "nature" | "ownership">) =>
    call<{ id: string }>("POST", "/categories", category),
  product: (key: string) => call<ProductDetail>("GET", `/products/${encodeURIComponent(key)}`),
  addProduct: (product: NewProduct) => call<ProductDetail>("POST", "/accounts", product),
  changeProduct: (key: string, change: ProductChange) =>
    call<ProductDetail>("PATCH", `/accounts/${encodeURIComponent(key)}`, change),
  setComposition: (key: string, on: string, funds: TypedFund[], total?: string) =>
    call<ProductDetail>("PUT", `/accounts/${encodeURIComponent(key)}/composition`, { on, funds, total }),
  removeComposition: (key: string, on: string) =>
    call<ProductDetail>("DELETE", `/accounts/${encodeURIComponent(key)}/composition?on=${on}`),
  setValue: (key: string, on: string, value: string) =>
    call<ProductDetail>("PUT", `/accounts/${encodeURIComponent(key)}/value`, { on, value }),
  funds: () => call<FundOption[]>("GET", "/funds"),
  classifyFund: (symbol: string, asset: string, regions: Record<string, number>) =>
    call<unknown>("PUT", `/funds/${encodeURIComponent(symbol)}`, { asset, regions }),
  unclassifyFund: (symbol: string) => call<void>("DELETE", `/funds/${encodeURIComponent(symbol)}`),
  rules: () => call<RuleRow[]>("GET", "/rules"),
  removeRule: (id: string, keep: boolean) => call<{ kept: number }>("DELETE", `/rules/${id}?keep=${keep}`),
  composition: (q: AnalysisQuery) => call<Composition>("GET", `/analysis/composition${query(q)}`),
  importBundle: (bundle: unknown) => call<Record<string, number>>("POST", "/import", bundle),
  exportBundle: () => call<unknown>("GET", "/export"),
  worth: (q: AnalysisQuery) => call<Worth>("GET", `/analysis/worth${query(q)}`),
  investments: (q: AnalysisQuery) => call<Investments>("GET", `/analysis/investments${query(q)}`),
  spending: (q: AnalysisQuery) => call<Spending>("GET", `/analysis/spending${query(q)}`),
  category: (q: AnalysisQuery) => call<CategoryDetail>("GET", `/analysis/spending/category${query(q)}`),
  flow: (q: AnalysisQuery) => call<Flow>("GET", `/analysis/flow${query(q)}`),
};
