import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// @ts-expect-error -- módulo .mjs sin tipos: es la definición, y el test la mide tal cual.
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

describe("el velo lo calcula el sistema", () => {
  it("los colores que mide son los que declara tokens.css", () => {
    expect(foregrounds[0]).toBe(THEMES.light.fg);
    expect(foregrounds.slice(1)).toContain(THEMES.dark.fg);
    expect(foregrounds.slice(1).every((value) => value === THEMES.dark.fg)).toBe(true);
  });

  it("el texto secundario que mide es el que declara tokens.css", () => {
    expect(secondaries[0]).toBe(THEMES.light.muted);
    expect(secondaries.slice(1).every((value) => value === THEMES.dark.muted)).toBe(true);
  });

  it("el cristal que mide es el que declara tokens.css", () => {
    expect(tints[0]).toBe(THEMES.light.glass);
    expect(tints.slice(1).every((value) => value === THEMES.dark.glass)).toBe(true);
  });

  it("el manifiesto guardado es lo que sale de medir la colección hoy", () => {
    for (const wallpaper of COLLECTION) {
      const stored = manifest.find((entry: { id: string }) => entry.id === wallpaper.id);
      const { image, blurred, ...measured } = { ...stored };
      void image;
      void blurred;
      expect(measured).toEqual(measure(wallpaper));
    }
  });

  it("cada fondo viene con su pareja pre-desenfocada", () => {
    for (const entry of manifest) {
      expect(entry.blurred).toBe(`/wallpapers/${entry.id}-blur.svg`);
    }
  });
});

describe.each(["light", "dark"] as const)("contraste real en tema %s", (theme) => {
  const fg = rgb(THEMES[theme].fg);
  const veil = rgb(THEMES[theme].scrim);

  it.each(ids)("%s se lee en todos sus puntos, no solo de media", (id: string) => {
      const wallpaper = COLLECTION.find((w: { id: string }) => w.id === id)!;
      const alpha = manifest.find((entry: { id: string }) => entry.id === id)!.scrim[theme];

      const worst = samples(wallpaper).reduce(
        (low: number, point: number[]) => Math.min(low, contrast(fg, over(veil, point, alpha))),
        Infinity,
      );

    expect(worst).toBeGreaterThanOrEqual(FLOOR);
  });

  it.each(ids)("%s deja ver la foto en el centro del escritorio", (id: string) => {
    const entry = manifest.find((candidate: { id: string }) => candidate.id === id)!;
    expect(entry.veil[theme]).toBeLessThanOrEqual(VEIL_MAX);
    expect(entry.veil[theme]).toBeLessThanOrEqual(entry.scrim[theme]);
  });

  it.each(ids)("%s se lee a través del cristal con su suelo, también lo secundario", (id: string) => {
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
  ["una foto a plena luz", { id: "b", name: "Playa al mediodía", base: "#f4efe2", blobs: [{ cx: 0.3, cy: 0.2, r: 0.6, color: "#ffffff", alpha: 0.9 }] }],
  ["nieve", { id: "c", name: "Nieve", base: "#ffffff", blobs: [] }],
  ["noche cerrada", { id: "d", name: "Noche", base: "#000000", blobs: [] }],
] as const;

describe("ninguna foto se rechaza por su color", () => {
  it.each(HARD)("%s entra, con lo que hace falta para leer encima", (_name, wallpaper) => {
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
