import { describe, expect, it } from "vitest";

import { boxAround, tileOf, tilesFor, documentsToKeep } from "./prepare";

describe("preparar un viaje sin conexión", () => {
  it("la tesela de un punto es la de MapLibre", () => {
    expect(tileOf(-1.6436, 42.8169, 14)).toEqual([8117, 6031]);
    expect(tileOf(0, 0, 0)).toEqual([0, 0]);
  });

  it("las de una caja, sin repetir, y la caja con su margen", () => {
    const box = boxAround([[-1.6436, 42.8169], [-1.651, 42.8125]], 0)!;
    expect(box).toEqual([-1.651, 42.8125, -1.6436, 42.8169]);
    const tiles = tilesFor(box, [13, 14]);
    expect(new Set(tiles).size).toBe(tiles.length);
    expect(tiles).toContain("14/8117/6031");
    expect(boxAround([])).toBeNull();
  });
});

describe("los documentos que se guardan sin red", () => {
  const paper = (id: string, size: number, created_at: string) => ({
    id,
    name: `${id}.pdf`,
    content_type: "application/pdf",
    size,
    created_at,
    mine: true,
    link: null,
  });

  it("guarda los más recientes hasta el tope y salta el que no cabe", () => {
    const kept = documentsToKeep(
      [paper("viejo", 40, "2027-01-01"), paper("grande", 80, "2027-02-01"), paper("nuevo", 30, "2027-03-01")],
      100,
    );

    expect(kept.map((one) => one.id)).toEqual(["nuevo", "viejo"]);
  });
});
