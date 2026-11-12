// eslint-disable-next-line @typescript-eslint/triple-slash-reference
/// <reference path="./d3-geo-projection.d.ts" />
import "maplibre-gl/dist/maplibre-gl.css";

import type { Feature, FeatureCollection, Geometry, LineString } from "geojson";
import * as maplibre from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import * as React from "react";
import { feature as topoFeature } from "topojson-client";

import { Icon } from "./icons";
import { EUROPE_VIEW, type RouteMode, boundsOf, distanceKm, graticuleLines, routeArc } from "./globe";
import { usePrefersReducedMotion } from "./motion";

export type MapLevel = "country" | "region" | "none";

export interface MapArea {
  code: string;
  tone: "slept" | "visited" | "home";
  weight: number;
}

export interface MapPlace {
  id: string;
  lon: number;
  lat: number;
  kind: "stay" | "visit" | "idea";
  size: number;
}

export interface MapRoute {
  id: string;
  group: string;
  order: number;
  from: [number, number];
  to: [number, number];
  mode: RouteMode;
}

export interface WorldMapProps {
  geoBase: string;
  level: MapLevel;
  areas: MapArea[];
  places: MapPlace[];
  routes: MapRoute[];
  highlight?: string | null;
  focus?: [number, number][] | null;
  selected?: string | null;
  tour?: boolean;
  onTourDone?: () => void;
  onSelectArea?: (code: string, name: string) => void;
  onSelectPlace?: (id: string) => void;
  label: string;
  className?: string;
}

maplibre.setWorkerUrl(workerUrl);

type Areas = FeatureCollection<Geometry, { code: string; name: string; country?: string }>;

const loaded = new Map<string, Promise<Areas>>();

function load(url: string, object: "countries" | "regions"): Promise<Areas> {
  let found = loaded.get(url);
  if (!found) {
    found = fetch(url)
      .then((response) => {
        if (!response.ok) throw new Error(`${url}: ${response.status}`);
        return response.json() as Promise<Parameters<typeof topoFeature>[0]>;
      })
      .then((topology) => topoFeature(topology, topology.objects[object]!) as unknown as Areas);
    found.catch(() => loaded.delete(url));
    loaded.set(url, found);
  }
  return found;
}

let lines: ReturnType<typeof graticuleLines> | null = null;
const grid = () => (lines ??= graticuleLines());

const TOKENS = [
  "bg-base",
  "map-water",
  "map-land",
  "map-border",
  "map-coast",
  "map-graticule",
  "map-slept-low",
  "map-slept-high",
  "map-visited",
  "map-home",
  "map-route",
  "map-route-quiet",
  "map-place",
  "map-place-edge",
  "map-selected",
  "map-idea",
] as const;

type Palette = Record<(typeof TOKENS)[number], string>;

export function readPalette(element: Element): Palette {
  const style = getComputedStyle(element);
  return Object.fromEntries(
    TOKENS.map((token) => [token, style.getPropertyValue(`--${token}`).trim() || "transparent"]),
  ) as Palette;
}

const STEPS = 4;

export function toneLayers(areas: MapArea[]): { visited: string[]; slept: string[][]; home: string[] } {
  const slept: string[][] = Array.from({ length: STEPS }, () => []);
  const visited: string[] = [];
  const home: string[] = [];
  for (const area of areas) {
    if (area.tone === "home") {
      home.push(area.code);
    } else if (area.tone === "visited") {
      visited.push(area.code);
    } else {
      const step = Math.min(STEPS - 1, Math.floor(Math.max(0, Math.min(1, area.weight)) * STEPS));
      slept[step]!.push(area.code);
    }
  }
  return { visited, slept, home };
}

const AREA_LAYERS = ["visited", ...Array.from({ length: STEPS }, (_, step) => `slept-${step}`), "home"];

function areaLayers(source: "countries" | "regions"): maplibre.LayerSpecification[] {
  return AREA_LAYERS.map((tone) => ({
    id: `${source}-${tone}`,
    type: "fill" as const,
    source,
    filter: ["in", ["get", "code"], ["literal", []]] as maplibre.FilterSpecification,
    paint: {},
  }));
}

