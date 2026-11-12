import {
  type GeoPath,
  type GeoPermissibleObjects,
  geoAzimuthalEquidistant,
  geoBounds,
  geoCentroid,
  geoDistance,
  geoGraticule,
  geoInterpolate,
  geoPath,
} from "d3-geo";
import type { Feature, Geometry, LineString, MultiLineString, Position } from "geojson";

export type RouteMode = "plane" | "train" | "car" | "bus" | "boat";

const LIFT: Record<RouteMode, number> = { plane: 0.22, train: 0.07, car: 0.06, bus: 0.06, boat: 0.1 };

export function routeArc(from: [number, number], to: [number, number], mode: RouteMode, steps = 48): LineString {
  const middle = geoInterpolate(from, to)(0.5);
  const plane = geoAzimuthalEquidistant()
    .rotate([-middle[0], -middle[1]])
    .scale(1000)
    .translate([0, 0]);
  const a = plane(from);
  const b = plane(to);
  if (!a || !b || !plane.invert) return { type: "LineString", coordinates: [] };
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
    const point = i === 0 ? from : i === steps ? to : plane.invert([x, y]);
    if (point) coordinates.push([round(point[0]), round(point[1])]);
  }
  return { type: "LineString", coordinates: unwrap(coordinates) };
}

function unwrap(points: Position[]): Position[] {
  const out: Position[] = [];
  for (const [lon, lat] of points) {
    const last = out[out.length - 1];
    let next = lon!;
    if (last) {
      while (next - last[0]! > 180) next -= 360;
      while (next - last[0]! < -180) next += 360;
    }
    out.push([next, lat!]);
  }
  return out;
}

const round = (value: number) => Math.round(value * 1e6) / 1e6;

export function distanceKm(from: [number, number], to: [number, number]): number {
  return geoDistance(from, to) * 6371;
}

export function graticuleLines(): MultiLineString {
  return geoGraticule()
    .step([10, 10])
    .extentMinor([
      [-180, -80],
      [180, 80.01],
    ])();
}

export function boundsOf(points: [number, number][]): [[number, number], [number, number]] | null {
  if (!points.length) return null;
  const lats = points.map(([, lat]) => lat);
  const lons = points.map(([lon]) => lon).sort((a, b) => a - b);
  let gap = 360 - (lons[lons.length - 1]! - lons[0]!);
  let west = lons[0]!;
  let east = lons[lons.length - 1]!;
  for (let i = 1; i < lons.length; i += 1) {
    const between = lons[i]! - lons[i - 1]!;
    if (between > gap) {
      gap = between;
      west = lons[i]!;
      east = lons[i - 1]! + 360;
    }
  }
  return [
    [west, Math.min(...lats)],
    [east, Math.max(...lats)],
  ];
}

export const EUROPE_VIEW: [number, number][] = [
  [-10.5, 35.5],
  [32, 35.5],
  [-10.5, 71],
  [32, 71],
];

export interface LocalView {
  project: (point: [number, number]) => [number, number] | null;
  path: GeoPath<unknown, GeoPermissibleObjects>;
  near: <T extends Feature<Geometry>>(features: T[]) => T[];
}

const MIN_SPAN_RAD = (0.5 * Math.PI) / 180;
const featureBounds = new WeakMap<object, [[number, number], [number, number]]>();

export function localView(points: [number, number][], width: number, height: number, pad: number): LocalView | null {
  if (!points.length) return null;
  const all = { type: "MultiPoint" as const, coordinates: points };
  const [clon, clat] = geoCentroid(all);
  const projection = geoAzimuthalEquidistant()
    .rotate([-clon, -clat])
    .clipAngle(90)
    .fitExtent(
      [
        [pad, pad],
        [width - pad, height - pad],
      ],
      all,
    );
  const most = (Math.min(width, height) - 2 * pad) / MIN_SPAN_RAD;
  if (!Number.isFinite(projection.scale()) || projection.scale() > most) {
    projection.scale(most).translate([width / 2, height / 2]);
  }
  projection.clipExtent([
    [0, 0],
    [width, height],
  ]);
  const reach = ((Math.hypot(width, height) / 2 / projection.scale()) * 180) / Math.PI + 1;
  const near = <T extends Feature<Geometry>>(features: T[]) =>
    features.filter((feature) => {
      let box = featureBounds.get(feature);
      if (!box) {
        box = geoBounds(feature) as [[number, number], [number, number]];
        featureBounds.set(feature, box);
      }
      const [[west, south], [east, north]] = box;
      if (south > clat + reach || north < clat - reach) return false;
      const span = reach / Math.max(0.05, Math.cos((clat * Math.PI) / 180));
      const length = west <= east ? east - west : east - west + 360;
      const start = ((west - clon + 540) % 360) - 180;
      return (start <= span && start + length >= -span) || start - 360 + length >= -span;
    });
  return {
    project: (point) => projection(point) as [number, number] | null,
    path: geoPath(projection),
    near,
  };
}
