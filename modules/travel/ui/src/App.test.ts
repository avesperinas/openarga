import { describe, expect, it } from "vitest";

import { pathOf, route } from "./App";

describe("las pestañas de la lista", () => {
  it("Planes y Viajes tienen cada una su dirección", () => {
    expect(route("/travel/planes")).toEqual({ screen: "plans" });
    expect(route("/travel/viajes")).toEqual({ screen: "trips" });
    expect(pathOf({ screen: "plans" })).toBe("/travel/planes");
    expect(route(pathOf({ screen: "plans" }))).toEqual({ screen: "plans" });
  });
});