function paint(map: maplibre.Map, palette: Palette, areas: { countries: MapArea[]; regions: MapArea[] }): void {
  const set = (layer: string, property: string, value: unknown) => {
    if (!map.getLayer(layer)) return;
    (map.setPaintProperty as (l: string, p: string, v: unknown) => void).call(map, layer, property, value);
  };
  set("backdrop", "background-color", palette["map-water"]);
  set("graticule", "line-color", palette["map-graticule"]);
  set("countries-fill", "fill-color", palette["map-land"]);
  for (const source of ["countries", "regions"] as const) {
    const tones = toneLayers(areas[source]);
    set(`${source}-visited`, "fill-color", palette["map-visited"]);
    map.setFilter(`${source}-visited`, ["in", ["get", "code"], ["literal", tones.visited]]);
    tones.slept.forEach((codes, step) => {
      const share = Math.round(((step + 1) / STEPS) * 100);
      set(
        `${source}-slept-${step}`,
        "fill-color",
        mix(palette["map-slept-high"], palette["map-slept-low"], share),
      );
      map.setFilter(`${source}-slept-${step}`, ["in", ["get", "code"], ["literal", codes]]);
    });
    set(`${source}-home`, "fill-color", palette["map-home"]);
    map.setFilter(`${source}-home`, ["in", ["get", "code"], ["literal", tones.home]]);
  }
  set("regions-line", "line-color", palette["map-border"]);
  set("countries-line", "line-color", palette["map-coast"]);
  set("selected-line", "line-color", palette["map-selected"]);
  set("routes", "line-color", palette["map-route"]);
  set("routes-boat", "line-color", palette["map-route"]);
  set("active", "line-color", palette["map-route"]);
  set("active-boat", "line-color", palette["map-route"]);
  set("places", "circle-color", [
    "case",
    ["==", ["get", "kind"], "stay"],
    palette["map-place-edge"],
    ["==", ["get", "kind"], "idea"],
    palette["map-idea"],
    palette["map-place"],
  ]);
  set("places", "circle-stroke-color", [
    "case",
    ["in", ["get", "kind"], ["literal", ["stay", "idea"]]],
    palette["map-place"],
    palette["map-place-edge"],
  ]);
}

function mix(a: string, b: string, share: number): string {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 1;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return a;
  context.fillStyle = b;
  context.fillRect(0, 0, 1, 1);
  context.globalAlpha = share / 100;
  context.fillStyle = a;
  context.fillRect(0, 0, 1, 1);
  const [r, g, bl] = context.getImageData(0, 0, 1, 1).data;
  return `rgb(${r}, ${g}, ${bl})`;
}

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

