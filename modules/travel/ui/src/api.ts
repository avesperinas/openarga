import { Unauthorised, createApi, invalidate, problemOf } from "@openarga/app";
import { createOfflineQueue, repeatable as replayable } from "@openarga/app/offline";

export { Unauthorised, signIn } from "@openarga/app";
export { NeedsNetwork, Queued } from "@openarga/app/offline";

export const api = createApi("travel");
const { get } = api;
const BASE = api.base;

export const queue = createOfflineQueue({ app: "travel" });
queue.onSent(() => invalidate(""));

export type Mode = "plane" | "train" | "car" | "bus" | "boat";
export type Category = "transport" | "lodging" | "other";
export type Status = "plan" | "confirmed";
export type Phase = "plan" | "upcoming" | "ongoing" | "done";

export interface Place {
  id: string;
  name: string;
  display_name: string | null;
  lat: number | null;
  lon: number | null;
  country_code: string | null;
  region_code: string | null;
  country: string | null;
  region: string | null;
  kind: string | null;
  category?: PlaceCategory | null;
}

export type PlaceCategory =
  | "restaurant"
  | "nightlife"
  | "cafe"
  | "market"
  | "beach"
  | "nature"
  | "viewpoint"
  | "culture"
  | "castle"
  | "town"
  | "shopping"
  | "parking"
  | "lodging"
  | "other";

export interface BookingFacts {
  confirmation?: string | null;
  provider?: string | null;
  booking_url?: string | null;
  cost_eur?: number | null;
}

export interface Stay extends BookingFacts {
  id: string;
  place: Place;
  arrives_on: string;
  leaves_on: string;
  nights: number;
  accommodation: string | null;
  check_in_at?: string | null;
  check_out_at?: string | null;
  address?: string | null;
}

export interface Visit {
  id: string;
  place: Place;
  stay_id: string | null;
  visited_on: string | null;
  note: string | null;
}

export interface Leg extends BookingFacts {
  id: string;
  from_place: Place;
  to_place: Place;
  mode: Mode;
  travelled_on: string | null;
  km: number | null;
  note: string | null;
  on_map: boolean | null;
  departs_at?: string | null;
  arrives_on?: string | null;
  arrives_at?: string | null;
  carrier?: string | null;
  number?: string | null;
  from_code?: string | null;
  to_code?: string | null;
  terminal?: string | null;
  seat?: string | null;
  ticket_leg_id?: string | null;
  paid_by?: string | null;
}

export interface Expense {
  id: string;
  category: Category;
  concept: string;
  amount_eur: number;
  note: string | null;
  mine: boolean;
  amount?: number | null;
  currency?: string;
  fx_rate?: number | null;
  fx_on?: string | null;
  total_eur?: number | null;
  spent_on?: string | null;
  paid_by?: string | null;
  stay_id?: string | null;
  leg_id?: string | null;
  block_id?: string | null;
}

export interface Spend {
  per_person: number;
  group: number;
  per_day: number | null;
  by_category: Record<Category, number>;
}

export interface Trip {
  id: string;
  title: string;
  starts_on: string;
  ends_on: string;
  days: number;
  nights: number;
  travellers: number;
  companions: string[];
  tags: string[];
  countries: string[];
  km: number;
  spend: Spend;
  source: string;
  archived: boolean;
  status: Status;
  phase: Phase;
  idea_id?: string | null;
  budget_eur?: number | null;
  space_id: string | null;
  mine: boolean;
  summary?: string | null;
  cover?: { version: number; author: string | null; license: string | null; page: string | null } | null;
  notes: string | null;
  stays: Stay[];
  visits: Visit[];
  legs: Leg[];
  expenses: Expense[];
}

export interface OtherPlace {
  id: string;
  place: Place;
  note: string | null;
  source: string;
}

export interface Atlas {
  trips: Trip[];
  others: OtherPlace[];
  home: Place | null;
  ideas?: Idea[];
}

export interface AreaVisited {
  code: string;
  name: string;
  slept: boolean;
  trips: number;
  nights: number;
  first: string | null;
  last: string | null;
  places: string[];
}

