import { describe, expect, it } from "vitest";

import { route, pathOf } from "./App";
import { forgetStoredLock, initials, lockedTrip, tripOfPath } from "./tripApp";

const ID = "3abfed4f-8cde-44ad-b81a-d0039f5a2ba6";

const memory = new Map<string, string>();
globalThis.localStorage = {
  getItem: (key: string) => memory.get(key) ?? null,
  setItem: (key: string, value: string) => void memory.set(key, value),
  removeItem: (key: string) => void memory.delete(key),
  clear: () => memory.clear(),
  key: () => null,
  length: 0,
} as Storage;

describe("la app de un viaje", () => {
  it("su dirección lleva al viaje, de ida y de vuelta", () => {
    expect(tripOfPath(`/travel/viaje/${ID}`)).toBe(ID);
    expect(tripOfPath(`/travel/viajes/${ID}`)).toBeNull();
    expect(route(pathOf({ screen: "tripapp", id: ID }))).toEqual({ screen: "tripapp", id: ID });
  });

  it("en el navegador solo se está en el viaje mientras se está en su dirección", () => {
    expect(lockedTrip(`/travel/viaje/${ID}`, false)).toBe(ID);
    expect(lockedTrip(`/travel/viajes/${ID}/dias`, false)).toBeNull();
  });

  it("instalada, se sigue en el viaje con el que arrancó la app", () => {
    expect(lockedTrip("/travel/viajes", true, `/travel/viaje/${ID}`)).toBe(ID);
  });

  it("la app de Travel no se queda encerrada en un viaje por haber entrado en su página", () => {
    expect(lockedTrip(`/travel/viaje/${ID}`, true, "/travel/")).toBe(ID);
    expect(lockedTrip("/travel/viajes", true, "/travel/")).toBeNull();
    expect(lockedTrip("/travel/", true, "/travel/")).toBeNull();
  });

  it("lo que dejó guardado la versión anterior no encierra a nadie", () => {
    localStorage.setItem("travel.trip-app", ID);
    forgetStoredLock();
    expect(localStorage.getItem("travel.trip-app")).toBeNull();
    expect(lockedTrip("/travel/viajes", true, "/travel/")).toBeNull();
  });

  it("las iniciales del icono saltan las palabras pequeñas", () => {
    expect(initials("Japón en sakura")).toBe("JS");
    expect(initials("Budapest")).toBe("B");
    expect(initials("La ruta de los castillos")).toBe("RC");
  });
});
