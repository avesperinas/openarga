import { Unauthorised, createApi, signIn } from "@openarga/app";
import type { InletSetting, InletValues, SourceAsk, SourceSearchResult } from "@openarga/ui";

const client = createApi("hub");
const { get } = client;

export { Unauthorised, signIn };

export interface SecretSpec {
  key: string;
  label: string;
  help: string;
  multiline: boolean;
}

export interface SettingSpec {
  key: string;
  label: string;
  help: string;
  default: string;
}

export interface Provider {
  id: string;
  name: string;
  description: string;
  capabilities: ("sync" | "action" | "lookup" | "push")[];
  available: boolean;
  single: boolean;
  lives_in: string | null;
  created_in?: string | null;
  authorizes?: boolean;
  daily_budget?: number | null;
  by_mail?: boolean;
  settings?: SettingSpec[];
  secrets: SecretSpec[];
  emits?: string[];
  offer?: Offer | null;
  inlets?: Inlet[];
}

export interface Offer {
  provider: string;
  title: string;
  subtitle: string;
  tone: number;
  asks: SourceAsk[];
  many: boolean;
  name: string;
  group: string;
}

export interface Inlet {
  key: string;
  app: string;
  title: string;
  settings: InletSetting[];
}

export interface Category {
  id: string;
  name: string;
  providers: Provider[];
}

export type ConnectionState = "pending" | "paused" | "expired" | "expiring" | "failing" | "active";

export interface Connection {
  id: string;
  provider: string;
  label: string;
  category: string;
  state: ConnectionState;
  brief: string;
  tone: "positive" | "warning" | "negative" | "neutral";
  reason: string | null;
  last_ok_at: string | null;
  last_run_at?: string | null;
  emitted_week: number;
}

export type Outcome = "running" | "ok" | "error" | "skipped" | "rate_limited";

export interface Run {
  operation: string;
  started_at: string;
  finished_at: string | null;
  outcome: Outcome;
  emitted: number;
  detail: string | null;
}

export interface SecretStatus extends SecretSpec {
  configured: boolean;
  hint: string | null;
}

export interface Budget {
  limit: number;
  used: number;
  remaining: number;
}

export interface ConnectionDetail extends Connection {
  provider_name: string;
  paused: boolean;
  emits: string[];
  secrets: SecretStatus[];
  runs: Run[];
  consent_expires_at?: string | null;
  authorizes?: boolean;
  push?: boolean;
  accounts?: { name: string | null; iban_tail: string | null; kind: string | null }[];
  budget?: Budget | null;
  settings?: Record<string, string | number | string[] | null>;
  extractors?: { id: string; entity: string }[];
  rules?: MailRule[];
  plugs?: Record<string, InletValues>;
  inlets?: Inlet[];
  relay?: boolean;
}

export type RuleFact = "balance" | "deposit" | "withdrawal";

export interface MailRule {
  id?: string;
  entity: string;
  product: string;
  sender: string;
  subject: string;
  anchor: string;
  fact: RuleFact;
}

export interface RuleTrial {
  on: string | null;
  subject: string;
  amount: string | null;
  problem: string | null;
}

export class Refused extends Error {}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  try {
    return await client.send<T>(path, method, body);
  } catch (error) {
    if (error instanceof Unauthorised || error instanceof TypeError || !(error instanceof Error)) throw error;
    throw new Refused(error.message);
  }
}

export const readCatalogue = () => get<Category[]>("/catalogue");

export interface AppEntry {
  module: string;
  name: string;
  view: string | null;
  inlets: { key: string; title: string; providers: string[] }[];
  services: { provider: string; capabilities: string[] }[];
}

export interface AppSources {
  apps: AppEntry[];
  others: string[];
}

export const readApps = () => get<AppSources>("/apps");
export const readConnections = () => get<Connection[]>("/connections");
export const readConnection = (id: string) => get<ConnectionDetail>(`/connections/${id}`);
export const createConnection = (
  provider: string,
  label: string,
  secrets: Record<string, string>,
  settings: Record<string, unknown> = {},
  plugs: Record<string, InletValues> = {},
) =>
  send<ConnectionDetail & { ingest_token?: string; authorization_url?: string }>("/connections", "POST", { provider, label, secrets, settings, plugs });
export const searchOffer = (provider: string, ask: string, query?: string, parent?: string) => {
  const params = new URLSearchParams({ ask });
  if (query) params.set("query", query);
  if (parent) params.set("parent", parent);
  return get<SourceSearchResult>(`/offers/${encodeURIComponent(provider)}/search?${params.toString()}`);
};
export const renewToken = (id: string) =>
  send<ConnectionDetail & { ingest_token: string }>(`/connections/${id}/token`, "POST");
export const changeCredential = (id: string, key: string, value: string) =>
  send<ConnectionDetail>(`/connections/${id}/credentials/${key}`, "PUT", { value });
export const pauseConnection = (id: string) => send<ConnectionDetail>(`/connections/${id}/pause`, "POST");
export const resumeConnection = (id: string) => send<ConnectionDetail>(`/connections/${id}/resume`, "POST");
export const removeConnection = (id: string) => send<void>(`/connections/${id}`, "DELETE");
export const setRelay = (id: string, relay: boolean) =>
  send<ConnectionDetail>(`/connections/${id}/relay`, "PUT", { relay });
export const renameConnection = (id: string, label: string) =>
  send<ConnectionDetail>(`/connections/${id}/label`, "PUT", { label });

export const readBankApp = () => get<{ app: boolean; redirect_url: string }>("/providers/enable_banking");
export const listBanks = (secrets: Record<string, string>, country = "ES") =>
  send<string[]>("/providers/enable_banking/banks", "POST", { country, secrets });
export const connectBank = (bank: string, secrets: Record<string, string>, country = "ES") =>
  send<ConnectionDetail & { authorization_url: string }>("/connections", "POST", {
    provider: "enable_banking",
    bank,
    country,
    label: bank,
    secrets,
  }).then((created) => created.authorization_url);
export const reauthorize = (id: string) =>
  send<{ authorization_url: string }>(`/connections/${id}/reauthorize`, "POST").then((r) => r.authorization_url);
export const saveRules = (id: string, rules: MailRule[]) =>
  send<ConnectionDetail>(`/connections/${id}/rules`, "PUT", { rules });
export const tryRule = (id: string, rule: MailRule) =>
  send<{ results: RuleTrial[] }>(`/connections/${id}/rules/try`, "POST", rule).then((r) => r.results);
export const syncNow = (id: string) =>
  send<ConnectionDetail & { outcome: string; outcome_detail: string | null }>(`/connections/${id}/sync`, "POST");

export const readVersion = client.readVersion;

export interface StatementRead {
  file: string;
  entity?: string;
  accounts?: string[];
  balances?: number;
  movements?: number;
  new?: number;
  repeated?: number;
  skipped?: string[];
  problem?: string;
}

export const uploadStatements = (files: { name: string; content: string }[]) =>
  send<{ files: StatementRead[] }>("/statements", "POST", { files });

export interface ClaudeRunApp {
  id: string;
  name: string;
  granted: { app: string; connection: string; label: string; since: string } | null;
}

export const readClaudeRun = () => get<{ configured: boolean; apps: ClaudeRunApp[] }>("/claude-run");
export const revokeClaudeRun = (app: string) => send<void>(`/claude-run/${app}`, "DELETE");
export const authorizeClaudeRun = (connection: string, app: string) =>
  `/api/hub/claude-run/authorize?${new URLSearchParams({ connection, app }).toString()}`;