export interface Stats {
  trips: number;
  nights: number;
  km: number;
  countries: number;
  regions: number;
  europe_visited: string[];
  europe_total: number;
  by_year: { year: number; trips: number; nights: number; km: number; spend_per_person: number }[];
  km_by_mode: Record<Mode, number>;
  top_countries: AreaVisited[];
  cost_per_day: { trip_id: string; title: string; starts_on: string; per_day: number }[];
  average_cost_per_day: number | null;
  spend_per_night_by_country: { code: string; name: string; per_night: number; nights: number }[];
  nights_calendar: Record<string, number>;
}

export interface Candidate {
  name: string;
  display_name: string;
  lat: number;
  lon: number;
  kind: string;
  osm_type: "node" | "way" | "relation";
  osm_id: number;
  country_code: string | null;
  region_code: string | null;
  country: string | null;
  region: string | null;
  category?: PlaceCategory | null;
}

export interface Search {
  candidates: Candidate[];
  failed: { source: string; reason: string }[];
}

export interface TripIn {
  title: string;
  starts_on: string;
  ends_on: string;
  travellers: number;
  companions: string[];
  tags: string[];
  notes: string | null;
  status?: Status;
  budget_eur?: string | null;
}

export function repeatable(method: string, body: unknown): boolean {
  return method === "PATCH" || replayable(method, body);
}

function send<T>(path: string, method: string, body?: unknown, what = "un cambio"): Promise<T> {
  return queue.send<T>(`${BASE}${path}`, method, body, { what, repeatable: repeatable(method, body) });
}

async function answer<T>(path: string, response: Response): Promise<T> {
  if (response.status === 401) throw new Unauthorised("sin sesión");
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(problemOf(body) ?? `${path}: ${response.status}`);
  }
  return (await response.json()) as T;
}

export const readMe = api.readMe;
export const readVersion = api.readVersion;

export interface Space {
  id: string;
  name: string;
  me: string;
  members: { user_id: string; name: string | null }[];
}

export const readSpaces = () => api.raw<Space[]>("/api/kernel/spaces");

export const readAtlas = () => get<Atlas>("/atlas");
export const readTrip = (id: string) => get<Trip>(`/trips/${id}`);
export const readStats = () => get<Stats>("/stats");
export const readConcepts = () => get<Record<Category, string[]>>("/concepts");
export const readPlaces = (query?: string) =>
  get<Place[]>(`/places${query ? `?query=${encodeURIComponent(query)}` : ""}`);
export const searchPlaces = (query: string) => get<Search>(`/places/search?query=${encodeURIComponent(query)}`);

export const savePlace = (place: Partial<Candidate> & { name: string }) => send<Place>("/places", "POST", place);
export const setPlaceCategory = (placeId: string, category: PlaceCategory) =>
  send<Place>(`/places/${placeId}/category`, "PUT", { category }, "el tipo del sitio");
export const createTrip = (trip: TripIn) => send<Trip>("/trips", "POST", trip);
export const updateTrip = (id: string, trip: TripIn, shift = false) =>
  send<Trip>(`/trips/${id}${shift ? "?shift=true" : ""}`, "PUT", trip);
export const setStatus = (id: string, status: Status) =>
  send<Trip>(`/trips/${id}/status`, "PUT", { status });
export const deleteTrip = (id: string) => send<void>(`/trips/${id}`, "DELETE");
export const shareTrip = (id: string, spaceId: string | null) =>
  send<Trip>(`/trips/${id}/space`, "PUT", { space_id: spaceId });
export const archiveTrip = (id: string, archived: boolean) =>
  send<Trip>(`/trips/${id}/archived`, "PUT", { archived });
export const addOtherPlace = (other: { place_id: string; note: string | null }) =>
  send<OtherPlace>("/others", "POST", other);
export const deleteOtherPlace = (id: string) => send<void>(`/others/${id}`, "DELETE");
export const setHome = (placeId: string) => send<Place>("/home", "PUT", { place_id: placeId });
export const clearHome = () => send<void>("/home", "DELETE");

export const addStay = (tripId: string, stay: StayIn) => send<Trip>(`/trips/${tripId}/stays`, "POST", stay);
export const updateStay = (tripId: string, stayId: string, stay: StayIn) =>
  send<Trip>(`/trips/${tripId}/stays/${stayId}`, "PUT", stay);
