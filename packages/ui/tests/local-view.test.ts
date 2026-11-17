import type { Feature, Polygon } from "geojson";
import { describe, expect, it } from "vitest";

import { localView } from "../src/globe";

const square = (code: string, lon: number, lat: number, side = 2): Feature<Polygon, { code: string }> => ({
  type: "Feature",
  properties: { code },
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [lon, lat],
        [lon, lat + side],
        [lon + side, lat + side],
        [lon + side, lat],
        [lon, lat],
      ],
    ],
  },
});

describe("a trip's small map", () => {
  it("fits its points inside the box, with a margin", () => {
    const view = localView(
      [
        [3.23, 51.21],
        [3.72, 51.05],
        [4.4, 51.22],
      ],
      120,
      80,
      10,
    )!;
    for (const point of [
      [3.23, 51.21],
      [4.4, 51.22],
    ] as [number, number][]) {
      const [x, y] = view.project(point)!;
      expect(x).toBeGreaterThanOrEqual(9.5);
      expect(x).toBeLessThanOrEqual(110.5);
      expect(y).toBeGreaterThanOrEqual(9.5);
      expect(y).toBeLessThanOrEqual(70.5);
    }
  });

  it("a single place stays in the centre, without zooming to street level", () => {
    const view = localView([[2.35, 48.86]], 120, 80, 10)!;
    expect(view.project([2.35, 48.86])).toEqual([60, 40]);
    const [x] = view.project([2.85, 48.86])!;
    expect(x - 60).toBeLessThan(100);
  });

  it("draws the surrounding countries and leaves out those on the other side of the world", () => {
    const view = localView([[3.23, 51.21]], 120, 80, 10)!;
    const belgium = square("BE", 2.5, 49.5);
    const chile = square("CL", -72, -35);
    const fiji = square("FJ", 179, -18);

    expect(view.near([belgium, chile, fiji]).map((one) => one.properties.code)).toEqual(["BE"]);
    expect(view.path(belgium)).toMatch(/^M/);
  });

  it("next to the antimeridian it sees both sides", () => {
    const view = localView([[179.5, -17.8]], 120, 80, 10)!;
    const east = square("A", 178.5, -18.5);
    const west = square("B", -180, -18.5);
    expect(view.near([east, west]).map((one) => one.properties.code)).toEqual(["A", "B"]);
  });
});
