import { describe, expect, it } from "vitest";

import { boundsOf, graticule, projectCollection, projectPoint, routeLine, unprojectPoint } from "../src/map-projection";

describe("la cónica disfrazada para MapLibre", () => {
  it("ida y vuelta: un punto proyectado vuelve a su sitio", () => {
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

  it("el norte queda arriba y el este a la derecha", () => {
    const [, oslo] = projectPoint(10.75, 59.91);
    const [, rome] = projectPoint(12.5, 41.9);
    const [lisbon] = projectPoint(-9.14, 38.72);
    const [athens] = projectPoint(23.73, 37.98);

    expect(oslo).toBeGreaterThan(rome);
    expect(athens).toBeGreaterThan(lisbon);
  });

  it("los paralelos se curvan: es una cónica y no Mercator", () => {
    const [, west] = projectPoint(-9.14, 38.72);
    const [, east] = projectPoint(37.14, 38.72);
    const [, middle] = projectPoint(14, 38.72);

    expect(middle).toBeLessThan(west);
    expect(middle).toBeLessThan(east);
    expect(west).toBeCloseTo(east, 3);
  });

  it("todo el mundo cabe dentro de lo que MapLibre sabe dibujar", () => {
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

  it("un país que cruza el antimeridiano de la cónica se corta, no atraviesa el mapa", () => {
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

  it("la retícula y el contorno existen y son líneas de verdad", () => {
    const { lines, outline } = graticule();

    expect(lines.coordinates.length).toBeGreaterThan(20);
    expect(["Polygon", "MultiPolygon"]).toContain(outline.type);
  });
});

describe("las rutas", () => {
  const madrid: [number, number] = [-3.7, 40.42];
  const bruges: [number, number] = [3.23, 51.21];

  it("empiezan y acaban en sus lugares", () => {
    const line = routeLine(madrid, bruges, "plane");

    expect(line.coordinates[0]).toEqual(projectPoint(...madrid));
    expect(line.coordinates.at(-1)).toEqual(projectPoint(...bruges));
  });

  it("el avión se levanta más que el tren", () => {
    const middle = (mode: "plane" | "train") => routeLine(madrid, bruges, mode).coordinates[24]!;
    const straight = projectPoint((madrid[0] + bruges[0]) / 2, (madrid[1] + bruges[1]) / 2);
    const away = (p: number[]) => Math.hypot(p[0]! - straight[0], p[1]! - straight[1]);

    expect(away(middle("plane"))).toBeGreaterThan(away(middle("train")) * 2);
  });

  it("la ida y la vuelta no se pisan", () => {
    const there = routeLine(madrid, bruges, "train").coordinates[24]!;
    const back = routeLine(bruges, madrid, "train").coordinates[24]!;

    expect(there).not.toEqual(back);
  });

  it("la caja de unos puntos los contiene", () => {
    const box = boundsOf([madrid, bruges])!;

    for (const point of [madrid, bruges]) {
      const [x, y] = projectPoint(...point);
      expect(x).toBeGreaterThanOrEqual(box[0][0]);
      expect(y).toBeLessThanOrEqual(box[1][1]);
    }
  });
});

describe("las geometrías de verdad", () => {
  it("cada país de Natural Earth se proyecta entero y ninguno cruza el mapa de lado a lado", async () => {
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