export const addVisit = (
  tripId: string,
  visit: { place_id: string; stay_id: string | null; visited_on: string | null; note: string | null },
) => send<Trip>(`/trips/${tripId}/visits`, "POST", visit);
export interface LegIn extends TicketIn {
  from_place_id: string;
  to_place_id: string;
  mode: Mode;
  travelled_on: string | null;
  note?: string | null;
  on_map?: boolean | null;
}
export const addLeg = (tripId: string, leg: LegIn) => send<Trip>(`/trips/${tripId}/legs`, "POST", leg);
export const updateLeg = (tripId: string, legId: string, leg: LegIn) =>
  send<Trip>(`/trips/${tripId}/legs/${legId}`, "PUT", leg);
export interface ExpenseIn {
  category: Category;
  concept: string;
  note: string | null;
  amount_eur?: string;
  amount?: string;
  currency?: string;
  paid_by?: string | null;
  spent_on?: string | null;
  fx_rate?: string | null;
  shares?: { traveller_id: string; amount: string }[] | null;
}

export interface Traveller {
  id: string;
  name: string;
  me: boolean;
  position: number;
  member_user_id?: string | null;
}

export const readTravellers = (tripId: string) => get<Traveller[]>(`/trips/${tripId}/travellers`);
export const updateTraveller = (
  tripId: string,
  travellerId: string,
  change: { name?: string; member_user_id?: string | null },
) => send<Traveller[]>(`/trips/${tripId}/travellers/${travellerId}`, "PATCH", change, "un viajero");

export interface Balance {
  people: { traveller: Traveller; paid_eur: number; share_eur: number; net_eur: number }[];
  transfers: { from_traveller: Traveller; to_traveller: Traveller; amount_eur: number }[];
  settlements: {
    id: string;
    from_traveller: Traveller;
    to_traveller: Traveller;
    amount_eur: number;
    settled_on: string;
    note: string | null;
  }[];
  unassigned_eur: number;
}

export const readBalance = (tripId: string) => get<Balance>(`/trips/${tripId}/balance`);
export const addSettlement = (
  tripId: string,
  settlement: { from_traveller: string; to_traveller: string; amount_eur: string },
) => send<Balance>(`/trips/${tripId}/settlements`, "POST", settlement);
export const removeSettlement = (tripId: string, id: string) =>
  send<Balance>(`/trips/${tripId}/settlements/${id}`, "DELETE");

export const addExpense = (tripId: string, expense: ExpenseIn) =>
  send<Trip>(
    `/trips/${tripId}/expenses`,
    "POST",
    { id: crypto.randomUUID(), ...expense },
    `el gasto «${expense.concept}»`,
  );
export const updateExpense = (tripId: string, expenseId: string, expense: ExpenseIn) => send<Trip>(`/trips/${tripId}/expenses/${expenseId}`, "PUT", expense);
export const deletePart = (tripId: string, part: "stays" | "visits" | "legs" | "expenses", id: string) =>
  send<Trip>(`/trips/${tripId}/${part}/${id}`, "DELETE");

export type Kind = "activity" | "transport" | "meal" | "accommodation" | "free_time" | "other";

export interface Block extends BookingFacts {
  id: string;
  day: string | null;
  position: number;
  kind: Kind;
  title: string;
  starts_at: string | null;
  ends_at: string | null;
  place: Place | null;
  visit_id: string | null;
  notes: string | null;
  mine: boolean;
}

export interface DayItem {
  type: "check_out" | "leg" | "check_in" | "block";
  stay: Stay | null;
  leg: Leg | null;
  block: Block | null;
}

export interface Day {
  day: string;
  number: number;
  title?: string | null;
  sleeping: Stay | null;
  items: DayItem[];
}

export interface Itinerary {
  trip_id: string;
  title: string;
  days: Day[];
  unscheduled: Block[];
}

export interface BookingIn {
  confirmation?: string | null;
  provider?: string | null;
  booking_url?: string | null;
  cost_eur?: string | null;
  paid_by?: string | null;
}

export interface StayIn extends BookingIn {
  place_id: string;
  arrives_on: string;
  leaves_on: string;
  accommodation: string | null;
  check_in_at?: string | null;
  check_out_at?: string | null;
  address?: string | null;
}

