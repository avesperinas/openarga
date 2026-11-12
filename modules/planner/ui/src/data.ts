import { invalidate, mutate, useResource } from "@openarga/app";
import type { CalendarEvent } from "@openarga/ui";
import * as React from "react";

import { type Layer, type Occurrence, readLayers, readOccurrences } from "./api";

export interface CalendarData {
  layers: Layer[];
  occurrences: Occurrence[];
  loading: boolean;
  failed: boolean;
  error: string | null;
  reload: () => Promise<void>;
  setLayers: React.Dispatch<React.SetStateAction<Layer[]>>;
}

export const LAYERS_KEY = "calendars";
const OCCURRENCES = "occurrences:";

export function windowKey(from: Date, to: Date, home: string | null): string {
  if (home) return `${OCCURRENCES}now:${home}`;
  return `${OCCURRENCES}${from.toISOString()}/${to.toISOString()}`;
}

const message = (error: Error | null) => (error ? error.message : null);

export function useCalendarData(from: Date, to: Date, home: string | null): CalendarData {
  const fromTime = from.getTime();
  const toTime = to.getTime();
  const key = windowKey(from, to, home);
  const layers = useResource(LAYERS_KEY, readLayers, { persist: true });
  const last = React.useRef<Occurrence[] | undefined>(undefined);
  const occurrences = useResource(key, () => readOccurrences(new Date(fromTime), new Date(toTime)), {
    persist: home !== null,
    initial: () => last.current,
  });
  if (occurrences.data !== undefined) last.current = occurrences.data;

  const asked = React.useRef({ key, fromTime });
  const { refresh } = occurrences;
  React.useEffect(() => {
    const before = asked.current;
    asked.current = { key, fromTime };
    if (before.key === key && before.fromTime !== fromTime) void refresh();
  }, [key, fromTime, refresh]);

  const reload = React.useCallback(async () => {
    invalidate(OCCURRENCES);
    invalidate(LAYERS_KEY);
  }, []);

  const setLayers = React.useCallback<React.Dispatch<React.SetStateAction<Layer[]>>>((next) => {
    void mutate<Layer[]>(LAYERS_KEY, (current) => (typeof next === "function" ? next(current ?? []) : next));
  }, []);

  const error = message(layers.error) ?? message(occurrences.error);
  return {
    layers: layers.data ?? [],
    occurrences: occurrences.data ?? [],
    loading: layers.loading || occurrences.loading,
    failed: error !== null && (layers.data === undefined || occurrences.data === undefined),
    error,
    reload,
    setLayers,
  };
}

export function toGridEvent(occurrence: Occurrence, layer: Layer | undefined, twinLayer?: string): CalendarEvent {
  return {
    id: occurrence.id,
    title: occurrence.title,
    start: occurrence.start,
    end: occurrence.end,
    allDay: occurrence.all_day,
    tone: layer?.tone ?? 8,
    subtitle: occurrence.location ?? undefined,
    status: occurrence.status === "cancelled" ? "cancelled" : "confirmed",
    readOnly: !isEditable(layer),
    subscribed: layer?.origin === "subscription",
    recurring: occurrence.original_start !== null,
    background: isBackground(layer),
    duplicateOf: twinLayer,
  };
}

export const isBackground = (layer: Layer | undefined): boolean => layer?.display === "background";

export const isEditable = (layer: Layer | undefined): boolean =>
  layer?.origin === "own" || (layer?.origin === "app" && !!layer.movable);

export function counts(occurrence: Occurrence, layer: Layer | undefined): boolean {
  return occurrence.all_day || !isBackground(layer);
}

export function usePreference<T>(key: string, initial: T): [T, (value: T) => void] {
  const [value, setValue] = React.useState<T>(() => {
    try {
      const stored = window.localStorage.getItem(key);
      return stored === null ? initial : (JSON.parse(stored) as T);
    } catch {
      return initial;
    }
  });
  const set = React.useCallback(
    (next: T) => {
      setValue(next);
      try {
        window.localStorage.setItem(key, JSON.stringify(next));
      } catch {
      }
    },
    [key],
  );
  return [value, set];
}

export function useWidth(): number {
  const [width, setWidth] = React.useState(() => (typeof window === "undefined" ? 1280 : window.innerWidth));
  React.useEffect(() => {
    const resize = () => setWidth(window.innerWidth);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  return width;
}

function words(title: string): Set<string> {
  const folded = title
    .toLocaleLowerCase("es")
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .replace(/[^\p{L}\p{N}]+/gu, " ");
  return new Set(folded.split(" ").filter((word) => word.length >= 4));
}

export function similar(a: string, b: string): boolean {
  const left = words(a);
  const right = words(b);
  if (left.size === 0 || right.size === 0) {
    const fold = (text: string) => text.toLocaleLowerCase("es").normalize("NFKD").replace(/[^\p{L}\p{N}]/gu, "");
    return fold(a) !== "" && fold(a) === fold(b);
  }
  const shared = [...left].filter((word) => right.has(word)).length;
  if (shared === left.size || shared === right.size) return true;
  return shared / Math.min(left.size, right.size) >= 0.5;
}

const minute = (value: string) => (value.length === 10 ? value : new Date(value).toISOString().slice(0, 16));

export function duplicatesOf(occurrences: Occurrence[], layers: Layer[]): Map<string, Occurrence> {
  const byId = new Map(layers.map((layer) => [layer.id, layer]));
  const others = occurrences.filter((one) => {
    const origin = byId.get(one.calendar_id)?.origin;
    return (origin === "app" || origin === "subscription") && one.status !== "cancelled";
  });
  const found = new Map<string, Occurrence>();
  for (const one of occurrences) {
    if (byId.get(one.calendar_id)?.origin !== "own" || one.status === "cancelled") continue;
    const twin = others.find(
      (other) => minute(other.start) === minute(one.start) && minute(other.end) === minute(one.end) && similar(other.title, one.title),
    );
    if (twin) found.set(one.id, twin);
  }
  return found;
}

export interface AppGroup {
  app: string;
  name: string;
  layers: Layer[];
}

export const appOf = (layer: Layer): string => (layer.app ?? "").split(":")[0] ?? "";

export function shortName(layer: Layer, appName: string): string {
  const prefix = `${appName} · `;
  if (layer.name.startsWith(prefix)) return layer.name.slice(prefix.length);
  const cut = layer.name.indexOf(" · ");
  return cut > 0 ? layer.name.slice(cut + 3) : layer.name;
}

export function sidebarGroups(layers: Layer[], appNames: Record<string, string> = {}) {
  const daysOff = new Set(layers.flatMap((layer) => layer.days_off_from ?? []));
  const holiday = (layer: Layer) => layer.origin !== "app" && daysOff.has(layer.id);
  const own = layers.filter((layer) => layer.origin === "own" && !holiday(layer));
  const holidays = layers.filter(holiday);
  const subscriptions = layers.filter((layer) => layer.origin === "subscription" && !holiday(layer));
  const apps: AppGroup[] = [];
  for (const layer of layers.filter((one) => one.origin === "app")) {
    const app = appOf(layer);
    let group = apps.find((one) => one.app === app);
    if (!group) {
      const fallback = layer.name.split(" · ")[0] ?? app;
      group = { app, name: appNames[app] ?? fallback, layers: [] };
      apps.push(group);
    }
    group.layers.push(layer);
  }
  const holidayIds = new Set(holidays.map((layer) => layer.id));
  const resting = layers.filter((layer) => (layer.days_off_from ?? []).some((id) => holidayIds.has(id))).map((layer) => layer.name);
  return { own, holidays, subscriptions, apps, resting };
}
