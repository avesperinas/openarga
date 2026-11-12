import { describe, expect, it } from "vitest";

import { boundsOf, distanceKm, graticuleLines, routeArc } from "../src/globe";

const MADRID: [number, number] = [-3.7, 40.42];
const BRUGES: [number, number] = [3.23, 51.21];
const SANTIAGO: [number, number] = [-70.65, -33.45];
const TOKYO: [number, number] = [139.69, 35.69];
const HONOLULU: [number, number] = [-157.86, 21.31];

describe("las rutas en el globo", () => {
  it("empiezan y acaban en sus lugares, en cualquier parte del mundo", () => {
    for (const [from, to] of [
      [MADRID, BRUGES],
      [MADRID, SANTIAGO],
      [TOKYO, HONOLULU],
    ] as const) {
      const line = routeArc(from, to, "plane");
      expect(line.coordinates[0]).toEqual(from);
      const [lon, lat] = line.coordinates[line.coordinates.length - 1]!;
      expect(((lon! - to[0] + 540) % 360) - 180).toBeCloseTo(0, 4);
      expect(lat).toBeCloseTo(to[1], 4);
    }
  });

  it("cruzar el Pacífico va por el lado corto y no da la vuelta al mundo", () => {
    const line = routeArc(TOKYO, HONOLULU, "plane");
    const lons = line.coordinates.map(([lon]) => lon!);
    for (let i = 1; i < lons.length; i += 1) expect(Math.abs(lons[i]! - lons[i - 1]!)).toBeLessThan(10);
    expect(Math.max(...lons)).toBeGreaterThan(180);
  });

  it("el avión se levanta más que el tren, y la ida y la vuelta no se pisan", () => {
    const middle = (line: ReturnType<typeof routeArc>) => line.coordinates[24]!;
    const straight = [(MADRID[0] + BRUGES[0]) / 2, (MADRID[1] + BRUGES[1]) / 2];
    const off = (point: number[]) => Math.hypot(point[0]! - straight[0]!, point[1]! - straight[1]!);

    expect(off(middle(routeArc(MADRID, BRUGES, "plane")))).toBeGreaterThan(off(middle(routeArc(MADRID, BRUGES, "train"))));
    expect(middle(routeArc(MADRID, BRUGES, "plane"))).not.toEqual(middle(routeArc(BRUGES, MADRID, "plane")));
  });

  it("mide en kilómetros por la superficie", () => {
    expect(distanceKm(MADRID, BRUGES)).toBeGreaterThan(1300);
    expect(distanceKm(MADRID, BRUGES)).toBeLessThan(1400);
  });
});

describe("la caja de unos puntos", () => {
  it("los contiene", () => {
    expect(boundsOf([MADRID, BRUGES])).toEqual([
      [-3.7, 40.42],
      [3.23, 51.21],
    ]);
    expect(boundsOf([])).toBeNull();
  });

  it("a los dos lados del antimeridiano va por el lado corto", () => {
    const [[west], [east]] = boundsOf([TOKYO, HONOLULU])!;
    expect(west).toBe(139.69);
    expect(east).toBeCloseTo(-157.86 + 360, 6);
  });
});

it("la retícula son líneas de verdad", () => {
  expect(graticuleLines().coordinates.length).toBeGreaterThan(30);
});
