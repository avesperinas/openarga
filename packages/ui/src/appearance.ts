import type * as React from "react";

import type { AppNameSet } from "./app-names";
import collection from "../wallpapers.json";
import { say } from "./words";

export interface Wallpaper {
  id: string;
  name: string;
  luminance: { mean: number; variance: number };
  scrim: { light: number; dark: number };
  veil?: { light: number; dark: number };
  glass?: { light: number; dark: number };
  contrast: { light: number; dark: number };
  focus?: { x: number; y: number } | null;
  image: string;
  blurred: string;
  sources?: { type: string; srcset: string }[] | null;
  thumb?: string | null;
  aspect?: number | null;
}

export const WALLPAPERS = collection as Wallpaper[];

export const wallpaperOf = (id: string, mine: Wallpaper[] = []): Wallpaper =>
  mine.find((entry) => entry.id === id) ??
  WALLPAPERS.find((entry) => entry.id === id) ??
  WALLPAPERS[0]!;

export const focusOf = (wallpaper: Wallpaper): string => {
  const focus = wallpaper.focus ?? { x: 0.5, y: 0.5 };
  return `${Math.round(focus.x * 100)}% ${Math.round(focus.y * 100)}%`;
};

export const wallpaperSizes = (wallpaper: Wallpaper): string =>
  wallpaper.aspect ? `max(100vw, ${Math.ceil(wallpaper.aspect * 100)}vh)` : "100vw";

export const LIGHT_PHOTO = 0.4;
export const wallpaperInk = (wallpaper: Wallpaper) =>
  wallpaper.luminance.mean > LIGHT_PHOTO
    ? { ink: "#1c1c1e", shadow: "0 1px 2px rgb(255 255 255 / 0.5)" }
    : { ink: "#ffffff", shadow: "0 1px 3px rgb(0 0 0 / 0.45)" };

export const wallpaperStyle = (wallpaper: Wallpaper) =>
  ({
    "--wallpaper-ink": wallpaperInk(wallpaper).ink,
    "--wallpaper-ink-shadow": wallpaperInk(wallpaper).shadow,
    "--wallpaper-image": wallpaper.sources?.length ? "none" : `url(${wallpaper.image})`,
    "--wallpaper-blurred": `url(${wallpaper.blurred})`,
    "--wallpaper-focus": focusOf(wallpaper),
    "--wallpaper-scrim-light": wallpaper.scrim.light,
    "--wallpaper-scrim-dark": wallpaper.scrim.dark,
    "--wallpaper-middle-light": wallpaper.veil?.light ?? wallpaper.scrim.light,
    "--wallpaper-middle-dark": wallpaper.veil?.dark ?? wallpaper.scrim.dark,
    "--wallpaper-glass-light": wallpaper.glass?.light ?? 0,
    "--wallpaper-glass-dark": wallpaper.glass?.dark ?? 0,
  }) as React.CSSProperties;

export const APP_HUES: Record<string, number> = {
  recipes: 7,
  study: 6,
  money: 2,
  hub: 6,
  planner: 6,
  outings: 7,
  travel: 8,
  library: 5,
  macros: 4,
  shopping: 1,
  notebook: 3,
  vitals: 5,
  goals: 3,
  training: 4,
};

export type AppBackground = "app" | "plain" | `hue-${1 | 2 | 3 | 4 | 5 | 6 | 7 | 8}`;

export const APP_BACKGROUNDS: { value: AppBackground; label: string }[] = [
  { value: "app", get label() { return say("background.app"); } },
  { value: "plain", get label() { return say("background.plain"); } },
  { value: "hue-1", get label() { return say("colour.blue"); } },
  { value: "hue-2", get label() { return say("colour.green"); } },
  { value: "hue-3", get label() { return say("colour.amber"); } },
  { value: "hue-4", get label() { return say("colour.red"); } },
  { value: "hue-5", get label() { return say("colour.violet"); } },
  { value: "hue-6", get label() { return say("colour.teal"); } },
  { value: "hue-7", get label() { return say("colour.pink"); } },
  { value: "hue-8", get label() { return say("colour.slate"); } },
];

const isBackground = (value: unknown): value is AppBackground =>
  APP_BACKGROUNDS.some((one) => one.value === value);

export const backgroundOf = (app: string, preferences: Partial<UiPreferences>): AppBackground => {
  const chosen = preferences.app_backgrounds?.[app];
  return isBackground(chosen) ? chosen : "app";
};

const HUE_TOKENS = [
  "var(--hue-1)",
  "var(--hue-2)",
  "var(--hue-3)",
  "var(--hue-4)",
  "var(--hue-5)",
  "var(--hue-6)",
  "var(--hue-7)",
  "var(--hue-8)",
];

export const backgroundStyle = (app: string, background: AppBackground) => {
  const hue = background === "app" ? APP_HUES[app] : background.startsWith("hue-") ? Number(background.slice(4)) : null;
  const token = hue ? HUE_TOKENS[hue - 1] : undefined;
  return (token ? { "--app-background-hue": token } : {}) as React.CSSProperties;
};

export const STORAGE_KEY = "arga:ui";

export interface UiPreferences {
  glass_opacity: number;
  theme: "system" | "light" | "dark";
  wallpaper: string;
  app_wallpapers?: Record<string, string>;
  app_backgrounds?: Record<string, AppBackground>;
  app_names?: AppNameSet;
  custom_app_names?: Record<string, string>;
  icon_style?: IconStyle;
  home_panels?: { order?: string[]; hidden?: string[]; placed?: string[] };
}

export type IconStyle = "solid" | "ink" | "paper";

export const ICON_STYLES: { value: IconStyle; label: string; hint: string }[] = [
  { value: "solid", get label() { return say("icon_style.solid"); }, get hint() { return say("icon_style.solid.hint"); } },
  { value: "ink", get label() { return say("icon_style.ink"); }, get hint() { return say("icon_style.ink.hint"); } },
  { value: "paper", get label() { return say("icon_style.paper"); }, get hint() { return say("icon_style.paper.hint"); } },
];

export function styledIcon(src: string, style: IconStyle | undefined): string {
  return style ? src.replace(/\/icon\.svg(?=\?|$)/, `/icon-${style}.svg`) : src;
}

export const OPACITY_RANGE = { min: 0.35, max: 1, step: 0.05 };

export const FIRST_PAINT = `
try {
  var saved = JSON.parse(localStorage.getItem(${JSON.stringify(STORAGE_KEY)}) || "{}");
  var root = document.documentElement;
  if (saved.theme === "light" || saved.theme === "dark") root.dataset.theme = saved.theme;
  if (typeof saved.glass_opacity === "number") {
    root.style.setProperty("--glass-opacity", saved.glass_opacity);
    if (saved.glass_opacity >= 1) root.dataset.opaque = "true";
  }
} catch (e) {}
`.trim();

export function remember(preferences: UiPreferences): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  } catch {
  }
}

export function apply(preferences: UiPreferences): void {
  const root = document.documentElement;
  if (preferences.theme === "system") delete root.dataset.theme;
  else root.dataset.theme = preferences.theme;

  root.style.setProperty("--glass-opacity", String(preferences.glass_opacity));
  if (preferences.glass_opacity >= 1) root.dataset.opaque = "true";
  else delete root.dataset.opaque;
}

export function remembered(): Partial<UiPreferences> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") as Partial<UiPreferences>;
  } catch {
    return {};
  }
}