export interface TicketIn extends BookingIn {
  departs_at?: string | null;
  arrives_on?: string | null;
  arrives_at?: string | null;
  carrier?: string | null;
  number?: string | null;
  from_code?: string | null;
  to_code?: string | null;
  terminal?: string | null;
  seat?: string | null;
  ticket_leg_id?: string | null;
}

export interface Booking {
  type: "stay" | "leg" | "block";
  id: string;
  title: string;
  detail: string | null;
  day: string | null;
  until: string | null;
  at: string | null;
  confirmation: string | null;
  provider: string | null;
  booking_url: string | null;
  cost_eur: number | null;
  booked: boolean;
  paid_by?: string | null;
  ticket_leg_id?: string | null;
  ticket_of?: string | null;
}

export const readBookings = (tripId: string) => get<Booking[]>(`/trips/${tripId}/bookings`);

export interface BlockIn extends BookingIn {
  id?: string;
  day: string | null;
  kind: Kind;
  title: string;
  starts_at: string | null;
  ends_at: string | null;
  place_id: string | null;
  notes: string | null;
}

export const readDays = (tripId: string) => get<Itinerary>(`/trips/${tripId}/days`);
export const addBlock = (tripId: string, block: BlockIn) =>
  send<Itinerary>(`/trips/${tripId}/blocks`, "POST", block, `«${block.title}» al itinerario`);
export const updateBlock = (tripId: string, blockId: string, block: BlockIn) =>
  send<Itinerary>(`/trips/${tripId}/blocks/${blockId}`, "PUT", block, `el cambio de «${block.title}»`);
export const moveBlock = (tripId: string, blockId: string, day: string | null, position: number) =>
  send<Itinerary>(`/trips/${tripId}/blocks/${blockId}/position`, "PUT", { day, position }, "mover un bloque");
export const removeBlock = (tripId: string, blockId: string) =>
  send<Itinerary>(`/trips/${tripId}/blocks/${blockId}`, "DELETE");
export const setDayTitle = (tripId: string, day: string, title: string) =>
  send<Itinerary>(`/trips/${tripId}/days/${day}/title`, "PUT", { title }, "el título del día");

export type Profile = "foot" | "bike" | "car";

export interface RouteStop {
  type: "stay" | "block";
  id: string;
  number: number | null;
  title: string;
  lon: number;
  lat: number;
}

export interface DayRoute {
  day: string;
  profile: Profile;
  stops: RouteStop[];
  line: [number, number][] | null;
  legs: { distance_m: number; duration_s: number }[];
  distance_m: number | null;
  duration_s: number | null;
  failed: string | null;
}

export const readDayRoute = (tripId: string, day: string, profile: Profile) =>
  get<DayRoute>(`/trips/${tripId}/days/${day}/route?profile=${profile}`);

export type NearbyKind = "sights" | "food" | "nature" | "shopping" | "nightlife";

export interface NearbyPlace extends Candidate {
  local_name: string | null;
  distance_m: number;
  group: NearbyKind;
  cuisine: string | null;
  website: string | null;
  opening_hours: string | null;
}

export const readNearby = (lat: number, lon: number, kind: NearbyKind, radius = 1000) =>
  get<{ places: NearbyPlace[]; failed: string | null }>(
    `/nearby?lat=${lat}&lon=${lon}&kind=${kind}&radius=${radius}`,
  );

export interface TodayEntry {
  type: "check_out" | "leg" | "check_in" | "block";
  id: string;
  title: string;
  detail: string | null;
  kind: string | null;
  starts_at: string | null;
  ends_at: string | null;
  where: { name: string; lat: number; lon: number; google: string; apple: string } | null;
  confirmation: string | null;
}

export interface Today {
  day: string;
  trip: { id: string; title: string; number: number; days: number; day_title?: string | null } | null;
  sleeping: string | null;
  entries: TodayEntry[];
  here: [number, number] | null;
  next_trip: Trip | null;
  journal?: string | null;
}

export const readToday = (day: string) => get<Today>(`/today?day=${day}`);

