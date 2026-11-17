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

describe("a trip's app", () => {
  it("its address leads to the trip, there and back", () => {
    expect(tripOfPath(`/travel/viaje/${ID}`)).toBe(ID);
    expect(tripOfPath(`/travel/viajes/${ID}`)).toBeNull();
    expect(route(pathOf({ screen: "tripapp", id: ID }))).toEqual({ screen: "tripapp", id: ID });
  });

  it("in the browser you are in the trip only while you are at its address", () => {
    expect(lockedTrip(`/travel/viaje/${ID}`, false)).toBe(ID);
    expect(lockedTrip(`/travel/viajes/${ID}/dias`, false)).toBeNull();
  });

  it("installed, it stays in the trip the app started with", () => {
    expect(lockedTrip("/travel/viajes", true, `/travel/viaje/${ID}`)).toBe(ID);
  });

  it("the Travel app is not locked in a trip for having opened its page", () => {
    expect(lockedTrip(`/travel/viaje/${ID}`, true, "/travel/")).toBe(ID);
    expect(lockedTrip("/travel/viajes", true, "/travel/")).toBeNull();
    expect(lockedTrip("/travel/", true, "/travel/")).toBeNull();
  });

  it("what the previous version left stored locks nobody in", () => {
    localStorage.setItem("travel.trip-app", ID);
    forgetStoredLock();
    expect(localStorage.getItem("travel.trip-app")).toBeNull();
    expect(lockedTrip("/travel/viajes", true, "/travel/")).toBeNull();
  });

  it("the icon's initials skip the small words", () => {
    expect(initials("Japan in sakura")).toBe("JS");
    expect(initials("Budapest")).toBe("B");
    expect(initials("The road of the castles")).toBe("RC");
  });
});
