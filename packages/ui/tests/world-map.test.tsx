import { readFileSync } from "node:fs";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MapFigures, TimeBar, partOf } from "../src/world-map";

describe("la barra de tiempo", () => {
  const markup = (value: [number, number], playing = false) =>
    renderToStaticMarkup(
      <TimeBar min={2016} max={2026} value={value} onChange={() => {}} playing={playing} onPlay={() => {}} onPause={() => {}} />,
    );

  it("son dos tiradores con nombre y el tramo elegido pintado entre ellos", () => {
    const html = markup([2018, 2023]);

    expect(html).toContain('aria-label="Desde"');
    expect(html).toContain('aria-label="Hasta"');
    expect(html).toContain("--from:20%");
    expect(html).toContain("--to:70%");
  });

  it("el botón dice lo que va a hacer", () => {
    expect(markup([2016, 2026])).toContain("Reproducir los viajes en orden");
    expect(markup([2016, 2026], true)).toContain('aria-label="Pausar"');
  });

  it("sin reproducir que ofrecer no hay botón: la barra solo filtra", () => {
    const html = renderToStaticMarkup(<TimeBar min={2016} max={2026} value={[2016, 2026]} onChange={() => {}} />);

    expect(html).not.toContain("time-bar-play");
    expect(html).toContain('aria-label="Desde"');
  });

  it("con un solo año no hay rango que mover", () => {
    const html = renderToStaticMarkup(
      <TimeBar min={2025} max={2025} value={[2025, 2025]} onChange={() => {}} playing={false} onPlay={() => {}} onPause={() => {}} />,
    );

    expect(html.match(/disabled=""/g)).toHaveLength(2);
  });
});

describe("las cifras", () => {
  it("cada una es un término con su valor", () => {
    const html = renderToStaticMarkup(<MapFigures figures={[{ label: "Países", value: "12" }]} />);

    expect(html).toContain("<dt>Países</dt><dd>12</dd>");
  });
});

describe("una ruta a medias", () => {
  const line = {
    type: "LineString" as const,
    coordinates: Array.from({ length: 11 }, (_, i) => [i, 0]),
  };

  it("crece con el progreso y acaba entera", () => {
    expect(partOf(line, 0.5).coordinates).toHaveLength(6);
    expect(partOf(line, 1)).toBe(line);
    expect(partOf(line, 0).coordinates.length).toBeGreaterThanOrEqual(2);
  });
});

describe("ningún color sale del componente", () => {
  it("el mapa no escribe un solo color: todos son tokens --map-*", () => {
    const source = readFileSync(new URL("../src/world-map.tsx", import.meta.url), "utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");

    expect(code).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(code.match(/rgba?\([^)]*\)/g) ?? []).toEqual(["rgb(${r}, ${g}, ${bl})", "rgba(0, 0, 0, 0)"]);
  });

  it("los tokens del mapa existen en claro y en los dos oscuros", () => {
    const tokens = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");

    for (const token of ["--map-water", "--map-slept-high", "--map-home", "--map-route", "--map-selected"]) {
      expect(tokens.match(new RegExp(`${token}:`, "g"))).toHaveLength(3);
    }
  });
});
