import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { VIEWS, bilingual, maxBoundsOf, pointFeatures, zoneOf } from "../src/area-map";

describe("el mapa de la comarca", () => {
  it("dice los nombres en los dos idiomas donde OpenStreetMap los tiene: «Pamplona / Iruña»", () => {
    const expression = JSON.stringify(bilingual("gris"));

    expect(expression).toContain('"index-of"," / "');
    expect(expression).toContain('"font-scale":0.8');
    expect(expression).toContain('"text-color":"gris"');
  });

  it("la vista de la comarca cae dentro del extracto de calles más detallado", () => {
    const [[west, south], [east, north]] = VIEWS.near;
    expect(west).toBeGreaterThan(-1.82);
    expect(south).toBeGreaterThan(42.7);
    expect(east).toBeLessThan(-1.47);
    expect(north).toBeLessThan(42.93);
  });

  it("takes the old view names as the profile's zones", () => {
    expect(zoneOf("comarca")).toBe("near");
    expect(zoneOf("navarra")).toBe("region");
    expect(zoneOf("region")).toBe("region");
  });

  it("lets the map move half a region around the region and no further", () => {
    const [[west, south], [east, north]] = maxBoundsOf([
      [11, 47.6],
      [12.2, 48.4],
    ]);
    expect([west, south, east, north].map((value) => Number(value.toFixed(6)))).toEqual([10.4, 47, 12.8, 49]);
  });

  it("cada punto viaja con su id para agruparse", () => {
    const features = pointFeatures([{ id: "a", lon: -1.64, lat: 42.81, kind: "pill", hue: 5, title: "x", label: "Sáb 3" }]);

    expect(features.features[0]).toEqual({
      type: "Feature",
      properties: { id: "a" },
      geometry: { type: "Point", coordinates: [-1.64, 42.81] },
    });
  });

  it("ningún color escrito en el componente: todos salen de `--area-map-*`", () => {
    const source = readFileSync(new URL("../src/area-map.tsx", import.meta.url), "utf8");

    expect(source).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(source).not.toMatch(/\brgba?\(/);
  });
});