export interface Idea {
  id: string;
  title: string;
  notes: string | null;
  budget_eur: number | null;
  days_min: number | null;
  days_max: number | null;
  months: number[];
  tags: string[];
  archived: boolean;
  places: { id: string; place: Place; note: string | null }[];
  trips: { id: string; title: string; starts_on: string; phase: Phase }[];
  countries: string[];
  space_id: string | null;
  mine: boolean;
}

export interface IdeaIn {
  title: string;
  notes: string | null;
  budget_eur: string | null;
  days_min: number | null;
  days_max: number | null;
  months: number[];
  tags: string[];
}

export const readIdeas = () => get<Idea[]>("/ideas");
export const readIdea = (id: string) => get<Idea>(`/ideas/${id}`);
export const createIdea = (idea: IdeaIn) => send<Idea>("/ideas", "POST", idea);
export const updateIdea = (id: string, idea: IdeaIn) => send<Idea>(`/ideas/${id}`, "PUT", idea);
export const deleteIdea = (id: string) => send<void>(`/ideas/${id}`, "DELETE");
export const archiveIdea = (id: string, archived: boolean) =>
  send<Idea>(`/ideas/${id}/archived`, "PUT", { archived });
export const addIdeaPlace = (id: string, placeId: string) =>
  send<Idea>(`/ideas/${id}/places`, "POST", { place_id: placeId });
export const removeIdeaPlace = (id: string, ideaPlaceId: string) =>
  send<Idea>(`/ideas/${id}/places/${ideaPlaceId}`, "DELETE");
export const planIdea = (id: string, plan: { starts_on: string; ends_on: string; travellers: number }) =>
  send<Trip>(`/ideas/${id}/plan`, "POST", plan);
export const shareIdea = (id: string, spaceId: string | null) =>
  send<Idea>(`/ideas/${id}/space`, "PUT", { space_id: spaceId });

export interface ForecastDay {
  day: string;
  code: number | null;
  sky: string;
  max_c: number | null;
  min_c: number | null;
  rain_chance: number | null;
}

export interface ClimateMonth {
  month: number;
  max_c: number;
  min_c: number | null;
  rain_mm: number;
  rain_days: number;
}

export const readForecast = (lat: number, lon: number) =>
  get<{ weather: { timezone: string; days: ForecastDay[] } | null; failed: string | null }>(
    `/weather/forecast?lat=${lat}&lon=${lon}`,
  );
export const readClimate = (lat: number, lon: number) =>
  get<{ weather: { years: string; months: ClimateMonth[] } | null; failed: string | null }>(
    `/weather/climate?lat=${lat}&lon=${lon}`,
  );

export type NoteCategory = "general" | "visa" | "culture" | "tips" | "health" | "other";

export interface TripNote {
  id: string;
  category: NoteCategory;
  title: string;
  body: string;
  position: number;
  updated_at: string;
  mine: boolean;
}

export interface NoteIn {
  id?: string;
  category: NoteCategory;
  title: string;
  body: string;
}

export interface JournalEntry {
  id: string;
  trip_id: string;
  day: string;
  body: string;
  updated_at: string;
}

export const readJournal = (tripId: string) => get<JournalEntry[]>(`/trips/${tripId}/journal`);
export const writeJournal = (tripId: string, day: string, body: string) =>
  send<JournalEntry[]>(`/trips/${tripId}/journal/${day}`, "PUT", { body }, "el diario");

export const readNotes = (tripId: string) => get<TripNote[]>(`/trips/${tripId}/notes`);
export const addNote = (tripId: string, note: NoteIn) =>
  send<TripNote[]>(`/trips/${tripId}/notes`, "POST", { id: crypto.randomUUID(), ...note }, `la nota «${note.title}»`);
export const updateNote = (tripId: string, noteId: string, note: NoteIn) =>
  send<TripNote[]>(`/trips/${tripId}/notes/${noteId}`, "PUT", note, `la nota «${note.title}»`);
export const removeNote = (tripId: string, noteId: string) =>
  send<TripNote[]>(`/trips/${tripId}/notes/${noteId}`, "DELETE");

export type ListKind = "packing" | "todo";

export interface CheckItem {
  id: string;
  list: ListKind;
  text: string;
  position: number;
  checked: boolean;
  traveller_id?: string | null;
}

