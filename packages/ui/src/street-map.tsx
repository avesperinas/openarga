import "maplibre-gl/dist/maplibre-gl.css";

import * as maplibre from "maplibre-gl";
import * as React from "react";

import { labelLayers, readAreaPalette, streetLayers } from "./area-map";

export interface StreetStop {
  id: string;
  lon: number;
  lat: number;
  number: number | null;
  title: string;
  hue?: number;
  quiet?: boolean;
}

export interface StreetMapProps {
  tiles: string;
  glyphs: string;
  stops: StreetStop[];
  line: [number, number][] | null;
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  label: string;
  lineHue?: number;
  padding?: { top: number; bottom: number; left: number; right: number };
}

const EMPTY_LINE: GeoJSON.Feature<GeoJSON.LineString> = {
  type: "Feature",
  properties: {},
  geometry: { type: "LineString", coordinates: [] },
};

function routeColor(element: Element, hue?: number): string {
  const token = hue ? `--hue-${hue}` : "--map-route";
  return getComputedStyle(element).getPropertyValue(token).trim() || "transparent";
}

function style(tiles: string, glyphs: string, element: Element, hue?: number): maplibre.StyleSpecification {
  const palette = readAreaPalette(element);
  return {
    version: 8,
    glyphs: `${glyphs}fonts/{fontstack}/{range}.pbf`,
    sources: {
      streets: { type: "vector", tiles: [tiles], maxzoom: 15, attribution: "© OpenStreetMap · Protomaps" },
      route: { type: "geojson", data: EMPTY_LINE },
    },
    layers: [
      { id: "paper", type: "background", paint: { "background-color": palette.paper } },
      ...streetLayers("streets", palette),
      {
        id: "route-halo",
        type: "line",
        source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": palette.halo, "line-width": 7 },
      },
      {
        id: "route",
        type: "line",
        source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": routeColor(element, hue), "line-width": 4 },
      },
      ...labelLayers("streets", palette),
    ],
  };
}

export function boundsOf(stops: StreetStop[], line: [number, number][] | null): [[number, number], [number, number]] | null {
  const points: [number, number][] = [...stops.map((one) => [one.lon, one.lat] as [number, number]), ...(line ?? [])];
  if (points.length < 2) return null;
  const lons = points.map((one) => one[0]);
  const lats = points.map((one) => one[1]);
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ];
}

export function StreetMap({
  tiles,
  glyphs,
  stops,
  line,
  selected = null,
  onSelect,
  label,
  lineHue,
  padding,
}: StreetMapProps) {
  const container = React.useRef<HTMLDivElement>(null);
  const [map, setMap] = React.useState<maplibre.Map | null>(null);
  const onSelectRef = React.useRef(onSelect);
  onSelectRef.current = onSelect;
  const hueRef = React.useRef(lineHue);
  hueRef.current = lineHue;
  const frameRef = React.useRef<() => void>(() => undefined);
  const movedRef = React.useRef(false);
  const absolute = React.useMemo(
    () => ({
      tiles: new URL(tiles.replace(/\{/g, "%7B").replace(/\}/g, "%7D"), window.location.href).href
        .replace(/%7B/g, "{")
        .replace(/%7D/g, "}"),
      glyphs: new URL(glyphs, window.location.href).href,
    }),
    [tiles, glyphs],
  );

  React.useEffect(() => {
    const element = container.current;
    if (!element) return;
    const created = new maplibre.Map({
      container: element,
      style: style(absolute.tiles, absolute.glyphs, element, hueRef.current),
      center: [0, 20],
      zoom: 1,
      maxZoom: 18,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      fadeDuration: 0,
    });
    created.addControl(new maplibre.AttributionControl({ compact: true }), "bottom-left");
    created.touchZoomRotate.disableRotation();
    created.keyboard.disableRotation();
    created.on("style.load", () => setMap(created));
    created.on("click", (event) => {
      if ((event.originalEvent.target as Element).closest(".maplibregl-marker")) return;
      onSelectRef.current?.(null);
    });
    created.on("dragstart", () => (movedRef.current = true));
    created.on("zoomstart", (event) => {
      if (event.originalEvent) movedRef.current = true;
    });
    const resize = new ResizeObserver(() => {
      created.resize();
      if (!movedRef.current) frameRef.current();
    });
    resize.observe(element);
    const repaint = () => created.setStyle(style(absolute.tiles, absolute.glyphs, element, hueRef.current));
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
  }, [absolute]);

  React.useEffect(() => {
    if (!map) return;
    const source = map.getSource("route") as maplibre.GeoJSONSource | undefined;
    source?.setData(
      line && line.length > 1
        ? { ...EMPTY_LINE, geometry: { type: "LineString", coordinates: line } }
        : EMPTY_LINE,
    );
  }, [map, line]);

  React.useEffect(() => {
    const element = container.current;
    if (!map || !element || !map.getLayer("route")) return;
    map.setPaintProperty("route", "line-color", routeColor(element, lineHue));
  }, [map, lineHue]);

  React.useEffect(() => {
    if (!map) return;
    const markers = stops.map((stop) => {
      const mark = document.createElement("button");
      mark.type = "button";
      mark.className = "street-map-stop";
      mark.dataset.home = stop.number === null && !stop.quiet ? "true" : "false";
      if (stop.hue) mark.dataset.hue = String(stop.hue);
      if (stop.quiet) mark.dataset.quiet = "true";
      if (stop.id === selected) mark.dataset.selected = "true";
      mark.textContent = stop.quiet ? "" : stop.number === null ? "⌂" : String(stop.number);
      mark.setAttribute(
        "aria-label",
        stop.quiet ? stop.title : stop.number === null ? `Alojamiento: ${stop.title}` : `${stop.number}. ${stop.title}`,
      );
      mark.addEventListener("click", () => onSelectRef.current?.(stop.id));
      return new maplibre.Marker({ element: mark }).setLngLat([stop.lon, stop.lat]).addTo(map);
    });
    return () => markers.forEach((one) => one.remove());
  }, [map, stops, selected]);

  const key = stops.map((one) => `${one.lon},${one.lat}`).join(";");
  React.useEffect(() => {
    if (!map) return;
    frameRef.current = () => {
      const box = boundsOf(stops, line);
      const around = padding ?? { top: 48, bottom: 48, left: 48, right: 48 };
      const canvas = map.getCanvas();
      if (canvas.clientHeight <= around.top + around.bottom + 40) return;
      if (box) map.fitBounds(box, { padding: around, maxZoom: 16, duration: 0 });
      else if (stops[0]) map.jumpTo({ center: [stops[0].lon, stops[0].lat], zoom: 15 });
    };
    movedRef.current = false;
    frameRef.current();
  }, [map, key, line]);

  return (
    <div className="area-map street-map">
      <div ref={container} className="area-map-canvas" role="region" aria-label={label} />
    </div>
  );
}
