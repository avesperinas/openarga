import { Unauthorised, createApi, signIn } from "@openarga/app";
import type { InletSetting, SourceAsk, SourceSearchResult } from "@openarga/ui";

const client = createApi("planner");
const { get, send } = client;

export { Unauthorised, signIn };

export type Tone = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10;
export type Scope = "this" | "following" | "all";
export type Display = "events" | "background";

export interface SubscriptionState {
  provider: string | null;
  updated_at: string | null;
  failing: boolean;
  detail: string | null;
  paused: boolean;
}

export interface Layer {
  id: string;
  name: string;
  tone: Tone;
  origin: "own" | "subscription" | "app";
  visible: boolean;
  position: number;
  display?: Display;
  connection_id: string | null;
  app?: string | null;
  movable?: boolean;
  subscription?: SubscriptionState | null;
  days_off_from?: string[];
}

export type Ask = SourceAsk;

export interface SourceInlet {
  key: string;
  app: string;
  title: string;
  settings: InletSetting[];
}

export interface Source {
  provider: string;
  title: string;
  subtitle: string;
  tone: Tone;
  asks: Ask[];
  many: boolean;
  name: string;
  group: string;
  subscribed: Layer[];
  inlets?: SourceInlet[];
}

export interface SubscriptionMenu {
  groups?: { id: string; title: string }[];
  sources: Source[];
  others: Layer[];
}

export interface Choice {
  code: string;
  name: string;
  league?: string;
  league_name?: string;
}

export interface Occurrence {
  id: string;
  event_id: string;
  calendar_id: string;
  title: string;
  all_day: boolean;
  start: string;
  end: string;
  tz: string;
  location: string | null;
  notes: string | null;
  url: string | null;
  status: string;
  original_start: string | null;
  rrule: string | null;
  repeat: string | null;
  moved: boolean;
  href?: string | null;
}

export interface CalendarEventFull {
  id: string;
  calendar_id: string;
  title: string;
  all_day: boolean;
  start: string;
  end: string;
  tz: string;
  location: string | null;
  notes: string | null;
  url: string | null;
  rrule: string | null;
  repeat: string | null;
  status: string;
  source: string;
}

export interface EventDraft {
  calendar_id?: string | null;
  title?: string;
  all_day?: boolean;
  start?: string;
  end?: string;
  tz?: string;
  location?: string | null;
  notes?: string | null;
  url?: string | null;
  rrule?: string | null;
}

export const readLayers = () => get<Layer[]>("/calendars");
export const createLayer = (name: string, tone: Tone, display: Display, daysOffFrom: string[] = []) =>
  send<Layer>("/calendars", "POST", { name, tone, display, days_off_from: daysOffFrom });
export const updateLayer = (
  id: string,
  patch: Partial<Pick<Layer, "name" | "tone" | "visible" | "display" | "days_off_from">>,
) => send<Layer>(`/calendars/${id}`, "PATCH", patch);
export const reorderLayers = (ids: string[]) => send<Layer[]>("/calendars/order", "PUT", { ids });

export const readOccurrences = (from: Date, to: Date) =>
  get<Occurrence[]>(
    `/occurrences?from=${encodeURIComponent(from.toISOString())}&to=${encodeURIComponent(to.toISOString())}`,
  );
export const searchEvents = (query: string) =>
  get<Occurrence[]>(`/search?q=${encodeURIComponent(query)}&limit=20`);
export const readEvent = (id: string) => get<CalendarEventFull>(`/events/${id}`);
export const createEvent = (draft: EventDraft) => send<CalendarEventFull>("/events", "POST", draft);
export const moveAppEvent = (id: string, range: { start: string; end: string; all_day: boolean }) =>
  send<Occurrence>(`/app-events/${id.replace(/^app:/, "")}/move`, "POST", range);
export const updateEvent = (id: string, changes: EventDraft, scope: Scope, originalStart: string | null) =>
  send<CalendarEventFull>(`/events/${id}`, "PATCH", { changes, scope, original_start: originalStart });
export const cancelEvent = (id: string, scope: Scope, originalStart: string | null) =>
  send<CalendarEventFull>(`/events/${id}/cancel`, "POST", { scope, original_start: originalStart });

export const readSubscriptionMenu = () => get<SubscriptionMenu>("/subscriptions/catalogue");
export const searchSource = (provider: string, ask: string, query?: string, parent?: string) => {
  const params = new URLSearchParams({ provider, ask });
  if (query) params.set("q", query);
  if (parent) params.set("parent", parent);
  return get<SourceSearchResult>(`/subscriptions/search?${params.toString()}`);
};
export const unsubscribe = (layerId: string) => send<void>(`/subscriptions/${encodeURIComponent(layerId)}`, "DELETE");

export const subscribe = (provider: string, name: string, tone: Tone, params: Record<string, unknown>) =>
  send<Layer>("/subscriptions", "POST", { provider, name, tone, params });
export const hideSubscribed = (id: string) =>
  send<void>(`/feed/${encodeURIComponent(id.replace(/^feed:/, ""))}/hide`, "POST");

export const readVersion = client.readVersion;

export const VIEWER_TZ = (() => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
})();
