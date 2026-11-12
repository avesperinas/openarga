import type { WidgetSize } from "@openarga/ui";
import { headers } from "next/headers";

import { AREA_APPS, type AreaKey, type Contributor, type PanelContribution } from "./panels";

const SUBJECT = "x-arga-subject";
const USER = "x-arga-user";
const SPACES = "x-arga-spaces";

export type Breakpoint = "mobile" | "tablet" | "desktop";
export type Device = "mobile" | "desktop";
export type { WidgetSize };

export interface DeskItem {
  instance_id: string;
  source: string;
  widget: string;
  size: WidgetSize;
  option?: string | null;
}

export interface DeskPage {
  id: string;
  items: DeskItem[];
}

export type Cell = [number, number];

export type Placements = Partial<Record<Breakpoint, Record<string, Record<string, Cell>>>>;

export interface DesktopLayout {
  pages: DeskPage[];
  placements: Placements;
  updated_at: string | null;
  default: boolean;
}

export interface LayoutItem extends DeskItem {
  x: number;
  y: number;
}

export interface LayoutPage {
  id: string;
  items: LayoutItem[];
}

export interface Layout {
  pages: LayoutPage[];
  updated_at: string | null;
  default: boolean;
}

export type WidgetKind =
  | "kpi"
  | "kpi-delta"
  | "chart"
  | "bars"
  | "heatmap"
  | "progress"
  | "ring"
  | "streak"
  | "stats"
  | "list"
  | "calendar"
  | "upnext"
  | "shortcuts"
  | "agenda"
  | "week"
  | "tasks";

export interface CatalogueEntry {
  source: string;
  id: string;
  title: string;
  hue: number;
  kind: WidgetKind;
  shape: "number" | "list";
  sizes: WidgetSize[];
  endpoint: string;
  refresh: number;
  link?: string | null;
  option?: { label: string; endpoint: string } | null;
}

export interface WidgetChoice {
  value: string;
  label: string;
}

export { envelopeKey, widgetUrl } from "./envelope";

export interface EnvelopeBody {
  value?: string | number;
  unit?: string;
  detail?: string;
  icon?: string;
  icon_hue?: number;
  previous?: number;
  since?: string;
  good_when?: "up" | "down" | "neutral";
  series?: number[];
  labels?: string[];
  highlight?: number;
  values?: number[];
  columns?: number;
  target?: number;
  label?: string;
  expected?: number;
  show?: "value" | "percent";
  current?: number;
  best?: number;
  days?: boolean[];
  stats?: { label: string; value: number | string; unit?: string }[];
  rows?: { label: string; value: string; tone?: "positive" | "warning" | "negative" | "neutral" }[];
  marked?: number[];
  today?: number;
  entries?: {
    start: string;
    end?: string;
    all_day?: boolean;
    title: string;
    detail?: string;
    tone?: number;
  }[];
  tasks?: {
    id: string;
    title: string;
    due?: string;
    overdue?: boolean;
    done?: boolean;
    detail?: string;
    hue?: number;
  }[];
  count?: number;
  checkable?: boolean;
  events?: { at: string; title: string; detail?: string }[];
  actions?: { label: string; href: string; icon?: string }[];
}

export interface Envelope {
  state: "ready" | "empty" | "error" | "disconnected";
  updated_at: string;
  uncertainty?: { summary: string; candidates?: { entity_id: string; label: string }[] };
  body: EnvelopeBody;
}

const base = process.env.KERNEL_URL ?? "http://kernel:8000";

async function get<T>(path: string): Promise<T> {
  return absolute<T>(`${base}${path}`);
}

async function absolute<T>(url: string, limitMs?: number): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    headers: identity(await headers()),
    ...(limitMs ? { signal: AbortSignal.timeout(limitMs) } : {}),
  });
  if (!response.ok) throw new Error(`${url} respondió ${response.status}`);
  return (await response.json()) as T;
}

export function identity(incoming: Pick<Headers, "get">): Record<string, string> {
  const forwarded: Record<string, string> = {};
  for (const name of [SUBJECT, USER, SPACES]) {
    const value = incoming.get(name);
    if (value) forwarded[name] = value;
  }
  return forwarded;
}

export interface Preferences {
  glass_opacity: number;
  theme: "system" | "light" | "dark";
  wallpaper: string;
  icon_style?: "solid" | "ink" | "paper";
  home_panels?: { order?: string[]; hidden?: string[]; placed?: string[] };
}

export interface ModuleSummary {
  id: string;
  name: string;
  version: string;
  enabled: boolean;
  api_prefix: string;
  view?: string | null;
  family?: string | null;
  badge?: string | null;
  search?: string | null;
  scopes: string[];
  updated_at: string;
}

export const readWallpapers = () =>
  get<
    {
      id: string;
      name: string;
      luminance: { mean: number; variance: number };
      scrim: { light: number; dark: number };
      contrast: { light: number; dark: number };
      image: string;
      blurred: string;
    }[]
  >("/ui/wallpapers");

export const launchable = (modules: ModuleSummary[]) => modules.filter((module) => module.enabled);

export const readModules = () => get<ModuleSummary[]>("/modules");
export const readPreferences = () => get<Preferences>("/ui/preferences");
export const readDesktops = () => get<Record<Device, DesktopLayout>>("/ui/desktops");
export const readCatalogue = () => get<CatalogueEntry[]>("/ui/widgets");
export function serviceUrl(endpoint: string): string {
  const match = /^\/api\/([a-z][a-z0-9_]{1,30})\/(.*)$/.exec(endpoint);
  if (!match) throw new Error(`endpoint que no cuelga de /api/<módulo>: ${endpoint}`);
  const [, source, rest] = match;
  const host = source === "kernel" ? base : `http://${source}:8000`;
  return `${host}/${rest}`;
}

export const readWidget = (endpoint: string, limitMs?: number) =>
  absolute<Envelope>(serviceUrl(endpoint), limitMs);

export async function readPanel(apiPrefix: string, limitMs?: number): Promise<PanelContribution[]> {
  try {
    const found = await absolute<PanelContribution | { panels: PanelContribution[] }>(serviceUrl(`${apiPrefix}/panel`), limitMs);
    return "panels" in found ? found.panels : [found];
  } catch {
    return [];
  }
}

export async function readArea(area: AreaKey, modules: ModuleSummary[], limitMs?: number): Promise<Contributor[]> {
  const apps = modules.filter((module) => AREA_APPS[area].includes(module.id));
  const found = await Promise.all(
    apps.map(async (module) =>
      (await readPanel(module.api_prefix, limitMs))
        .filter((panel) => panel.area === area)
        .map((panel) => ({ source: module.id, name: module.name, panel })),
    ),
  );
  return found.flat();
}

export async function readBadge(badge: string, limitMs?: number): Promise<number | null> {
  try {
    const body = await absolute<{ count?: unknown }>(serviceUrl(badge), limitMs);
    return typeof body.count === "number" ? body.count : null;
  } catch {
    return null;
  }
}

export async function readSearch(endpoint: string, query: string, limit: number, limitMs: number): Promise<unknown> {
  try {
    const url = new URL(serviceUrl(endpoint));
    url.searchParams.set("q", query);
    url.searchParams.set("limit", String(limit));
    return await absolute<unknown>(url.toString(), limitMs);
  } catch {
    return null;
  }
}
