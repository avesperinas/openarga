import { Unauthorised, createApi, problemOf, signIn } from "@openarga/app";
import type { SourceAsk } from "@openarga/ui";

const BASE = "/api/outings";

export type Kind = "eat" | "plan" | "getaway" | "trip";

export interface Place {
  name: string;
  detail?: string | null;
  town?: string | null;
  country?: string | null;
  country_code?: string | null;
  lat?: number | null;
  lon?: number | null;
  osm_ref?: string | null;
}

export interface PhotoCredit {
  author: string | null;
  license: string | null;
  page: string;
}

export interface Wish {
  id: string;
  kind: Kind;
  name: string;
  body: string | null;
  place: Place | null;
  has_photo: boolean;
  photo_version: string | null;
  photo_credit?: PhotoCredit | null;
  done_at: string | null;
  event_id?: string | null;
  starts_on?: string | null;
  ends_on?: string | null;
  source: string;
  created_at: string;
  updated_at: string;
  space_id: string | null;
  mine: boolean;
}

export interface WishIn {
  kind: Kind;
  name: string;
  body: string | null;
  place: Place | null;
}

export interface PlaceCandidate extends Place {
  kind?: string | null;
}

export interface PlaceSearch {
  candidates: PlaceCandidate[];
  failed: { source: string; reason: string }[];
}

const client = createApi("outings");
const { get, send } = client;

export { Unauthorised, problemOf, signIn };

async function answer<T>(path: string, response: Response): Promise<T> {
  if (response.status === 401) throw new Unauthorised("sin sesión");
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(problemOf(body) ?? `${path}: ${response.status}`);
  }
  return (await response.json()) as T;
}

export const readVersion = client.readVersion;

export const readWishes = (archived = false) => get<Wish[]>(`/wishes${archived ? "?archived=true" : ""}`);
export const readWish = (id: string) => get<Wish>(`/wishes/${id}`);
export const addWish = (wish: WishIn) => send<Wish>("/wishes", "POST", wish);
export const updateWish = (id: string, patch: Partial<WishIn>) => send<Wish>(`/wishes/${id}`, "PATCH", patch);
export const markDone = (id: string) => send<Wish>(`/wishes/${id}/done`, "POST");
export const restoreWish = (id: string) => send<Wish>(`/wishes/${id}/restore`, "POST");
export const deleteWish = (id: string) => send<void>(`/wishes/${id}`, "DELETE");
export interface Planned {
  app: string;
  id: string;
  title: string;
  phase: "idea" | "plan" | "upcoming" | "ongoing";
  href: string;
  starts_on: string | null;
  ends_on: string | null;
  image: string | null;
  detail: string;
}
export const readPlanned = () => get<Planned[]>("/planned");
export const wishToIdea = (id: string) => send<{ href: string; already: boolean }>(`/wishes/${id}/idea`, "POST");
export const shareWish = (id: string, spaceId: string | null) =>
  send<Wish>(`/wishes/${id}/space`, "PUT", { space_id: spaceId });

export interface Space {
  id: string;
  name: string;
  me: string;
  members: { user_id: string; name: string | null }[];
}

export const readSpaces = () => client.raw<Space[]>("/api/kernel/spaces");
export const removePhoto = (id: string) => send<Wish>(`/wishes/${id}/photo`, "DELETE");

export async function uploadPhoto(id: string, photo: Blob): Promise<Wish> {
  const path = `/wishes/${id}/photo`;
  const response = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "content-type": photo.type || "image/jpeg", accept: "application/json" },
    body: photo,
  });
  return answer<Wish>(path, response);
}

export function creditLine(credit: PhotoCredit) {
  return ["Foto: " + (credit.author ?? "autor sin nombre"), credit.license, "Wikimedia Commons"]
    .filter(Boolean)
    .join(" · ");
}

export function photoUrl(wish: Pick<Wish, "id" | "has_photo" | "photo_version">, size: "full" | "thumb" = "full") {
  if (!wish.has_photo) return undefined;
  return `${BASE}/wishes/${wish.id}/photo?size=${size}&v=${wish.photo_version ?? ""}`;
}

export type Category = "eat" | "stage" | "culture" | "festival" | "outdoors";
export type Period = "weekend" | "week" | "month" | "year";

export interface EventLink {
  name: string;
  url: string;
  page: string;
}

