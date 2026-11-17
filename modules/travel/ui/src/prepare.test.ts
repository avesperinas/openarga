import { describe, expect, it } from "vitest";

import { boxAround, tileOf, tilesFor, documentsToKeep } from "./prepare";

describe("preparing a trip for offline use", () => {
  it("a point's tile is MapLibre's", () => {
    expect(tileOf(-1.6436, 42.8169, 14)).toEqual([8117, 6031]);
    expect(tileOf(0, 0, 0)).toEqual([0, 0]);
  });

  it("those of a box, without repeats, and the box with its margin", () => {
    const box = boxAround([[-1.6436, 42.8169], [-1.651, 42.8125]], 0)!;
    expect(box).toEqual([-1.651, 42.8125, -1.6436, 42.8169]);
    const tiles = tilesFor(box, [13, 14]);
    expect(new Set(tiles).size).toBe(tiles.length);
    expect(tiles).toContain("14/8117/6031");
    expect(boxAround([])).toBeNull();
  });
});

describe("the documents kept for offline use", () => {
  const paper = (id: string, size: number, created_at: string) => ({
    id,
    name: `${id}.pdf`,
    content_type: "application/pdf",
    size,
    created_at,
    mine: true,
    link: null,
  });

  it("keeps the latest up to the limit and skips the one that does not fit", () => {
    const kept = documentsToKeep(
      [paper("viejo", 40, "2027-01-01"), paper("grande", 80, "2027-02-01"), paper("nuevo", 30, "2027-03-01")],
      100,
    );

    expect(kept.map((one) => one.id)).toEqual(["nuevo", "viejo"]);
  });
});
