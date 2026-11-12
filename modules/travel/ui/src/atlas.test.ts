import { describe, expect, it } from "vitest";

import type { OtherPlace, Place, Trip } from "./api";
import {
  activeFilters,
  ahead,
  areasOf,
  drawn,
  insideArea,
  listed,
  lived,
  matches,
  noFilters,
  orderedLegs,
  othersShown,
  placesOf,
  playOrder,
  pointsOf,
  routesOf,
  talliesOf,
} from "./atlas";

const place = (id: string, name: string, country: string, region: string, lon = 3, lat = 51): Place => ({
  id,
  name,
  display_name: null,
  lat,
  lon,
  country_code: country,
  region_code: region,
  country: null,
  region: null,
  kind: null,
});

const BRUGES = place("p1", "Brujas", "BE", "BE-VLG", 3.23, 51.21);
const LILLE = place("p2", "Lille", "FR", "FR-HDF", 3.06, 50.63);
const ROME = place("p3", "Roma", "IT", "IT-62", 12.5, 41.9);
const HOME = place("p0", "Madrid", "ES", "ES-MD", -3.7, 40.42);

function trip(id: string, starts: string, extra: Partial<Trip> = {}): Trip {
  return {
    id,
    title: id,
    starts_on: starts,
    ends_on: starts,
    days: 1,
    nights: 0,
    travellers: 1,
    companions: [],
    tags: [],
    countries: [],
    km: 0,
    spend: { per_person: 0, group: 0, per_day: null, by_category: { transport: 0, lodging: 0, other: 0 } },
    source: "app",
    archived: false,
    status: "confirmed",
    phase: "done",
    space_id: null,
    mine: true,
    notes: null,
    stays: [],
    visits: [],
    legs: [],
    expenses: [],
    ...extra,
  };
}

const FLANDERS = trip("flandes", "2024-04-10", {
  nights: 4,
  km: 1400,
  companions: ["Ane"],
  tags: ["escapada"],
  stays: [{ id: "s1", place: BRUGES, arrives_on: "2024-04-10", leaves_on: "2024-04-14", nights: 4, accommodation: null }],
  visits: [{ id: "v1", place: LILLE, stay_id: "s1", visited_on: "2024-04-12", note: null }],
  legs: [
    { id: "l1", from_place: HOME, to_place: BRUGES, mode: "plane", travelled_on: "2024-04-10", km: 1300, note: null, on_map: null },
    { id: "l2", from_place: BRUGES, to_place: place("x", "Sin situar", "BE", "BE-VLG", 0, 0), mode: "car", travelled_on: null, km: null, note: null, on_map: null },
  ],
});
const ROMA = trip("roma", "2025-06-01", {
  nights: 2,
  stays: [{ id: "s2", place: ROME, arrives_on: "2025-06-01", leaves_on: "2025-06-03", nights: 2, accommodation: null }],
  legs: [{ id: "l3", from_place: HOME, to_place: ROME, mode: "train", travelled_on: null, km: 1500, note: null, on_map: null }],
});

