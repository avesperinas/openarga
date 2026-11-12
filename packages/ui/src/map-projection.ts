// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="./d3-geo-projection.d.ts" />
import { geoConicEqualArea, geoGraticule, geoPath } from "d3-geo";
import { geoProject } from "d3-geo-projection";
import type { Feature, FeatureCollection, Geometry, LineString, MultiLineString, Position } from "geojson";

const CONIC = geoConicEqualArea()
  .parallels([38, 62])
  .rotate([-14, 0])
  .scale(1000)
  .translate([0, 0])
  .precision(0.3);

const SPHERE = { type: "Sphere" } as const;
const [[x0, y0], [x1, y1]] = geoPath(CONIC).bounds(SPHERE as never);
const SPAN = Math.max(x1 - x0, y1 - y0);
const MARGIN = 0.04;
const FIT = (1 - 2 * MARGIN) / SPAN;
const CX = (x0 + x1) / 2;
const CY = (y0 + y1) / 2;

function disguise(x: number, y: number): [number, number] {
  const u = 0.5 + (x - CX) * FIT;
  const v = 0.5 + (y - CY) * FIT;
  const lon = u * 360 - 180;
  const lat = (Math.atan(Math.sinh(Math.PI * (1 - 2 * v))) * 180) / Math.PI;
  return [round(lon), round(lat)];
}

function reveal(lon: number, lat: number): [number, number] {
  const u = (lon + 180) / 360;
  const v = (1 - Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) / Math.PI) / 2;
  return [(u - 0.5) / FIT + CX, (v - 0.5) / FIT + CY];
}

const round = (value: number) => Math.round(value * 1e6) / 1e6;

export function projectPoint(lon: number, lat: number): [number, number] {
  const projected = CONIC([lon, lat]);
  if (!projected) return [0, 0];
  return disguise(projected[0], projected[1]);
}

export function unprojectPoint(lon: number, lat: number): [number, number] | null {
  const [x, y] = reveal(lon, lat);
  const found = CONIC.invert?.([x, y]);
  return found ? [found[0], found[1]] : null;
}

function mapPositions(geometry: Geometry, change: (p: Position) => Position): Geometry {
  switch (geometry.type) {
    case "Point":
      return { ...geometry, coordinates: change(geometry.coordinates) };
    case "MultiPoint":
    case "LineString":
      return { ...geometry, coordinates: geometry.coordinates.map(change) };
    case "MultiLineString":
    case "Polygon":
      return { ...geometry, coordinates: geometry.coordinates.map((line) => line.map(change)) };
    case "MultiPolygon":
      return {
        ...geometry,
        coordinates: geometry.coordinates.map((polygon) => polygon.map((ring) => ring.map(change))),
      };
    case "GeometryCollection":
      return { ...geometry, geometries: geometry.geometries.map((one) => mapPositions(one, change)) };
  }
}

export function projectCollection<P>(collection: FeatureCollection<Geometry, P>): FeatureCollection<Geometry, P> {
  const projected = geoProject(collection, CONIC) as FeatureCollection<Geometry | null, P>;
  const features: Feature<Geometry, P>[] = [];
  for (const feature of projected.features) {
    if (!feature.geometry) continue;
    features.push({
      ...feature,
      geometry: mapPositions(feature.geometry, ([x, y]) => disguise(x ?? 0, y ?? 0)),
    });
  }
  return { type: "FeatureCollection", features };
}

export function graticule(): { lines: MultiLineString; outline: Geometry } {
  const maker = geoGraticule().step([10, 10]).extentMinor([
    [-180, -80],
    [180, 80.01],
  ]);
  const edge = geoGraticule().extentMajor([
    [-180, -89.99],
    [180, 89.99],
  ]);
  const lines = projectCollection({
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: {}, geometry: maker() }],
  }).features[0]?.geometry as MultiLineString;
  const outline = projectCollection({
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: {}, geometry: edge.outline() }],
  }).features[0]?.geometry as Geometry;
  return { lines, outline };
}

export type RouteMode = "plane" | "train" | "car" | "bus" | "boat";

const LIFT: Record<RouteMode, number> = { plane: 0.22, train: 0.07, car: 0.06, bus: 0.06, boat: 0.1 };

export function routeLine(from: [number, number], to: [number, number], mode: RouteMode, steps = 48): LineString {
  const a = CONIC(from);
  const b = CONIC(to);
  if (!a || !b) return { type: "LineString", coordinates: [] };
  const [ax, ay] = a;
  const [bx, by] = b;
  const dx = bx - ax;
  const dy = by - ay;
  const length = Math.hypot(dx, dy);
  const nx = length ? dy / length : 0;
  const ny = length ? -dx / length : 0;
  const lift = LIFT[mode] * length;
  const cx = (ax + bx) / 2 + nx * lift;
  const cy = (ay + by) / 2 + ny * lift;
  const coordinates: Position[] = [];
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps;
    const x = (1 - t) ** 2 * ax + 2 * (1 - t) * t * cx + t ** 2 * bx;
    const y = (1 - t) ** 2 * ay + 2 * (1 - t) * t * cy + t ** 2 * by;
    coordinates.push(disguise(x, y));
  }
  return { type: "LineString", coordinates };
}

export function boundsOf(points: [number, number][]): [[number, number], [number, number]] | null {
  if (!points.length) return null;
  const projected = points.map(([lon, lat]) => projectPoint(lon, lat));
  const lons = projected.map(([lon]) => lon);
  const lats = projected.map(([, lat]) => lat);
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ];
}

export const EUROPE_VIEW: [number, number][] = [
  [-10.5, 35.5],
  [32, 35.5],
  [-10.5, 71],
  [32, 71],
  [14, 34],
  [14, 71.5],
];
