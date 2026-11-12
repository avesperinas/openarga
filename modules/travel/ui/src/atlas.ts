import type { MapArea, MapLevel, MapPlace, MapRoute } from "@openarga/ui/world-map";

import type { Leg, Mode, OtherPlace, Place, Trip } from "./api";

export const GEO = "/travel/geo/";

export interface Filters {
  years: [number, number];
  trip: string | null;
  companions: string[];
  tags: string[];
  modes: Mode[];
}

export const year = (day: string) => Number(day.slice(0, 4));

export function yearSpan(trips: Trip[]): [number, number] {
  const now = new Date().getFullYear();
  if (!trips.length) return [now, now];
  const years = trips.map((one) => year(one.starts_on));
  return [Math.min(...years), Math.max(...years)];
}

export function noFilters(trips: Trip[]): Filters {
  return { years: yearSpan(trips), trip: null, companions: [], tags: [], modes: [] };
}

export function activeFilters(filters: Filters): number {
  return (
    (filters.trip ? 1 : 0) + filters.companions.length + filters.tags.length + filters.modes.length
  );
}

export function matches(trip: Trip, filters: Filters): boolean {
  const starts = year(trip.starts_on);
  if (starts < filters.years[0] || starts > filters.years[1]) return false;
  if (filters.trip && trip.id !== filters.trip) return false;
  if (filters.companions.length && !trip.companions.some((one) => filters.companions.includes(one))) {
    return false;
  }
  if (filters.tags.length && !trip.tags.some((one) => filters.tags.includes(one))) return false;
  if (filters.modes.length && !trip.legs.some((leg) => filters.modes.includes(leg.mode))) return false;
  return true;
}

export function options(trips: Trip[]) {
  const sorted = (values: Iterable<string>) => [...new Set(values)].sort((a, b) => a.localeCompare(b, "es"));
  return {
    companions: sorted(trips.flatMap((one) => one.companions)),
    tags: sorted(trips.flatMap((one) => one.tags)),
    modes: [...new Set(trips.flatMap((one) => one.legs.map((leg) => leg.mode)))] as Mode[],
  };
}

export function areasOf(
  trips: Trip[],
  level: MapLevel,
  others: OtherPlace[] = [],
  home: Place | null = null,
): MapArea[] {
  if (level === "none") return [];
  const codeOf = (place: Place) => (level === "country" ? place.country_code : place.region_code);
  const codes = new Set<string>();
  const places = [
    ...trips.flatMap((trip) => [...trip.stays.map((one) => one.place), ...trip.visits.map((one) => one.place)]),
    ...others.map((one) => one.place),
  ];
  for (const place of places) {
    const code = codeOf(place);
    if (code) codes.add(code);
  }
  const homeCode = home ? codeOf(home) : null;
  const areas: MapArea[] = [...codes]
    .filter((code) => code !== homeCode)
    .map((code) => ({ code, tone: "slept", weight: 1 }));
  if (homeCode) areas.push({ code: homeCode, tone: "home", weight: 0 });
  return areas;
}

export function orderedLegs(trip: Trip): Leg[] {
  const stays = [...trip.stays].sort(
    (a, b) => a.arrives_on.localeCompare(b.arrives_on) || a.leaves_on.localeCompare(b.leaves_on),
  );
  const at = (place: Place, after: number) => stays.findIndex((one, index) => index >= after && one.place.id === place.id);
  const keyed = trip.legs.map((leg, input) => {
    const leaving = at(leg.from_place, 0);
    const to = at(leg.to_place, leaving + 1);
    const from = to >= 0 ? leaving : stays.map((one) => one.place.id).lastIndexOf(leg.from_place.id);
    const day =
      leg.travelled_on ??
      (to >= 0 ? stays[to]!.arrives_on : from >= 0 ? stays[from]!.leaves_on : trip.ends_on);
    const place = to >= 0 ? to : from >= 0 ? stays.length + from : stays.length * 2;
    return { leg, day, place, input };
  });
  return keyed
    .sort((a, b) => a.day.localeCompare(b.day) || a.place - b.place || a.input - b.input)
    .map((one) => one.leg);
}

export function drawn(trip: Trip, leg: Leg): boolean {
  if (leg.on_map !== null && leg.on_map !== undefined) return leg.on_map;
  const inside = new Set([...trip.stays.map((one) => one.place.id), ...trip.visits.map((one) => one.place.id)]);
  return inside.has(leg.from_place.id) && inside.has(leg.to_place.id);
}

export function legsAround(trip: Trip): Leg[] {
  return orderedLegs(trip).filter((leg) => drawn(trip, leg));
}