describe("lo que se pinta", () => {
  it("todo lo visitado del mismo azul, dormido o de excursión, por país o por región", () => {
    expect(areasOf([FLANDERS], "country")).toEqual([
      { code: "BE", tone: "slept", weight: 1 },
      { code: "FR", tone: "slept", weight: 1 },
    ]);
    expect(areasOf([FLANDERS], "region").map((a) => a.code)).toEqual(["BE-VLG", "FR-HDF"]);
    expect(areasOf([FLANDERS], "none")).toEqual([]);
  });

  it("da igual cuántos viajes o noches: un área visitada pinta igual que otra", () => {
    const areas = areasOf([FLANDERS, ROMA, ROMA], "country");
    expect(new Set(areas.map((a) => `${a.tone}:${a.weight}`))).toEqual(new Set(["slept:1"]));
  });

  it("los lugares principales crecen con sus noches y los visitados van aparte", () => {
    const found = placesOf([FLANDERS, ROMA]);
    expect(found.find((p) => p.id === "p1")).toMatchObject({ kind: "stay", size: 1 });
    expect(found.find((p) => p.id === "p2")).toMatchObject({ kind: "visit" });
  });

  it("cada trayecto por el viaje es una ruta en su orden, sin la ida desde casa ni la vuelta", () => {
    const GHENT = place("p4", "Gante", "BE", "BE-VLG", 3.72, 51.05);
    const stays = [
      { id: "s1", place: BRUGES, arrives_on: "2024-04-10", leaves_on: "2024-04-12", nights: 2, accommodation: null },
      { id: "s2", place: GHENT, arrives_on: "2024-04-12", leaves_on: "2024-04-13", nights: 1, accommodation: null },
      { id: "s3", place: BRUGES, arrives_on: "2024-04-13", leaves_on: "2024-04-14", nights: 1, accommodation: null },
    ];
    const leg = (id: string, from: Place, to: Place, travelled_on: string | null = null) =>
      ({ id, from_place: from, to_place: to, mode: "train", travelled_on, km: null, note: null, on_map: null }) as const;
    const back = trip("vuelta", "2024-04-10", {
      stays,
      visits: [{ id: "v1", place: LILLE, stay_id: "s1", visited_on: "2024-04-11", note: null }],
      legs: [
        leg("vuelta", BRUGES, HOME),
        leg("gante-brujas", GHENT, BRUGES),
        leg("excursion", BRUGES, LILLE, "2024-04-11"),
        leg("brujas-gante", BRUGES, GHENT),
        leg("ida", HOME, BRUGES),
      ],
    });

    expect(orderedLegs(back).map((one) => one.id)).toEqual(["ida", "excursion", "brujas-gante", "gante-brujas", "vuelta"]);
    expect(routesOf([back]).map((r) => [r.id, r.order])).toEqual([
      ["excursion", 0],
      ["brujas-gante", 1],
      ["gante-brujas", 2],
    ]);
    expect(routesOf([FLANDERS])).toEqual([]);
    expect(pointsOf(FLANDERS)).not.toContainEqual([HOME.lon, HOME.lat]);
  });

  it("lo que se elige a mano manda sobre lo deducido: la vuelta que sale y un trayecto que no", () => {
    const GHENT = place("p4", "Gante", "BE", "BE-VLG", 3.72, 51.05);
    const leg = (id: string, from: Place, to: Place, on_map: boolean | null) =>
      ({ id, from_place: from, to_place: to, mode: "car", travelled_on: null, km: null, note: null, on_map }) as const;
    const chosen = trip("elegido", "2024-04-10", {
      stays: [
        { id: "s1", place: BRUGES, arrives_on: "2024-04-10", leaves_on: "2024-04-12", nights: 2, accommodation: null },
        { id: "s2", place: GHENT, arrives_on: "2024-04-12", leaves_on: "2024-04-14", nights: 2, accommodation: null },
      ],
      legs: [
        leg("ida", HOME, BRUGES, null),
        leg("brujas-gante", BRUGES, GHENT, false),
        leg("ultimo-dia", GHENT, LILLE, true),
      ],
    });

    expect(chosen.legs.map((one) => drawn(chosen, one))).toEqual([false, false, true]);
    expect(routesOf([chosen]).map((r) => r.id)).toEqual(["ultimo-dia"]);
  });

  it("las cifras suman lo filtrado", () => {
    expect(talliesOf([FLANDERS, ROMA])).toEqual({ countries: 3, regions: 3, trips: 2, nights: 6, km: 1400 });
  });
});

describe("los filtros", () => {
  it("de inicio abarcan todos los años y nada más", () => {
    const filters = noFilters([FLANDERS, ROMA]);
    expect(filters.years).toEqual([2024, 2025]);
    expect(activeFilters(filters)).toBe(0);
  });

  it("filtran por años, compañía, etiqueta y medio", () => {
    const all = noFilters([FLANDERS, ROMA]);
    expect(matches(ROMA, { ...all, years: [2024, 2024] })).toBe(false);
    expect(matches(FLANDERS, { ...all, companions: ["Ane"] })).toBe(true);
    expect(matches(ROMA, { ...all, companions: ["Ane"] })).toBe(false);
    expect(matches(ROMA, { ...all, modes: ["train"] })).toBe(true);
    expect(matches(FLANDERS, { ...all, tags: ["trabajo"] })).toBe(false);
  });

  it("reproducir va del primero al último", () => {
    expect(playOrder([ROMA, FLANDERS]).map((t) => t.id)).toEqual(["flandes", "roma"]);
  });
});

