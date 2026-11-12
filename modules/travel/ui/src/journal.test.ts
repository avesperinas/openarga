import { describe, expect, it } from "vitest";

import { daysSoFar, withDay } from "./Journal";

const TRIP = { starts_on: "2026-05-01", ends_on: "2026-05-04" };

describe("los días del diario", () => {
  it("los que ya han llegado, del último al primero", () => {
    expect(daysSoFar(TRIP, "2026-05-02")).toEqual(["2026-05-02", "2026-05-01"]);
    expect(daysSoFar(TRIP, "2026-06-01")).toEqual(["2026-05-04", "2026-05-03", "2026-05-02", "2026-05-01"]);
  });

  it("antes de salir, ninguno", () => {
    expect(daysSoFar(TRIP, "2026-04-30")).toEqual([]);
  });
});

describe("lo escrito, pintado antes de que conteste el servidor", () => {
  const entry = { id: "a", trip_id: "t", day: "2026-05-02", body: "Tranvía.", updated_at: "" };

  it("pone el día entero y en su orden", () => {
    const found = withDay([entry], "t", "2026-05-01", " Llegada. ");
    expect(found.map((one) => [one.day, one.body])).toEqual([
      ["2026-05-01", "Llegada."],
      ["2026-05-02", "Tranvía."],
    ]);
    expect(withDay([entry], "t", "2026-05-02", "Otro.")[0]).toMatchObject({ id: "a", body: "Otro." });
  });

  it("vacío lo quita", () => {
    expect(withDay([entry], "t", "2026-05-02", "  ")).toEqual([]);
  });
});