export const readChecklist = (tripId: string) => get<CheckItem[]>(`/trips/${tripId}/checklist`);
export const addCheckItems = (tripId: string, list: ListKind, texts: string[]) =>
  send<CheckItem[]>(
    `/trips/${tripId}/checklist`,
    "POST",
    texts.map((text) => ({ id: crypto.randomUUID(), list, text })),
    texts.length === 1 ? `«${texts[0]}»` : `${texts.length} cosas de la lista`,
  );
export const setChecked = (tripId: string, item: CheckItem, checked: boolean) =>
  send<CheckItem[]>(`/trips/${tripId}/checklist/${item.id}`, "PATCH", { checked }, `«${item.text}»`);
export const changeCheckItem = (
  tripId: string,
  item: CheckItem,
  change: { text?: string; traveller_id?: string | null },
) => send<CheckItem[]>(`/trips/${tripId}/checklist/${item.id}`, "PATCH", change, `«${change.text ?? item.text}»`);
export const removeCheckItem = (tripId: string, itemId: string) =>
  send<CheckItem[]>(`/trips/${tripId}/checklist/${itemId}`, "DELETE");
export const copyChecklist = (tripId: string, fromTripId: string, list: ListKind) =>
  send<CheckItem[]>(`/trips/${tripId}/checklist/copy`, "POST", { from_trip_id: fromTripId, list });

export type LinkKind = "stay" | "leg" | "block";

export interface TripDocument {
  id: string;
  name: string;
  content_type: string;
  size: number;
  created_at: string;
  mine: boolean;
  link: { type: LinkKind; id: string; title: string } | null;
}

export const DOCUMENT_LIMIT = 20 * 1024 * 1024;

export const readDocuments = (tripId: string) => get<TripDocument[]>(`/trips/${tripId}/documents`);
export const documentUrl = (tripId: string, documentId: string) =>
  `${BASE}/trips/${tripId}/documents/${documentId}/file`;

export const coverUrl = (trip: Pick<Trip, "id" | "cover">, size: "full" | "thumb" = "full") =>
  trip.cover ? `${BASE}/trips/${trip.id}/cover?size=${size}&v=${trip.cover.version}` : null;

export async function uploadCover(tripId: string, file: File): Promise<Trip> {
  const path = `/trips/${tripId}/cover`;
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method: "PUT",
      body: file,
      headers: { "content-type": file.type || "application/octet-stream", accept: "application/json" },
    });
  } catch {
    throw new Error("Sin conexión: subir una portada necesita red.");
  }
  return answer<Trip>(path, response);
}

export const removeCover = (tripId: string) => send<Trip>(`/trips/${tripId}/cover`, "DELETE");
export const setSummary = (trip: Trip, summary: string) =>
  send<Trip>(
    `/trips/${trip.id}`,
    "PUT",
    {
      title: trip.title,
      starts_on: trip.starts_on,
      ends_on: trip.ends_on,
      travellers: trip.travellers,
      companions: trip.companions,
      tags: trip.tags,
      notes: trip.notes,
      summary: summary.trim() || null,
    },
    "el resumen del viaje",
  );

export async function uploadDocument(
  tripId: string,
  file: File,
  link: { type: LinkKind; id: string } | null,
): Promise<TripDocument[]> {
  const query = new URLSearchParams({ name: file.name });
  if (link) {
    query.set("link_type", link.type);
    query.set("link_id", link.id);
  }
  const path = `/trips/${tripId}/documents?${query}`;
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "content-type": file.type || "application/octet-stream", accept: "application/json" },
      body: file,
    });
  } catch {
    throw new Error("Sin conexión: subir un documento necesita red.");
  }
  return answer<TripDocument[]>(path, response);
}

export const changeDocument = (
  tripId: string,
  documentId: string,
  change: { name?: string; link_type?: LinkKind; link_id?: string; unlink?: boolean },
) => send<TripDocument[]>(`/trips/${tripId}/documents/${documentId}`, "PATCH", change, "un documento");
export const removeDocument = (tripId: string, documentId: string) =>
  send<TripDocument[]>(`/trips/${tripId}/documents/${documentId}`, "DELETE");
