import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { VIEWS, bilingual, pointFeatures } from "../src/area-map";

describe("el mapa de la comarca", () => {
  it("dice los nombres en los dos idiomas donde OpenStreetMap los tiene: «Pamplona / Iruña»", () => {
    const expression = JSON.stringify(bilingual("gris"));

    expect(expression).toContain('"index-of"," / "');
    expect(expression).toContain('"font-scale":0.8');
    expect(expression).toContain('"text-color":"gris"');
  });

  it("la vista de la comarca cae dentro del extracto de calles más detallado", () => {
    const [[west, south], [east, north]] = VIEWS.comarca;
    expect(west).toBeGreaterThan(-1.82);
    expect(south).toBeGreaterThan(42.7);
    expect(east).toBeLessThan(-1.47);
    expect(north).toBeLessThan(42.93);
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