function baseStyle(): maplibre.StyleSpecification {
  return {
    version: 8,
    projection: { type: "globe" },
    sky: { "atmosphere-blend": 0 },
    sources: {
      graticule: {
        type: "geojson",
        data: { type: "Feature", properties: {}, geometry: grid() },
      },
      countries: { type: "geojson", data: EMPTY, tolerance: 0.05 },
      regions: { type: "geojson", data: EMPTY, tolerance: 0.05 },
      routes: { type: "geojson", data: EMPTY },
      active: { type: "geojson", data: EMPTY },
      places: { type: "geojson", data: EMPTY },
    },
    layers: [
      { id: "backdrop", type: "background", paint: {} },
      { id: "graticule", type: "line", source: "graticule", paint: { "line-width": 0.6 } },
      { id: "countries-fill", type: "fill", source: "countries", paint: {} },
      ...areaLayers("countries"),
      {
        id: "regions-fill",
        type: "fill",
        source: "regions",
        layout: { visibility: "none" },
        paint: { "fill-color": "rgba(0, 0, 0, 0)" },
      },
      ...areaLayers("regions"),
      {
        id: "regions-line",
        type: "line",
        source: "regions",
        layout: { visibility: "none", "line-join": "round" },
        paint: { "line-width": ["interpolate", ["linear"], ["zoom"], 2, 0.3, 6, 0.8] },
      },
      {
        id: "countries-line",
        type: "line",
        source: "countries",
        layout: { "line-join": "round" },
        paint: { "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.4, 5, 1, 9, 1.6] },
      },
      {
        id: "routes",
        type: "line",
        source: "routes",
        filter: ["!=", ["get", "mode"], "boat"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-width": ["interpolate", ["linear"], ["zoom"], 2, 1, 7, 2.2], "line-opacity": ["get", "opacity"] },
      },
      {
        id: "routes-boat",
        type: "line",
        source: "routes",
        filter: ["==", ["get", "mode"], "boat"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": ["interpolate", ["linear"], ["zoom"], 2, 1, 7, 2.2],
          "line-opacity": ["get", "opacity"],
          "line-dasharray": [2, 2.5],
        },
      },
      {
        id: "active",
        type: "line",
        source: "active",
        filter: ["!=", ["get", "mode"], "boat"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-width": ["interpolate", ["linear"], ["zoom"], 2, 2, 7, 3.4] },
      },
      {
        id: "active-boat",
        type: "line",
        source: "active",
        filter: ["==", ["get", "mode"], "boat"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-width": ["interpolate", ["linear"], ["zoom"], 2, 2, 7, 3.4],
          "line-dasharray": [2, 2],
        },
      },
      {
        id: "places",
        type: "circle",
        source: "places",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            2,
            ["case", ["==", ["get", "kind"], "stay"], ["+", 1.6, ["*", 1.6, ["get", "size"]]], ["==", ["get", "kind"], "idea"], 2.4, 1.2],
            8,
            ["case", ["==", ["get", "kind"], "stay"], ["+", 5, ["*", 5, ["get", "size"]]], ["==", ["get", "kind"], "idea"], 6, 3.5],
          ],
          "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 2, 1, 6, 1.5],
        },
      },
    ],
  };
}

function routeFeatures(routes: MapRoute[], highlight: string | null | undefined): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: routes
      .filter((route) => route.group !== highlight)
      .map((route) => ({
        type: "Feature",
        properties: { mode: route.mode, group: route.group, opacity: highlight ? 0.35 : 0.9 },
        geometry: routeArc(route.from, route.to, route.mode),
      })),
  };
}

const ORDER: Record<MapPlace["kind"], number> = { visit: 0, stay: 1, idea: 2 };

function placeFeatures(places: MapPlace[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: [...places]
      .sort((a, b) => ORDER[a.kind] - ORDER[b.kind])
      .map((place) => ({
        type: "Feature",
        properties: { id: place.id, kind: place.kind, size: Math.max(0, Math.min(1, place.size)) },
        geometry: { type: "Point", coordinates: [place.lon, place.lat] },
      })),
  };
}

export function partOf(line: LineString, progress: number): LineString {
  const points = line.coordinates;
  if (progress >= 1 || points.length < 2) return line;
  const cut = Math.max(1, Math.floor(progress * (points.length - 1)));
  return { type: "LineString", coordinates: points.slice(0, cut + 1) };
}

const FRAME = { top: 120, bottom: 150, left: 12, right: 12 };
const FRAME_TIGHT = { top: 48, bottom: 48, left: 32, right: 32 };

const LEG_MS = 700;
const MAX_MS = 6000;

const TOUR_FRAME_MS = 900;
const TOUR_FLY_MAX_MS = 4000;
const TOUR_TRIP_ZOOM = 6;
const TOUR_LEG_ZOOM = 8.5;
const tourLegMs = (km: number) => 900 + 250 * Math.log10(km + 1);

function useLatest<T>(value: T) {
  const ref = React.useRef(value);
  ref.current = value;
  return ref;
}

