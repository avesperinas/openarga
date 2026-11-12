// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="./d3-geo-projection.d.ts" />
import "maplibre-gl/dist/maplibre-gl.css";

import type { FeatureCollection, Geometry } from "geojson";
import * as maplibre from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { Protocol } from "pmtiles";
import * as React from "react";
import { createRoot, type Root } from "react-dom/client";
import { feature as topoFeature } from "topojson-client";

import { Icon, type IconName } from "./icons";

export type AreaView = "comarca" | "navarra";

export interface AreaPoint {
  id: string;
  lon: number;
  lat: number;
  kind: "photo" | "pill";
  image?: string;
  icon?: IconName;
  hue: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;
  label?: string;
  title: string;
}

export interface AreaMapProps {
  base: string;
  view: AreaView;
  points: AreaPoint[];
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  label: string;
  center?: [number, number] | null;
  compact?: boolean;
}

export const VIEWS: Record<AreaView, [[number, number], [number, number]]> = {
  comarca: [
    [-1.76, 42.74],
    [-1.52, 42.88],
  ],
  navarra: [
    [-2.5, 41.91],
    [-0.72, 43.32],
  ],
};

maplibre.setWorkerUrl(workerUrl);

let protocolReady = false;
function ensurePmtiles(): void {
  if (protocolReady) return;
  const protocol = new Protocol();
  maplibre.addProtocol("pmtiles", protocol.tile);
  protocolReady = true;
}

const TOKENS = [
  "paper",
  "contour",
  "contour-bold",
  "park",
  "water",
  "river",
  "arga",
  "road",
  "road-edge",
  "road-major",
  "building",
  "boundary",
  "label",
  "label-muted",
  "label-water",
  "label-relief",
  "halo",
] as const;

export type AreaPalette = Record<(typeof TOKENS)[number], string>;

export function readAreaPalette(element: Element): AreaPalette {
  const style = getComputedStyle(element);
  return Object.fromEntries(
    TOKENS.map((token) => [token, style.getPropertyValue(`--area-map-${token}`).trim() || "transparent"]),
  ) as AreaPalette;
}

type Piece = "navarra" | "comarca";
const REGULAR = ["Noto Sans Regular"];
const MEDIUM = ["Noto Sans Medium"];
const ITALIC = ["Noto Sans Italic"];

export function bilingual(muted: string): maplibre.ExpressionSpecification {
  const name: maplibre.ExpressionSpecification = ["coalesce", ["get", "name"], ""];
  const cut: maplibre.ExpressionSpecification = ["index-of", " / ", name];
  return [
    "case",
    [">=", cut, 0],
    [
      "format",
      ["slice", name, 0, cut],
      {},
      "\n",
      {},
      ["slice", name, ["+", cut, 3]],
      { "font-scale": 0.8, "text-color": muted },
    ],
    name,
  ];
}

const ARGA: maplibre.ExpressionSpecification = ["in", "Arga", ["coalesce", ["get", "name"], ""]];

export function streetLayers(source: Piece | string, palette: AreaPalette): maplibre.LayerSpecification[] {
  const id = (name: string) => `${source}-${name}`;
  const roads = (kinds: string[]): maplibre.FilterSpecification => [
    "all",
    ["in", ["get", "kind"], ["literal", kinds]],
    ["!=", ["get", "is_tunnel"], true],
  ];
  return [
    { id: id("earth"), type: "fill", source, "source-layer": "earth", paint: { "fill-color": palette.paper } },
    {
      id: id("park"),
      type: "fill",
      source,
      "source-layer": "landuse",
      filter: ["in", ["get", "kind"], ["literal", ["park", "forest", "wood", "nature_reserve", "national_park", "grass", "meadow"]]],
      paint: { "fill-color": palette.park, "fill-opacity": 0.8 },
    },
    {
      id: id("water"),
      type: "fill",
      source,
      "source-layer": "water",
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "fill-color": palette.water },
    },
    {
      id: id("rivers"),
      type: "line",
      source,
      "source-layer": "water",
      filter: ["all", ["==", ["geometry-type"], "LineString"], ["!", ARGA]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": palette.river,
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, ["match", ["get", "kind"], "river", 1, 0.4], 14, ["match", ["get", "kind"], "river", 3, 1]],
      },
    },
    {
      id: id("arga"),
      type: "line",
      source,
      "source-layer": "water",
      filter: ["all", ["==", ["geometry-type"], "LineString"], ARGA],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": palette.arga, "line-width": ["interpolate", ["linear"], ["zoom"], 7, 1.6, 11, 3, 15, 6] },
    },
    {
      id: id("boundaries"),
      type: "line",
      source,
      "source-layer": "boundaries",
      paint: { "line-color": palette.boundary, "line-width": 0.8, "line-dasharray": [3, 2] },
    },
    {
      id: id("roads-edge"),
      type: "line",
      source,
      "source-layer": "roads",
      minzoom: 12,
      filter: roads(["highway", "major_road", "medium_road", "minor_road"]),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": palette["road-edge"],
        "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 12, 1.5, 18, 22],
      },
    },
    {
      id: id("roads-minor"),
      type: "line",
      source,
      "source-layer": "roads",
      minzoom: 12,
      filter: roads(["minor_road", "medium_road", "path"]),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": palette.road,
        "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 12, 0.6, 18, 16],
      },
    },
    {
      id: id("roads-major"),
      type: "line",
      source,
      "source-layer": "roads",
      filter: roads(["highway", "major_road"]),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": palette["road-major"],
        "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 7, 0.6, 12, 2, 18, 20],
      },
    },
    {
      id: id("buildings"),
      type: "fill",
      source,
      "source-layer": "buildings",
      minzoom: 14,
      paint: { "fill-color": palette.building },
    },
  ];
}

