import { describe, expect, it } from "vitest";

import { daysSoFar, withDay } from "./Journal";

const TRIP = { starts_on: "2026-05-01", ends_on: "2026-05-04" };

describe("the journal's days", () => {
  it("those that have come, from the last to the first", () => {
    expect(daysSoFar(TRIP, "2026-05-02")).toEqual(["2026-05-02", "2026-05-01"]);
    expect(daysSoFar(TRIP, "2026-06-01")).toEqual(["2026-05-04", "2026-05-03", "2026-05-02", "2026-05-01"]);
  });

  it("before leaving, none", () => {
    expect(daysSoFar(TRIP, "2026-04-30")).toEqual([]);
  });
});

describe("what is written, drawn before the server answers", () => {
  const entry = { id: "a", trip_id: "t", day: "2026-05-02", body: "Tram.", updated_at: "" };

  it("puts the whole day and in its order", () => {
    const found = withDay([entry], "t", "2026-05-01", " Llegada. ");
    expect(found.map((one) => [one.day, one.body])).toEqual([
      ["2026-05-01", "Llegada."],
      ["2026-05-02", "Tram."],
    ]);
    expect(withDay([entry], "t", "2026-05-02", "Otro.")[0]).toMatchObject({ id: "a", body: "Otro." });
  });

  it("empty removes it", () => {
    expect(withDay([entry], "t", "2026-05-02", "  ")).toEqual([]);
  });
});
