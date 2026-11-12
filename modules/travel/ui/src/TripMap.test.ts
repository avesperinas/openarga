import { describe, expect, it } from "vitest";

import type { Block, Itinerary, Stay } from "./api";
import { savedKinds, savedStops, tripStops } from "./TripMap";
import { dayHue } from "./words";

const place = (name: string, lat: number | null, lon: number | null) => ({
  id: name,
  name,
  display_name: null,
  lat,
  lon,
  country_code: "HU",
  region_code: null,
  country: null,
  region: null,
  kind: null,
});

const block = (id: string, day: string, lat: number | null): Block => ({
  id,
  day,
  position: 0,
  kind: "activity",
  title: id,
  starts_at: null,
  ends_at: null,
  place: place(id, lat, lat === null ? null : 19),
  visit_id: null,
  notes: null,
  mine: true,
});

const hotel = {
  id: "h",
  place: place("Budapest", 47.5, 19.04),
  arrives_on: "2027-11-11",
  leaves_on: "2027-11-13",
  nights: 2,
  accommodation: "Hotel",
} as Stay;

const TRIP: Itinerary = {
  trip_id: "t",
  title: "Budapest",
  days: [
    {
      day: "2027-11-11",
      number: 1,
      sleeping: hotel,
      items: [
        { type: "check_in", stay: hotel, leg: null, block: null },
        { type: "block", stay: null, leg: null, block: block("Parlamento", "2027-11-11", 47.507) },
        { type: "block", stay: null, leg: null, block: block("Sin sitio", "2027-11-11", null) },
      ],
    },
    {
      day: "2027-11-12",
      number: 2,
      sleeping: hotel,
      items: [{ type: "block", stay: null, leg: null, block: block("Termas", "2027-11-12", 47.518) }],
    },
  ],
  unscheduled: [],
};

describe("el mapa del viaje", () => {
  it("cada día en su color, lo que tiene lugar numerado y el alojamiento una vez", () => {
    const stops = tripStops(TRIP);
    expect(stops.map((one) => [one.title, one.number, one.hue])).toEqual([
      ["Hotel", null, dayHue(1)],
      ["Parlamento", 1, dayHue(1)],
      ["Termas", 1, dayHue(2)],
    ]);
  });

  it("los colores de los días no repiten hasta el octavo y nunca son el gris", () => {
    const hues = Array.from({ length: 7 }, (_, index) => dayHue(index + 1));
    expect(new Set(hues).size).toBe(7);
    expect(dayHue(8)).toBe(dayHue(1));
    expect(hues).not.toContain(8);
  });
});

describe("los sitios guardados", () => {
  const saved = (id: string, category: "beach" | "restaurant" | null): Block => ({
    ...block(id, "", 39.6),
    day: null,
    place: { ...place(id, 39.6, 19.8), category },
  });
  const WITH_SAVED: Itinerary = { ...TRIP, unscheduled: [saved("Glyfada", "beach"), saved("Taverna", "restaurant"), saved("Algo", null)] };

  it("salen como marcas pequeñas en el color de su tipo, y se filtran por tipo", () => {
    expect(savedStops(WITH_SAVED).map((one) => [one.title, one.quiet, one.hue])).toEqual([
      ["Glyfada", true, 6],
      ["Taverna", true, 4],
      ["Algo", true, 8],
    ]);
    expect(savedStops(WITH_SAVED, "beach").map((one) => one.title)).toEqual(["Glyfada"]);
  });

  it("los tipos con cuántos hay, en el orden de la lista y sin tipo como otro", () => {
    expect(savedKinds(WITH_SAVED)).toEqual([
      { category: "restaurant", count: 1 },
      { category: "beach", count: 1 },
      { category: "other", count: 1 },
    ]);
  });
});