export function labelLayers(source: Piece | string, palette: AreaPalette): maplibre.LayerSpecification[] {
  const id = (name: string) => `${source}-${name}-label`;
  const halo = { "text-halo-color": palette.halo, "text-halo-width": 1.4 };
  return [
    {
      id: id("water"),
      type: "symbol",
      source,
      "source-layer": "water",
      minzoom: 10,
      filter: ["all", ["==", ["geometry-type"], "LineString"], ["has", "name"]],
      layout: {
        "symbol-placement": "line",
        "text-field": ["get", "name"],
        "text-font": ITALIC,
        "text-size": ["case", ARGA, 13, 11],
        "symbol-spacing": 400,
      },
      paint: { "text-color": palette["label-water"], ...halo },
    },
    {
      id: id("street"),
      type: "symbol",
      source,
      "source-layer": "roads",
      minzoom: 15,
      filter: ["has", "name"],
      layout: {
        "symbol-placement": "line",
        "text-field": ["get", "name"],
        "text-font": REGULAR,
        "text-size": 11,
      },
      paint: { "text-color": palette["label-muted"], ...halo },
    },
    {
      id: id("peak"),
      type: "symbol",
      source,
      "source-layer": "pois",
      minzoom: 9,
      filter: ["all", ["in", ["get", "kind"], ["literal", ["peak", "ridge", "mountain_range"]]], ["has", "name"]],
      layout: {
        "text-field": ["upcase", ["get", "name"]],
        "text-font": MEDIUM,
        "text-size": 10,
        "text-letter-spacing": 0.16,
      },
      paint: { "text-color": palette["label-relief"], ...halo },
    },
    {
      id: id("place"),
      type: "symbol",
      source,
      "source-layer": "places",
      filter: ["==", ["get", "kind"], "locality"],
      layout: {
        "text-field": bilingual(palette["label-muted"]),
        "text-font": ["case", [">=", ["coalesce", ["get", "population_rank"], 0], 9], ["literal", MEDIUM], ["literal", REGULAR]],
        "text-size": [
          "interpolate",
          ["linear"],
          ["coalesce", ["get", "population_rank"], 1],
          1,
          11,
          10,
          16,
        ],
        "symbol-sort-key": ["-", 20, ["coalesce", ["get", "population_rank"], 0]],
        "text-max-width": 9,
      },
      paint: {
        "text-color": ["case", ["==", ["get", "kind"], "locality"], palette.label, palette["label-muted"]],
        ...halo,
      },
    },
    {
      id: id("hood"),
      type: "symbol",
      source,
      "source-layer": "places",
      minzoom: 13.5,
      filter: ["in", ["get", "kind"], ["literal", ["macrohood", "neighbourhood"]]],
      layout: {
        "text-field": bilingual(palette["label-muted"]),
        "text-font": ["case", [">=", ["coalesce", ["get", "population_rank"], 0], 9], ["literal", MEDIUM], ["literal", REGULAR]],
        "text-size": [
          "interpolate",
          ["linear"],
          ["coalesce", ["get", "population_rank"], 1],
          1,
          11,
          10,
          16,
        ],
        "symbol-sort-key": ["-", 20, ["coalesce", ["get", "population_rank"], 0]],
        "text-max-width": 9,
      },
      paint: {
        "text-color": ["case", ["==", ["get", "kind"], "locality"], palette.label, palette["label-muted"]],
        ...halo,
      },
    },
  ];
}