export function WorldMap({
  geoBase,
  level,
  areas,
  places,
  routes,
  highlight = null,
  focus = null,
  selected = null,
  tour = false,
  onTourDone,
  onSelectArea,
  onSelectPlace,
  label,
  className,
}: WorldMapProps) {
  const container = React.useRef<HTMLDivElement>(null);
  const [map, setMap] = React.useState<maplibre.Map | null>(null);
  const [countriesReady, setCountriesReady] = React.useState(false);
  const [regionsReady, setRegionsReady] = React.useState(false);
  const [failed, setFailed] = React.useState(false);
  const reduced = usePrefersReducedMotion();
  const callbacks = useLatest({ onSelectArea, onSelectPlace, onTourDone, level });
  const painted = useLatest({
    countries: level === "country" ? areas : [],
    regions: level === "region" ? areas : [],
  });

  React.useEffect(() => {
    const element = container.current;
    if (!element) return;
    const europe = boundsOf(EUROPE_VIEW)!;
    const created = new maplibre.Map({
      container: element,
      style: baseStyle(),
      bounds: europe,
      fitBoundsOptions: { padding: FRAME },
      renderWorldCopies: false,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      minZoom: 0.5,
      maxZoom: 11,
      fadeDuration: 0,
    });
    created.touchZoomRotate.disableRotation();
    created.keyboard.disableRotation();

    created.on("load", () => {
      paint(created, readPalette(element), painted.current);
      setMap(created);
    });

    created.on("click", (event) => {
      const box: [maplibre.PointLike, maplibre.PointLike] = [
        [event.point.x - 10, event.point.y - 10],
        [event.point.x + 10, event.point.y + 10],
      ];
      const place = created.queryRenderedFeatures(box, { layers: ["places"] })[0];
      if (place && callbacks.current.onSelectPlace) {
        callbacks.current.onSelectPlace(String(place.properties.id));
        return;
      }
      const layer = callbacks.current.level === "region" ? "regions-fill" : "countries-fill";
      const area = created.queryRenderedFeatures(event.point, { layers: [layer] })[0];
      if (area && callbacks.current.onSelectArea) {
        callbacks.current.onSelectArea(String(area.properties.code), String(area.properties.name));
      }
    });

    const resize = new ResizeObserver(() => created.resize());
    resize.observe(element);

    const repaint = () => paint(created, readPalette(element), painted.current);
    const scheme = window.matchMedia("(prefers-color-scheme: dark)");
    scheme.addEventListener("change", repaint);
    const theme = new MutationObserver(repaint);
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    return () => {
      resize.disconnect();
      theme.disconnect();
      scheme.removeEventListener("change", repaint);
      created.remove();
      setMap(null);
    };
  }, []);

  React.useEffect(() => {
    if (!map) return;
    let cancelled = false;
    load(`${geoBase}countries.json`, "countries")
      .then((data) => {
        if (cancelled) return;
        (map.getSource("countries") as maplibre.GeoJSONSource).setData(data);
        setCountriesReady(true);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [map, geoBase]);

  React.useEffect(() => {
    if (!map || level !== "region" || regionsReady) return;
    let cancelled = false;
    load(`${geoBase}regions.json`, "regions")
      .then((data) => {
        if (cancelled) return;
        (map.getSource("regions") as maplibre.GeoJSONSource).setData(data);
        setRegionsReady(true);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [map, geoBase, level, regionsReady]);

  React.useEffect(() => {
    if (!map || !countriesReady) return;
    const regionLevel = level === "region";
    for (const layer of ["regions-fill", "regions-line", ...AREA_LAYERS.map((tone) => `regions-${tone}`)]) {
      map.setLayoutProperty(layer, "visibility", regionLevel ? "visible" : "none");
    }
    paint(map, readPalette(container.current!), painted.current);
  }, [map, countriesReady, regionsReady, level, areas, painted]);

  React.useEffect(() => {
    if (!map) return;
    const source = level === "region" && regionsReady ? "regions" : "countries";
    if (map.getLayer("selected-line")) map.removeLayer("selected-line");
    map.addLayer(
      {
        id: "selected-line",
        type: "line",
        source,
        filter: ["==", ["get", "code"], selected ?? ""],
        layout: { "line-join": "round" },
        paint: { "line-width": 2, "line-color": readPalette(container.current!)["map-selected"] },
      },
      "routes",
    );
  }, [map, level, regionsReady, selected]);

  React.useEffect(() => {
    if (!map) return;
    (map.getSource("places") as maplibre.GeoJSONSource).setData(placeFeatures(places));
    (map.getSource("routes") as maplibre.GeoJSONSource).setData(routeFeatures(routes, highlight));
  }, [map, places, routes, highlight]);

  React.useEffect(() => {
    if (!map || tour) return;
    const source = map.getSource("active") as maplibre.GeoJSONSource;
    const legs = routes
      .filter((route) => route.group === highlight)
      .sort((a, b) => a.order - b.order)
      .map((route) => ({ route, line: routeArc(route.from, route.to, route.mode) }));
    const frame = (progress: number): FeatureCollection => {
      const done = progress * legs.length;
      const features: Feature[] = [];
      legs.forEach(({ route, line }, index) => {
        const part = Math.max(0, Math.min(1, done - index));
        if (part > 0) features.push({ type: "Feature", properties: { mode: route.mode }, geometry: partOf(line, part) });
      });
      return { type: "FeatureCollection", features };
    };
    if (!legs.length || reduced) {
      source.setData(frame(1));
      return;
    }
    const total = Math.min(MAX_MS, LEG_MS * legs.length);
    let start: number | null = null;
    let handle = 0;
    const step = (now: number) => {
      start ??= now;
      const progress = Math.min(1, (now - start) / total);
      source.setData(frame(progress));
      if (progress < 1) handle = requestAnimationFrame(step);
    };
    handle = requestAnimationFrame(step);
    return () => cancelAnimationFrame(handle);
  }, [map, routes, highlight, reduced, tour]);

  const focusKey = focus ? JSON.stringify(focus) : "";

  const tourLegs = routes
    .filter((route) => route.group === highlight)
    .sort((a, b) => a.order - b.order);
  const tourKey = tour && highlight ? `${highlight}:${tourLegs.map((one) => one.id).join(",")}` : "";
  React.useEffect(() => {
    if (!map || !tourKey) return;
    const source = map.getSource("active") as maplibre.GeoJSONSource;
    const legs = tourLegs;
    let cancelled = false;
    let frame = 0;
    const timers = new Set<number>();
    const wait = (ms: number) =>
      new Promise<void>((resolve) => {
        const timer = window.setTimeout(() => {
          timers.delete(timer);
          resolve();
        }, ms);
        timers.add(timer);
      });
    const drawn: Feature[] = [];
    const show = (partial?: Feature) =>
      source.setData({ type: "FeatureCollection", features: partial ? [...drawn, partial] : drawn });
    const cameraFor = (points: [number, number][], maxZoom: number) => {
      const box = boundsOf(points);
      const side = Math.round(map.getContainer().clientWidth * 0.18);
      return box ? map.cameraForBounds(box, { padding: { ...FRAME, left: side, right: side }, maxZoom }) : undefined;
    };
    const move = (camera: maplibre.CameraOptions | undefined, fly: boolean) =>
      new Promise<void>((resolve) => {
        if (!camera) return resolve();
        if (reduced) {
          map.jumpTo(camera);
          return resolve();
        }
        let finished = false;
        const done = () => {
          if (finished) return;
          finished = true;
          map.off("moveend", done);
          resolve();
        };
        map.on("moveend", done);
        void wait((fly ? TOUR_FLY_MAX_MS : TOUR_FRAME_MS) + 400).then(done);
        if (fly) map.flyTo({ ...camera, maxDuration: TOUR_FLY_MAX_MS });
        else map.easeTo({ ...camera, duration: TOUR_FRAME_MS });
      });
    const draw = (route: MapRoute, line: LineString) =>
      new Promise<void>((resolve) => {
        const properties = { mode: route.mode };
        const whole: Feature = { type: "Feature", properties, geometry: line };
        if (reduced) {
          drawn.push(whole);
          show();
          return resolve();
        }
        const total = tourLegMs(distanceKm(route.from, route.to));
        let start: number | null = null;
        const step = (now: number) => {
          if (cancelled) return resolve();
          start ??= now;
          const progress = Math.min(1, (now - start) / total);
          if (progress < 1) {
            show({ type: "Feature", properties, geometry: partOf(line, progress) });
            frame = requestAnimationFrame(step);
          } else {
            drawn.push(whole);
            show();
            resolve();
          }
        };
        frame = requestAnimationFrame(step);
      });

    const run = async () => {
      show();
      const everywhere = focus?.length ? focus : legs.flatMap((one) => [one.from, one.to]);
      await move(cameraFor(everywhere, TOUR_TRIP_ZOOM), true);
      if (cancelled) return;
      await wait(500);
      for (const route of legs) {
        if (cancelled) return;
        await move(cameraFor([route.from, route.to], TOUR_LEG_ZOOM), false);
        if (cancelled) return;
        await draw(route, routeArc(route.from, route.to, route.mode));
      }
      if (cancelled) return;
      await wait(legs.length ? 900 : 1600);
      if (!cancelled) callbacks.current.onTourDone?.();
    };
    void run();
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      timers.forEach((timer) => window.clearTimeout(timer));
      map.stop();
    };
  }, [map, tourKey, focusKey, reduced]);

  React.useEffect(() => {
    if (!map || tour) return;
    const points = focus && focus.length ? focus : EUROPE_VIEW;
    const box = boundsOf(points);
    if (!box) return;
    const single = box[0][0] === box[1][0] && box[0][1] === box[1][1];
    if (single) {
      map.easeTo({ center: box[0], zoom: Math.max(map.getZoom(), 5), duration: reduced ? 0 : 900 });
    } else {
      map.fitBounds(box, { padding: focus?.length ? FRAME_TIGHT : FRAME, maxZoom: 8, duration: reduced ? 0 : 900 });
    }
  }, [map, focusKey, reduced, tour]);

  return (
    <div className={["world-map", className].filter(Boolean).join(" ")}>
      <div ref={container} className="world-map-canvas" role="region" aria-label={label} />
      {failed && (
        <p className="world-map-failed" role="status">
          No se han podido cargar los países del mapa. Vuelve a abrirlo en un momento.
        </p>
      )}
    </div>
  );
}

export function useCountries(geoBase: string): Areas["features"] | null {
  const [found, setFound] = React.useState<Areas["features"] | null>(null);
  React.useEffect(() => {
    let cancelled = false;
    load(`${geoBase}countries.json`, "countries")
      .then((data) => !cancelled && setFound(data.features))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [geoBase]);
  return found;
}

export interface TimeBarProps {
  min: number;
  max: number;
  value: [number, number];
  onChange: (value: [number, number]) => void;
  playing?: boolean;
  onPlay?: () => void;
  onPause?: () => void;
}

export function TimeBar({ min, max, value, onChange, playing, onPlay, onPause }: TimeBarProps) {
  const [from, to] = value;
  const span = Math.max(1, max - min);
  const left = ((from - min) / span) * 100;
  const right = ((to - min) / span) * 100;
  const single = min === max;
  return (
    <div className="time-bar glass">
      {onPlay && (
        <button
          type="button"
          className="time-bar-play"
          aria-label={playing ? "Pausar" : "Reproducir los viajes en orden"}
          onClick={playing ? onPause : onPlay}
        >
          <Icon name={playing ? "pause" : "play"} />
        </button>
      )}
      <span className="time-bar-year">{from}</span>
      <div
        className="time-bar-track"
        style={{ "--from": `${left}%`, "--to": `${right}%` } as React.CSSProperties}
      >
        <input
          type="range"
          aria-label="Desde"
          min={min}
          max={max}
          step={1}
          value={from}
          disabled={single}
          onChange={(event) => onChange([Math.min(Number(event.target.value), to), to])}
        />
        <input
          type="range"
          aria-label="Hasta"
          min={min}
          max={max}
          step={1}
          value={to}
          disabled={single}
          onChange={(event) => onChange([from, Math.max(Number(event.target.value), from)])}
        />
      </div>
      <span className="time-bar-year">{to}</span>
    </div>
  );
}

export interface MapFigure {
  label: string;
  value: string;
}

export function MapFigures({ figures }: { figures: MapFigure[] }) {
  return (
    <dl className="map-figures glass">
      {figures.map((figure) => (
        <div key={figure.label} className="map-figure">
          <dt>{figure.label}</dt>
          <dd>{figure.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export { localView, routeArc } from "./globe";
export type { RouteMode } from "./globe";
