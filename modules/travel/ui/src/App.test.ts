import { describe, expect, it } from "vitest";

import { pathOf, route } from "./App";

const ID = "00000000-0000-4000-8000-000000000001";

describe("the routes", () => {
  it("Plans and Trips each have their own address", () => {
    expect(route("/travel/plans")).toEqual({ screen: "plans" });
    expect(route("/travel/trips")).toEqual({ screen: "trips" });
    expect(pathOf({ screen: "plans" })).toBe("/travel/plans");
    expect(route(pathOf({ screen: "plans" }))).toEqual({ screen: "plans" });
  });

  it("every screen goes back to its own route", () => {
    for (const to of [
      { screen: "trip", id: ID },
      { screen: "days", id: ID },
      { screen: "day", id: ID, day: "2026-11-15" },
      { screen: "money", id: ID },
      { screen: "tripsettings", id: ID },
      { screen: "tripapp", id: ID },
      { screen: "edit", id: ID },
      { screen: "edit", id: null },
      { screen: "settings" },
    ] as const) {
      expect(route(pathOf(to))).toEqual(to);
    }
  });

  it("the old Spanish addresses still open their screen", () => {
    expect(route("/travel/planes")).toEqual({ screen: "plans" });
    expect(route(`/travel/viajes/${ID}/dinero`)).toEqual({ screen: "money", id: ID });
    expect(route(`/travel/viajes/${ID}/ajustes`)).toEqual({ screen: "tripsettings", id: ID });
    expect(route(`/travel/viaje/${ID}`)).toEqual({ screen: "tripapp", id: ID });
    expect(route("/travel/ajustes")).toEqual({ screen: "settings" });
  });
});