function style(base: string, palette: AreaPalette): maplibre.StyleSpecification {
  return {
    version: 8,
    glyphs: `${base}fonts/{fontstack}/{range}.pbf`,
    sources: {
      navarra: { type: "vector", url: `pmtiles://${base}navarra.pmtiles`, attribution: "© OpenStreetMap" },
      comarca: { type: "vector", url: `pmtiles://${base}comarca.pmtiles` },
      "relief-navarra": { type: "geojson", data: EMPTY, attribution: "MDT © IGN" },
      "relief-comarca": { type: "geojson", data: EMPTY },
    },
    layers: [
      { id: "paper", type: "background", paint: { "background-color": palette.paper } },
      ...streetLayers("navarra", palette).filter((layer) => !layer.id.endsWith("buildings")),
      ...relief("relief-navarra", palette, 0, 11),
      ...relief("relief-comarca", palette, 10, 24),
      ...streetLayers("comarca", palette).filter((layer) => !layer.id.endsWith("earth")),
      ...labelLayers("navarra", palette),
      ...labelLayers("comarca", palette),
    ],
  };
}

function relief(
  source: string,
  palette: AreaPalette,
  minzoom: number,
  maxzoom: number,
): maplibre.LayerSpecification[] {
  const bold: maplibre.ExpressionSpecification = ["==", ["%", ["get", "ele"], 200], 0];
  return [
    {
      id: source,
      type: "line",
      source,
      minzoom,
      maxzoom,
      layout: { "line-join": "round" },
      paint: {
        "line-color": ["case", bold, palette["contour-bold"], palette.contour],
        "line-width": ["case", bold, 1, 0.6],
      },
    },
  ];
}

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

const RELIEFS = [
  ["relief-navarra", "relieve-navarra.json"],
  ["relief-comarca", "relieve-comarca.json"],
] as const;

const reliefs = new Map<string, Promise<FeatureCollection<Geometry>>>();

function loadRelief(url: string): Promise<FeatureCollection<Geometry>> {
  let found = reliefs.get(url);
  if (!found) {
    found = fetch(url)
      .then((response) => {
        if (!response.ok) throw new Error(`${url}: ${response.status}`);
        return response.json() as Promise<Parameters<typeof topoFeature>[0]>;
      })
      .then((topology) => topoFeature(topology, topology.objects.relief!) as unknown as FeatureCollection<Geometry>);
    found.catch(() => reliefs.delete(url));
    reliefs.set(url, found);
  }
  return found;
}

export function pointFeatures(points: AreaPoint[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: points.map((point) => ({
      type: "Feature",
      properties: { id: point.id },
      geometry: { type: "Point", coordinates: [point.lon, point.lat] },
    })),
  };
}

function Mark({ point, selected }: { point: AreaPoint; selected: boolean }) {
  if (point.kind === "pill") {
    return (
      <span className="area-map-pill" data-hue={point.hue} data-selected={selected || undefined}>
        <span className="area-map-pill-dot" />
        {point.label}
      </span>
    );
  }
  return (
    <span className="area-map-photo" data-hue={point.hue} data-selected={selected || undefined}>
      {point.image ? <img src={point.image} alt="" draggable={false} /> : <Icon name={point.icon ?? "pin"} />}
    </span>
  );
}

interface Placed {
  marker: maplibre.Marker;
  root: Root;
  key: string;
}

