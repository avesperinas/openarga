import { describe, expect, it } from "vitest";

import type { Layer, Occurrence } from "./api";
import { counts, duplicatesOf, shortName, sidebarGroups, similar, toGridEvent } from "./data";

const layer = (origin: Layer["origin"]): Layer => ({
  id: "l1",
  name: "Training",
  tone: 3,
  origin,
  visible: true,
  position: 0,
  connection_id: null,
  app: origin === "app" ? "training" : null,
});

const occurrence: Occurrence = {
  id: "app:1",
  event_id: "app:1",
  calendar_id: "l1",
  title: "Torso",
  all_day: false,
  start: "2026-10-06T18:00:00+02:00",
  end: "2026-10-06T19:00:00+02:00",
  tz: "Europe/Madrid",
  location: null,
  notes: null,
  url: null,
  status: "confirmed",
  original_start: null,
  rrule: null,
  repeat: null,
  moved: false,
  href: "/training/sesion/1",
};

describe("lo que viene de otra app", () => {
  it("no se arrastra si su app no deja moverlo desde aquí", () => {
    const event = toGridEvent(occurrence, layer("app"));

    expect(event.readOnly).toBe(true);
    expect(event.subscribed).toBe(false);
  });

  it("se arrastra si su app lo mueve (ADR-0085)", () => {
    expect(toGridEvent(occurrence, { ...layer("app"), movable: true }).readOnly).toBe(false);
  });

  it("lo suscrito nunca, aunque dijese que sí", () => {
    expect(toGridEvent(occurrence, { ...layer("subscription"), movable: true }).readOnly).toBe(true);
  });

  it("lo propio sí", () => {
    expect(toGridEvent(occurrence, layer("own")).readOnly).toBe(false);
  });
});

describe("una capa de fondo", () => {
  const background: Layer = { ...layer("own"), display: "background" };

  it("pinta lo suyo como fondo", () => {
    expect(toGridEvent(occurrence, background).background).toBe(true);
    expect(toGridEvent(occurrence, layer("own")).background).toBe(false);
  });

  it("lo que tiene hora no cuenta fuera de la rejilla, y lo de días enteros sí", () => {
    expect(counts(occurrence, background)).toBe(false);
    expect(counts({ ...occurrence, all_day: true, start: "2026-10-06", end: "2026-10-09" }, background)).toBe(true);
    expect(counts(occurrence, layer("own"))).toBe(true);
  });

  it("un servidor anterior no dice nada y son eventos", () => {
    expect(toGridEvent(occurrence, layer("app")).background).toBe(false);
  });
});

describe("la barra en grupos y lo mismo dos veces", () => {
  const layer = (id: string, name: string, origin: "own" | "subscription" | "app", extra: Record<string, unknown> = {}) =>
    ({ id, name, tone: 1, origin, visible: true, position: 0, connection_id: null, ...extra }) as never;
  const layers = [
    layer("p", "Personal", "own"),
    layer("t", "Trabajo", "own", { days_off_from: ["fc", "fl"] }),
    layer("fl", "Festivos · Local", "own"),
    layer("fc", "Festivos · Comunidad", "subscription", { subscription: { provider: "holidays" } }),
    layer("eq", "Equipo", "subscription", { subscription: { provider: "football" } }),
    layer("ca", "Carreras", "subscription", { subscription: { provider: "formula1" } }),
    layer("e1", "Travel · Plan", "app", { app: "travel:plan" }),
    layer("e2", "Travel · Trayectos", "app", { app: "travel:legs" }),
    layer("e3", "Travel · Viaje", "app", { app: "travel:trip" }),
    layer("r", "Training", "app", { app: "training" }),
  ];

  it("cuatro grupos, los festivos juntos y las apps por app", () => {
    const groups = sidebarGroups(layers);
    expect(groups.own.map((one: { name: string }) => one.name)).toEqual(["Personal", "Trabajo"]);
    expect(groups.holidays.map((one: { name: string }) => one.name)).toEqual(["Festivos · Local", "Festivos · Comunidad"]);
    expect(groups.subscriptions.map((one: { name: string }) => one.name)).toEqual(["Equipo", "Carreras"]);
    expect(groups.apps.map((one) => [one.name, one.layers.length])).toEqual([
      ["Travel", 3],
      ["Training", 1],
    ]);
    expect(groups.resting).toEqual(["Trabajo"]);
    expect(shortName(layers[6] as never, "Travel")).toBe("Plan");
  });

  it("lo tuyo a la misma hora y con título parecido a lo de una app es lo mismo", () => {
    const occurrence = (id: string, calendar_id: string, title: string, start = "2027-01-16T09:00:00+01:00") =>
      ({ id, event_id: id, calendar_id, title, all_day: false, start, end: "2027-01-16T13:30:00+01:00", status: "confirmed" }) as never;
    const found = duplicatesOf(
      [
        occurrence("mine", "p", "Museo (colección y jardines)"),
        occurrence("theirs", "e1", "Museo: colección permanente y jardines"),
        occurrence("lunch", "p", "Comida"),
        occurrence("later", "p", "Museo", "2027-01-16T10:00:00+01:00"),
      ],
      layers,
    );
    expect([...found.keys()]).toEqual(["mine"]);
    expect(similar("Tour por la sierra", "Tour organizado por la sierra")).toBe(true);
    expect(similar("Cena", "Comida")).toBe(false);
  });
});