describe("el panel de un área", () => {
  it("dice sus viajes, sus noches y sus lugares", () => {
    const inside = insideArea([FLANDERS, ROMA], "BE", "country");
    expect(inside.trips.map((t) => t.trip.id)).toEqual(["flandes"]);
    expect(inside.nights).toBe(4);
    expect(inside.places).toEqual(["Brujas"]);
    expect(insideArea([FLANDERS], "FR-HDF", "region").nights).toBe(0);
  });
});

describe("los otros lugares, sin viaje", () => {
  const SEVILLE: OtherPlace = { id: "o1", place: place("p9", "Sevilla", "ES", "ES-AN", -5.98, 37.39), note: null, source: "app" };

  it("pintan del mismo color que un viaje y suman países y regiones, no viajes ni noches", () => {
    expect(areasOf([ROMA], "country", [SEVILLE])).toEqual([
      { code: "IT", tone: "slept", weight: 1 },
      { code: "ES", tone: "slept", weight: 1 },
    ]);
    expect(talliesOf([ROMA], [SEVILLE])).toEqual({ countries: 2, regions: 2, trips: 1, nights: 2, km: 0 });
  });

  it("salen en el panel de su área", () => {
    const inside = insideArea([ROMA], "ES-AN", "region", [SEVILLE]);
    expect(inside.trips).toEqual([]);
    expect(inside.others.map((one) => one.place.name)).toEqual(["Sevilla"]);
  });

  it("solo cuando se mira todo: sin fecha no se sabe si caen en unos años o en un viaje", () => {
    const all = noFilters([FLANDERS, ROMA]);
    expect(othersShown([SEVILLE], all, [FLANDERS, ROMA])).toEqual([SEVILLE]);
    expect(othersShown([SEVILLE], { ...all, years: [2025, 2025] }, [FLANDERS, ROMA])).toEqual([]);
    expect(othersShown([SEVILLE], { ...all, trip: "roma" }, [FLANDERS, ROMA])).toEqual([]);
  });
});

describe("los viajes archivados", () => {
  const OLD = trip("viejo", "2019-06-01", { archived: true, stays: FLANDERS.stays });

  it("no salen en la lista ni en el recorrido", () => {
    expect(listed([FLANDERS, OLD, ROMA]).map((one) => one.id)).toEqual([FLANDERS.id, ROMA.id]);
  });

  it("siguen pintando en el mapa y contando en las cifras", () => {
    expect(areasOf([OLD], "country")).toEqual([{ code: "BE", tone: "slept", weight: 1 }]);
    expect(talliesOf([OLD]).trips).toBe(1);
  });
});

describe("dónde vives", () => {
  it("pinta su país o su región de su color, aunque también hayas viajado por allí", () => {
    const home = place("h", "Amberes", "BE", "BE-VLG");
    expect(areasOf([FLANDERS], "country", [], home)).toEqual([
      { code: "FR", tone: "slept", weight: 1 },
      { code: "BE", tone: "home", weight: 0 },
    ]);
    expect(areasOf([], "region", [], HOME)).toEqual([{ code: "ES-MD", tone: "home", weight: 0 }]);
  });
});

describe("lo que viene y lo vivido", () => {
  it("el mapa solo ve lo empezado; la lista de lo que viene, del más cercano al más lejano", () => {
    const done = trip("done", "2025-04-10");
    const now = trip("now", "2026-10-01", { phase: "ongoing" });
    const later = trip("later", "2027-05-01", { status: "plan", phase: "plan" });
    const soon = trip("soon", "2026-12-01", { phase: "upcoming" });
    const hidden = trip("hidden", "2027-01-01", { phase: "upcoming", archived: true });

    expect(lived([done, now, later, soon]).map((one) => one.id)).toEqual(["done", "now"]);
    expect(ahead([done, later, soon, now, hidden]).map((one) => one.id)).toEqual(["now", "soon", "later"]);
  });
});