export interface AgendaEvent {
  id: string;
  title: string;
  starts_on: string;
  ends_on: string;
  time: string | null;
  venue: string | null;
  town: string | null;
  category: Category;
  summary: string | null;
  links: EventLink[];
  in_calendar: boolean;
  wish_id: string | null;
  lat?: number | null;
  lon?: number | null;
  first_seen: string;
  last_seen: string;
  sources?: { id: string; name: string; page: string }[];
  programme: string[];
  highlight: boolean;
  dismissed: boolean;
  zone: Zone;
}

export type Zone = "pamplona" | "navarra";
export type When = "weekend" | "week" | "month" | "quarter" | "year";

export interface Explored {
  first: string;
  last: string;
  total: number;
  events: AgendaEvent[];
}

export interface ExploreQuery {
  q?: string;
  when: When;
  zone?: Zone;
  category?: Category;
  sort: "best" | "date";
  limit?: number;
  offset?: number;
  since?: string;
}

export interface ForYouPick {
  event: AgendaEvent;
  reasons: string[];
  score: number;
}

export const readForYou = () => get<ForYouPick[]>("/foryou");

export function readExplore(query: ExploreQuery): Promise<Explored> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  return get<Explored>(`/explore?${params.toString()}`);
}

export interface Mine {
  from: string;
  to: string;
  events: AgendaEvent[];
}

export const readMine = (from: string, to: string) => get<Mine>(`/mine?from=${from}&to=${to}`);
export const dismissEvent = (id: string, on: boolean) => send<AgendaEvent>(`/events/${id}/dismiss?on=${on}`, "PUT");

export interface Interest {
  id: string;
  kind: "like" | "mute";
  term: string;
}

export const readInterests = () => get<Interest[]>("/interests");
export const addInterest = (kind: Interest["kind"], term: string) => send<Interest>("/interests", "POST", { kind, term });
export const removeInterest = (id: string) => send<Interest>(`/interests/${id}`, "DELETE");

export interface Agenda {
  period: Period;
  from: string;
  to: string;
  events: AgendaEvent[];
}

export const readAgenda = (period: Period, category?: Category) =>
  get<Agenda>(`/agenda?period=${period}${category ? `&category=${category}` : ""}`);
export const readEvent = (id: string) => get<AgendaEvent>(`/events/${id}`);
export const saveEvent = (id: string) => send<Wish>(`/events/${id}/save`, "POST");
export const splitEvent = (id: string, source: string) => send<AgendaEvent>(`/events/${id}/split/${source}`, "POST");
export const toCalendar = (id: string, on: boolean) => send<AgendaEvent>(`/events/${id}/calendar?on=${on}`, "PUT");

export interface PluggedSource {
  connection: string;
  label: string;
  state: string;
  missing: string[];
  paused: boolean;
  last_run_at: string | null;
  last_outcome: string | null;
  last_detail: string | null;
}

export interface OfferedSource {
  provider: string;
  title: string;
  subtitle: string;
  name: string;
  asks: SourceAsk[];
}

export interface AgendaSources {
  plugged: PluggedSource[];
  offered: OfferedSource[];
  failed: string | null;
}

export const readAgendaPrompt = () => get<{ prompt: string }>("/agenda/prompt");

export const readSources = () => get<AgendaSources>("/agenda/sources");
export const plugSource = (provider: string, label: string, params: Record<string, unknown>) =>
  send<{ connection: string }>("/agenda/sources", "POST", { provider, label, params });
export const unplugSource = (connection: string) => send<{ removed: boolean }>(`/agenda/sources/${connection}`, "DELETE");

export const hubPath = (connection: string) => `/hub/${connection}`;

export interface WishPoint {
  id: string;
  name: string;
  kind: Kind;
  lat: number;
  lon: number;
  has_photo: boolean;
  photo_version: string | null;
  where: string | null;
}

export interface EventPoint {
  id: string;
  title: string;
  starts_on: string;
  ends_on: string;
  category: Category;
  lat: number;
  lon: number;
  where: string | null;
}

export interface MapPoints {
  wishes: WishPoint[];
  events: EventPoint[];
}

export interface Near {
  id: string;
  name: string;
  kind: Kind;
  km: number;
}

export const readMap = (days = 30) => get<MapPoints>(`/map?days=${days}`);
export const readNear = (event: string) => get<Near[]>(`/events/${event}/near`);

declare const __OUTINGS_MAP__: string;

export const MAP_BASE = `/outings/map/v-${__OUTINGS_MAP__}/`;
export const GEO_BASE = "/outings/geo/";

export const searchPlaces = (query: string) => get<PlaceSearch>(`/places/search?q=${encodeURIComponent(query)}`);
