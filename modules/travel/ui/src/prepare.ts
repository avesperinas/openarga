import { type DayRoute, type Itinerary, type TripDocument, documentUrl, readDayRoute, readDays, readDocuments } from "./api";
import { controlled } from "./offline";

export function tileOf(lon: number, lat: number, zoom: number): [number, number] {
  const n = 2 ** zoom;
  const x = Math.floor(((lon + 180) / 360) * n);
  const rad = (lat * Math.PI) / 180;
  const y = Math.floor(((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * n);
  return [Math.min(n - 1, Math.max(0, x)), Math.min(n - 1, Math.max(0, y))];
}

export function tilesFor(box: [number, number, number, number], zooms: number[]): string[] {
  const found = new Set<string>();
  const [west, south, east, north] = box;
  for (const zoom of zooms) {
    const [x0, y0] = tileOf(west, north, zoom);
    const [x1, y1] = tileOf(east, south, zoom);
    for (let x = x0; x <= x1; x += 1) for (let y = y0; y <= y1; y += 1) found.add(`${zoom}/${x}/${y}`);
  }
  return [...found];
}

export function boxAround(points: [number, number][], margin = 0.01): [number, number, number, number] | null {
  if (points.length === 0) return null;
  const lons = points.map((one) => one[0]);
  const lats = points.map((one) => one[1]);
  return [
    Math.min(...lons) - margin,
    Math.min(...lats) - margin,
    Math.max(...lons) + margin,
    Math.max(...lats) + margin,
  ];
}

const ZOOMS = [11, 12, 13, 14, 15];
const WHOLE_ZOOMS = [7, 8, 9, 10];
const MAX_TILES = 900;

export const DOCUMENTS_BUDGET = 100 * 1024 * 1024;

export function documentsToKeep(papers: TripDocument[], budget = DOCUMENTS_BUDGET): TripDocument[] {
  const kept: TripDocument[] = [];
  let used = 0;
  for (const one of [...papers].sort((a, b) => b.created_at.localeCompare(a.created_at))) {
    if (used + one.size > budget) continue;
    kept.push(one);
    used += one.size;
  }
  return kept;
}

export class CannotKeep extends Error {
  constructor() {
    super("Este navegador no deja guardar el viaje sin conexión.");
  }
}

export async function prepare(tripId: string, onProgress: (done: number, total: number) => void): Promise<number> {
  if (!(await controlled())) throw new CannotKeep();
  const days: Itinerary = await readDays(tripId);
  const papers: TripDocument[] = await readDocuments(tripId).catch(() => []);
  const pages = [
    `/api/travel/trips/${tripId}`,
    `/api/travel/trips/${tripId}/bookings`,
    `/api/travel/trips/${tripId}/notes`,
    `/api/travel/trips/${tripId}/balance`,
    `/api/travel/trips/${tripId}/checklist`,
    `/api/travel/trips/${tripId}/documents`,
    "/api/travel/atlas",
    "/api/travel/me",
    ...days.days.map((day) => `/api/travel/today?day=${day.day}`),
    ...new Set(
      days.days.flatMap((day) => {
        const place = day.sleeping?.place;
        return place?.lat != null && place.lon != null
          ? [`/api/travel/weather/forecast?lat=${place.lat}&lon=${place.lon}`]
          : [];
      }),
    ),
  ];
  const routes: DayRoute[] = [];
  for (const day of days.days) {
    try {
      routes.push(await readDayRoute(tripId, day.day, "foot"));
    } catch {
    }
  }
  const tiles = new Set<string>();
  const whole = boxAround(
    routes.flatMap((route) => route.stops.map((one) => [one.lon, one.lat] as [number, number])),
    0.05,
  );
  if (whole) for (const tile of tilesFor(whole, WHOLE_ZOOMS)) tiles.add(tile);
  for (const route of routes) {
    const box = boxAround([...route.stops.map((one) => [one.lon, one.lat] as [number, number]), ...(route.line ?? [])]);
    if (box) for (const tile of tilesFor(box, ZOOMS)) tiles.add(tile);
  }
  const wanted = [
    ...pages,
    ...documentsToKeep(papers).map((one) => documentUrl(tripId, one.id)),
    ...[...tiles].slice(0, MAX_TILES).map((tile) => `/api/travel/tiles/${tile}`),
  ];
  let done = 0;
  let failed = 0;
  onProgress(done, wanted.length);
  const queue = [...wanted];
  await Promise.all(
    Array.from({ length: 4 }, async () => {
      for (let next = queue.shift(); next; next = queue.shift()) {
        try {
          const response = await fetch(next, { headers: { accept: "application/json" } });
          if (!response.ok && response.status !== 204) failed += 1;
        } catch {
          failed += 1;
        }
        done += 1;
        onProgress(done, wanted.length);
      }
    }),
  );
  return failed;
}
