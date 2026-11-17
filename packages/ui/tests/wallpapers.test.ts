import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// @ts-expect-error -- untyped .mjs module: it is the definition, and the test measures it as is.
import { COLLECTION, FLOOR, MUTED_FLOOR, THEMES, VEIL_MAX, contrast, measure, rgb, samples } from "../wallpapers.mjs";

const css = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");
const manifest = JSON.parse(readFileSync(new URL("../wallpapers.json", import.meta.url), "utf8"));

const ids: string[] = COLLECTION.map((wallpaper: { id: string }) => wallpaper.id);

const foregrounds = [...css.matchAll(/--fg:\s*(#[0-9a-f]{6})/g)].map((match) => match[1]!);
const secondaries = [...css.matchAll(/--fg-muted:\s*(#[0-9a-f]{6})/g)].map((match) => match[1]!);
const tints = [...css.matchAll(/--glass-tint:\s*(\d+) (\d+) (\d+)/g)].map(
  (match) => "#" + match.slice(1, 4).map((n) => Number(n).toString(16).padStart(2, "0")).join(""),
);

const over = (source: number[], backdrop: number[], alpha: number) =>
  backdrop.map((value, index) => source[index]! * alpha + value * (1 - alpha));

describe("the system computes the scrim", () => {
  it("the colours measured are the ones tokens.css declares", () => {
    expect(foregrounds[0]).toBe(THEMES.light.fg);
    expect(foregrounds.slice(1)).toContain(THEMES.dark.fg);
    expect(foregrounds.slice(1).every((value) => value === THEMES.dark.fg)).toBe(true);
  });

  it("the secondary text measured is the one tokens.css declares", () => {
    expect(secondaries[0]).toBe(THEMES.light.muted);
    expect(secondaries.slice(1).every((value) => value === THEMES.dark.muted)).toBe(true);
  });

  it("the glass measured is the one tokens.css declares", () => {
    expect(tints[0]).toBe(THEMES.light.glass);
    expect(tints.slice(1).every((value) => value === THEMES.dark.glass)).toBe(true);
  });

  it("the saved manifest is what measuring the collection gives today", () => {
    for (const wallpaper of COLLECTION) {
      const stored = manifest.find((entry: { id: string }) => entry.id === wallpaper.id);
      const { image, blurred, ...measured } = { ...stored };
      void image;
      void blurred;
      expect(measured).toEqual(measure(wallpaper));
    }
  });

  it("each wallpaper comes with its pre-blurred pair", () => {
    for (const entry of manifest) {
      expect(entry.blurred).toBe(`/wallpapers/${entry.id}-blur.svg`);
    }
  });
});

describe.each(["light", "dark"] as const)("real contrast in the %s theme", (theme) => {
  const fg = rgb(THEMES[theme].fg);
  const veil = rgb(THEMES[theme].scrim);

  it.each(ids)("%s reads at every point, not just on average", (id: string) => {
      const wallpaper = COLLECTION.find((w: { id: string }) => w.id === id)!;
      const alpha = manifest.find((entry: { id: string }) => entry.id === id)!.scrim[theme];

      const worst = samples(wallpaper).reduce(
        (low: number, point: number[]) => Math.min(low, contrast(fg, over(veil, point, alpha))),
        Infinity,
      );

    expect(worst).toBeGreaterThanOrEqual(FLOOR);
  });

  it.each(ids)("%s lets the photo show in the centre of the desktop", (id: string) => {
    const entry = manifest.find((candidate: { id: string }) => candidate.id === id)!;
    expect(entry.veil[theme]).toBeLessThanOrEqual(VEIL_MAX);
    expect(entry.veil[theme]).toBeLessThanOrEqual(entry.scrim[theme]);
  });

  it.each(ids)("%s reads through the glass with its floor, the secondary text too", (id: string) => {
    const wallpaper = COLLECTION.find((w: { id: string }) => w.id === id)!;
    const alpha = manifest.find((entry: { id: string }) => entry.id === id)!.glass[theme];
    const tint = rgb(THEMES[theme].glass);
    const through = (colour: number[]) =>
      samples(wallpaper).reduce(
        (low: number, point: number[]) => Math.min(low, contrast(colour, over(tint, point, alpha))),
        Infinity,
      );

    expect(through(fg)).toBeGreaterThanOrEqual(FLOOR);
    expect(through(rgb(THEMES[theme].muted))).toBeGreaterThanOrEqual(MUTED_FLOOR);
  });
});

const HARD = [
  ["un reflejo blanco quemado", { id: "a", name: "Faros de noche", base: "#05070c", blobs: [{ cx: 0.5, cy: 0.4, r: 0.35, color: "#fffbe8", alpha: 1 }] }],
  ["a photo in full light", { id: "b", name: "Beach at noon", base: "#f4efe2", blobs: [{ cx: 0.3, cy: 0.2, r: 0.6, color: "#ffffff", alpha: 0.9 }] }],
  ["nieve", { id: "c", name: "Nieve", base: "#ffffff", blobs: [] }],
  ["noche cerrada", { id: "d", name: "Noche", base: "#000000", blobs: [] }],
] as const;

describe("no photo is rejected for its colour", () => {
  it.each(HARD)("%s gets in, with what is needed to read on top", (_name, wallpaper) => {
    const measured = measure(wallpaper);

    expect(measured).not.toHaveProperty("rejected");
    for (const theme of ["light", "dark"] as const) {
      const fg = rgb(THEMES[theme].fg);
      const veil = rgb(THEMES[theme].scrim);
      const tint = rgb(THEMES[theme].glass);
      const points = samples(wallpaper);
      const through = (colour: number[], alpha: number) =>
        points.reduce(
          (low: number, point: number[]) => Math.min(low, contrast(fg, over(colour, point, alpha))),
          Infinity,
        );

      expect(through(veil, measured.scrim[theme])).toBeGreaterThanOrEqual(FLOOR);
      expect(through(tint, measured.glass[theme])).toBeGreaterThanOrEqual(FLOOR);
      const secondary = rgb(THEMES[theme].muted);
      expect(
        points.reduce(
          (low: number, point: number[]) =>
            Math.min(low, contrast(secondary, over(tint, point, measured.glass[theme]))),
          Infinity,
        ),
      ).toBeGreaterThanOrEqual(MUTED_FLOOR);
      expect(measured.veil[theme]).toBeLessThanOrEqual(VEIL_MAX);
    }
  });
});