export function placesOf(trips: Trip[]): MapPlace[] {
  const found = new Map<string, { lon: number; lat: number; nights: number; stay: boolean }>();
  for (const trip of trips) {
    for (const stay of trip.stays) {
      const { place } = stay;
      if (place.lon === null || place.lat === null) continue;
      const known = found.get(place.id) ?? { lon: place.lon, lat: place.lat, nights: 0, stay: true };
      known.nights += stay.nights;
      known.stay = true;
      found.set(place.id, known);
    }
    for (const visit of trip.visits) {
      const { place } = visit;
      if (place.lon === null || place.lat === null || found.has(place.id)) continue;
      found.set(place.id, { lon: place.lon, lat: place.lat, nights: 0, stay: false });
    }
  }
  const top = Math.max(1, ...[...found.values()].map((one) => one.nights));
  return [...found.entries()].map(([id, one]) => ({
    id,
    lon: one.lon,
    lat: one.lat,
    kind: one.stay ? "stay" : "visit",
    size: Math.sqrt(one.nights / top),
  }));
}

export function routesOf(trips: Trip[]): MapRoute[] {
  const routes: MapRoute[] = [];
  for (const trip of trips) {
    legsAround(trip).forEach((leg, order) => {
      const { from_place: a, to_place: b } = leg;
      if (a.lon === null || a.lat === null || b.lon === null || b.lat === null) return;
      routes.push({ id: leg.id, group: trip.id, order, from: [a.lon, a.lat], to: [b.lon, b.lat], mode: leg.mode });
    });
  }
  return routes;
}

export function pointsOf(trip: Trip): [number, number][] {
  const points: [number, number][] = [];
  for (const place of [...trip.stays.map((one) => one.place), ...trip.visits.map((one) => one.place)]) {
    if (place.lon !== null && place.lat !== null) points.push([place.lon, place.lat]);
  }
  return points;
}

export interface Tallies {
  countries: number;
  regions: number;
  trips: number;
  nights: number;
  km: number;
}

export function talliesOf(trips: Trip[], others: OtherPlace[] = []): Tallies {
  const countries = new Set<string>();
  const regions = new Set<string>();
  const places = [
    ...trips.flatMap((trip) => [...trip.stays.map((one) => one.place), ...trip.visits.map((one) => one.place)]),
    ...others.map((one) => one.place),
  ];
  for (const place of places) {
    if (place.country_code) countries.add(place.country_code);
    if (place.region_code) regions.add(place.region_code);
  }
  return {
    countries: countries.size,
    regions: regions.size,
    trips: trips.length,
    nights: trips.reduce((sum, one) => sum + one.nights, 0),
    km: Math.round(trips.reduce((sum, one) => sum + one.km, 0)),
  };
}

export function insideArea(trips: Trip[], code: string, level: MapLevel, others: OtherPlace[] = []) {
  const codeOf = (place: Trip["stays"][number]["place"]) =>
    level === "region" ? place.region_code : place.country_code;
  const found: { trip: Trip; nights: number; places: string[] }[] = [];
  for (const trip of trips) {
    const stays = trip.stays.filter((one) => codeOf(one.place) === code);
    const visits = trip.visits.filter((one) => codeOf(one.place) === code);
    if (!stays.length && !visits.length) continue;
    found.push({
      trip,
      nights: stays.reduce((sum, one) => sum + one.nights, 0),
      places: [...new Set([...stays, ...visits].map((one) => one.place.name))],
    });
  }
  return {
    trips: found,
    nights: found.reduce((sum, one) => sum + one.nights, 0),
    places: [...new Set(found.flatMap((one) => one.places))],
    others: others.filter((one) => codeOf(one.place) === code),
  };
}

export function othersShown(others: OtherPlace[], filters: Filters, trips: Trip[]): OtherPlace[] {
  const [from, to] = yearSpan(trips);
  const everything = activeFilters(filters) === 0 && filters.years[0] <= from && filters.years[1] >= to;
  return everything ? others : [];
}

export function lived(trips: Trip[]): Trip[] {
  return trips.filter((one) => one.phase === "ongoing" || one.phase === "done");
}

export function ahead(trips: Trip[]): Trip[] {
  return trips
    .filter((one) => !one.archived && one.phase !== "done")
    .sort((a, b) => a.starts_on.localeCompare(b.starts_on));
}

export function listed(trips: Trip[]): Trip[] {
  return trips.filter((one) => !one.archived);
}

export function playOrder(trips: Trip[]): Trip[] {
  return [...trips].sort((a, b) => a.starts_on.localeCompare(b.starts_on));
}
