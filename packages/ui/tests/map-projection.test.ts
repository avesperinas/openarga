import { describe, expect, it } from "vitest";

import { boundsOf, graticule, projectCollection, projectPoint, routeLine, unprojectPoint } from "../src/map-projection";

describe("the conic projection disguised for MapLibre", () => {
  it("round trip: a projected point comes back to its place", () => {
    for (const [lon, lat] of [
      [3.2267, 51.2085],
      [-5.98, 37.39],
      [-74, 40.7],
      [139.7, 35.7],
    ] as [number, number][]) {
      const back = unprojectPoint(...projectPoint(lon, lat));
      expect(back?.[0]).toBeCloseTo(lon, 4);
      expect(back?.[1]).toBeCloseTo(lat, 4);
    }
  });

  it("north is up and east is to the right", () => {
    const [, oslo] = projectPoint(10.75, 59.91);
    const [, rome] = projectPoint(12.5, 41.9);
    const [lisbon] = projectPoint(-9.14, 38.72);
    const [athens] = projectPoint(23.73, 37.98);

    expect(oslo).toBeGreaterThan(rome);
    expect(athens).toBeGreaterThan(lisbon);
  });

  it("parallels curve: it is a conic and not Mercator", () => {
    const [, west] = projectPoint(-9.14, 38.72);
    const [, east] = projectPoint(37.14, 38.72);
    const [, middle] = projectPoint(14, 38.72);

    expect(middle).toBeLessThan(west);
    expect(middle).toBeLessThan(east);
    expect(west).toBeCloseTo(east, 3);
  });

  it("the whole world fits inside what MapLibre can draw", () => {
    for (const [lon, lat] of [
      [-165, -60],
      [165, -60],
      [0, 85],
      [-170, 70],
    ] as [number, number][]) {
      const [x, y] = projectPoint(lon, lat);
      expect(Math.abs(x)).toBeLessThan(180);
      expect(Math.abs(y)).toBeLessThan(85.06);
    }
  });

  it("a country crossing the conic's antimeridian is cut, it does not cross the map", () => {
    const strip = projectCollection({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { code: "XX" },
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [-170, 60],
                [-170, 65],
                [-160, 65],
                [-160, 60],
                [-170, 60],
              ],
            ],
          },
        },
      ],
    });

    const geometry = strip.features[0]!.geometry;
    expect(geometry.type).toBe("MultiPolygon");
  });

  it("the graticule and the outline exist and are real lines", () => {
    const { lines, outline } = graticule();

    expect(lines.coordinates.length).toBeGreaterThan(20);
    expect(["Polygon", "MultiPolygon"]).toContain(outline.type);
  });
});

describe("the routes", () => {
  const madrid: [number, number] = [-3.7, 40.42];
  const bruges: [number, number] = [3.23, 51.21];

  it("they start and end at their places", () => {
    const line = routeLine(madrid, bruges, "plane");

    expect(line.coordinates[0]).toEqual(projectPoint(...madrid));
    expect(line.coordinates.at(-1)).toEqual(projectPoint(...bruges));
  });

  it("the plane arcs higher than the train", () => {
    const middle = (mode: "plane" | "train") => routeLine(madrid, bruges, mode).coordinates[24]!;
    const straight = projectPoint((madrid[0] + bruges[0]) / 2, (madrid[1] + bruges[1]) / 2);
    const away = (p: number[]) => Math.hypot(p[0]! - straight[0], p[1]! - straight[1]);

    expect(away(middle("plane"))).toBeGreaterThan(away(middle("train")) * 2);
  });

  it("outbound and return do not overlap", () => {
    const there = routeLine(madrid, bruges, "train").coordinates[24]!;
    const back = routeLine(bruges, madrid, "train").coordinates[24]!;

    expect(there).not.toEqual(back);
  });

  it("the box of some points contains them", () => {
    const box = boundsOf([madrid, bruges])!;

    for (const point of [madrid, bruges]) {
      const [x, y] = projectPoint(...point);
      expect(x).toBeGreaterThanOrEqual(box[0][0]);
      expect(y).toBeLessThanOrEqual(box[1][1]);
    }
  });
});

describe("the real geometries", () => {
  it("every Natural Earth country projects whole and none crosses the map side to side", async () => {
    const { readFileSync } = await import("node:fs");
    const { feature } = await import("topojson-client");
    const topology = JSON.parse(readFileSync(new URL("../geo/countries.json", import.meta.url), "utf8"));
    const countries = projectCollection(feature(topology, topology.objects.countries) as never);

    const width = (code: string) => {
      const found = countries.features.find((one) => (one.properties as { code: string }).code === code)!;
      const xs = JSON.stringify(found.geometry)
        .match(/-?\d+\.?\d*(?=,-?\d)/g)!
        .map(Number);
      return Math.max(...xs) - Math.min(...xs);
    };

    expect(countries.features.length).toBeGreaterThan(230);
    expect(width("ES")).toBeLessThan(40);
    expect(width("FJ")).toBeLessThan(40);
    expect(width("RU")).toBeLessThan(200);
  });
});
