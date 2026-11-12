import { describe, expect, it } from "vitest";

import type { Block, Itinerary } from "./api";
import { blocksOf, moved, stepped } from "./reorder";

const block = (id: string, day: string | null): Block => ({
  id,
  day,
  position: 0,
  kind: "activity",
  title: id,
  starts_at: null,
  ends_at: null,
  place: null,
  visit_id: null,
  notes: null,
  mine: true,
});

const ITINERARY: Itinerary = {
  trip_id: "t",
  title: "Flandes",
  days: [
    {
      day: "2025-04-10",
      number: 1,
      sleeping: null,
      items: ["a", "b"].map((id) => ({ type: "block", stay: null, leg: null, block: block(id, "2025-04-10") })),
    },
    {
      day: "2025-04-11",
      number: 2,
      sleeping: null,
      items: [{ type: "block", stay: null, leg: null, block: block("c", "2025-04-11") }],
    },
  ],
  unscheduled: [block("d", null)],
};

const ids = (itinerary: Itinerary, slot: string | null) => blocksOf(itinerary, slot).map((one) => one.id);

describe("arrastrar en el itinerario", () => {
  it("soltar en otro día lo saca del suyo y lo pone en su puesto", () => {
    const after = moved(ITINERARY, "a", "2025-04-11", 1);
    expect(ids(after, "2025-04-10")).toEqual(["b"]);
    expect(ids(after, "2025-04-11")).toEqual(["c", "a"]);
    expect(blocksOf(after, "2025-04-11")[1]!.day).toBe("2025-04-11");
  });

  it("dentro del mismo día cuenta sin él, y a sin día también vale", () => {
    expect(ids(moved(ITINERARY, "a", "2025-04-10", 1), "2025-04-10")).toEqual(["b", "a"]);
    expect(ids(moved(ITINERARY, "c", null, 0), null)).toEqual(["c", "d"]);
  });

  it("lo que no es un bloque se queda en su sitio entre los bloques", () => {
    const leaving = { type: "check_out" as const, stay: null, leg: null, block: null };
    const withStay: Itinerary = {
      ...ITINERARY,
      days: [
        {
          ...ITINERARY.days[0]!,
          items: [ITINERARY.days[0]!.items[0]!, leaving, ITINERARY.days[0]!.items[1]!],
        },
        ITINERARY.days[1]!,
      ],
    };
    const after = moved(withStay, "a", "2025-04-10", 1);
    expect(after.days[0]!.items.map((item) => item.block?.id ?? item.type)).toEqual(["b", "check_out", "a"]);
  });

  it("con las flechas, al acabar un día pasa al siguiente o al anterior", () => {
    expect(stepped(ITINERARY, "a", 1)).toEqual({ slot: "2025-04-10", index: 1 });
    expect(stepped(ITINERARY, "b", 1)).toEqual({ slot: "2025-04-11", index: 0 });
    expect(stepped(ITINERARY, "c", -1)).toEqual({ slot: "2025-04-10", index: 2 });
    expect(stepped(ITINERARY, "a", -1)).toBeNull();
  });
});