export function AreaMap({ base, view, points, selected = null, onSelect, label, center = null, compact = false }: AreaMapProps) {
  const container = React.useRef<HTMLDivElement>(null);
  const [map, setMap] = React.useState<maplibre.Map | null>(null);
  const [failed, setFailed] = React.useState(false);
  const pointsRef = React.useRef(points);
  pointsRef.current = points;
  const selectedRef = React.useRef(selected);
  selectedRef.current = selected;
  const onSelectRef = React.useRef(onSelect);
  onSelectRef.current = onSelect;
  const placed = React.useRef(new Map<string, Placed>());
  const absolute = React.useMemo(() => new URL(base, window.location.href).href, [base]);

  React.useEffect(() => {
    const element = container.current;
    if (!element) return;
    ensurePmtiles();
    const created = new maplibre.Map({
      container: element,
      style: style(absolute, readAreaPalette(element)),
      bounds: center ? undefined : VIEWS[view],
      center: center ?? undefined,
      zoom: center ? 13.5 : undefined,
      fitBoundsOptions: { padding: compact ? 8 : 24 },
      maxBounds: [
        [-3.4, 41.4],
        [0.2, 43.8],
      ],
      minZoom: 6.5,
      maxZoom: 18,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      interactive: !compact,
      fadeDuration: 0,
    });
    created.addControl(new maplibre.AttributionControl({ compact: true }), "bottom-left");
    created.touchZoomRotate.disableRotation();
    created.keyboard.disableRotation();
    created.on("error", (event) => {
      if (String(event.error?.message ?? "").includes("pmtiles")) setFailed(true);
    });
    const decorate = () => {
      if (!created.getSource("points")) {
        created.addSource("points", {
          type: "geojson",
          data: pointFeatures(pointsRef.current),
          cluster: !compact,
          clusterRadius: 44,
          clusterMaxZoom: 16,
        });
        created.addLayer({
          id: "points",
          type: "circle",
          source: "points",
          paint: { "circle-radius": 0, "circle-opacity": 0 },
        });
      }
      for (const [key, file] of RELIEFS) {
        void loadRelief(`${absolute}${file}`)
          .then((data) => (created.getSource(key) as maplibre.GeoJSONSource | undefined)?.setData(data))
          .catch(() => undefined);
      }
      setMap(created);
    };
    created.on("style.load", decorate);
    created.on("click", (event) => {
      if ((event.originalEvent.target as Element).closest(".maplibregl-marker")) return;
      onSelectRef.current?.(null);
    });

    const resize = new ResizeObserver(() => created.resize());
    resize.observe(element);
    const repaint = () => created.setStyle(style(absolute, readAreaPalette(element)));
    const scheme = window.matchMedia("(prefers-color-scheme: dark)");
    scheme.addEventListener("change", repaint);
    const theme = new MutationObserver(repaint);
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    const marks = placed.current;
    return () => {
      resize.disconnect();
      theme.disconnect();
      scheme.removeEventListener("change", repaint);
      for (const one of marks.values()) {
        one.marker.remove();
        queueMicrotask(() => one.root.unmount());
      }
      marks.clear();
      created.remove();
      setMap(null);
    };
  }, [absolute, compact]);

  React.useEffect(() => {
    if (!map || center) return;
    map.fitBounds(VIEWS[view], { padding: 24, duration: 600 });
  }, [map, view, center]);

  React.useEffect(() => {
    if (!map) return;
    (map.getSource("points") as maplibre.GeoJSONSource | undefined)?.setData(pointFeatures(points));
  }, [map, points]);

  React.useEffect(() => {
    if (!map) return;
    const sync = () => {
      const byId = new Map(pointsRef.current.map((point) => [point.id, point]));
      const seen = new Set<string>();
      for (const found of map.querySourceFeatures("points")) {
        const properties = found.properties ?? {};
        const [lon, lat] = (found.geometry as GeoJSON.Point).coordinates as [number, number];
        if (properties.cluster) {
          const key = `cluster:${properties.cluster_id}`;
          if (seen.has(key)) continue;
          seen.add(key);
          const count = Number(properties.point_count);
          place(key, `${key}:${count}`, [lon, lat], () => (
            <button
              type="button"
              className="area-map-cluster"
              aria-label={`${count} juntos: acercar`}
              onClick={() => {
                void (map.getSource("points") as maplibre.GeoJSONSource)
                  .getClusterExpansionZoom(Number(properties.cluster_id))
                  .then((zoom) => map.easeTo({ center: [lon, lat], zoom: zoom + 0.5 }));
              }}
            >
              {count}
            </button>
          ));
          continue;
        }
        const point = byId.get(String(properties.id));
        if (!point || seen.has(point.id)) continue;
        seen.add(point.id);
        const isSelected = selectedRef.current === point.id;
        place(point.id, `${point.id}:${point.image ?? ""}:${point.label ?? ""}:${isSelected}`, [point.lon, point.lat], () => (
          <button
            type="button"
            className="area-map-mark"
            aria-label={point.title}
            aria-pressed={isSelected}
            onClick={() => onSelectRef.current?.(point.id)}
          >
            <Mark point={point} selected={isSelected} />
          </button>
        ));
      }
      for (const [key, one] of placed.current) {
        if (!seen.has(key)) {
          one.marker.remove();
          queueMicrotask(() => one.root.unmount());
          placed.current.delete(key);
        }
      }
    };

    const place = (key: string, version: string, at: [number, number], render: () => React.ReactNode) => {
      const existing = placed.current.get(key);
      if (existing && existing.key === version) {
        existing.marker.setLngLat(at);
        return;
      }
      if (existing) {
        existing.root.render(render());
        existing.key = version;
        existing.marker.setLngLat(at);
        return;
      }
      const element = document.createElement("div");
      const root = createRoot(element);
      root.render(render());
      const marker = new maplibre.Marker({ element }).setLngLat(at).addTo(map);
      placed.current.set(key, { marker, root, key: version });
    };

    map.on("idle", sync);
    map.on("moveend", sync);
    sync();
    return () => {
      map.off("idle", sync);
      map.off("moveend", sync);
    };
  }, [map, points, selected]);

  return (
    <div className="area-map" role="region" aria-label={label} data-compact={compact || undefined}>
      <div ref={container} className="area-map-canvas" />
      {failed && <p className="area-map-failed">No se ha podido cargar el mapa.</p>}
    </div>
  );
}
