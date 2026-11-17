import { readFileSync } from "node:fs";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MapFigures, TimeBar, partOf } from "../src/world-map";

describe("the time bar", () => {
  const markup = (value: [number, number], playing = false) =>
    renderToStaticMarkup(
      <TimeBar min={2016} max={2026} value={value} onChange={() => {}} playing={playing} onPlay={() => {}} onPause={() => {}} />,
    );

  it("they are two named handles with the chosen span drawn between them", () => {
    const html = markup([2018, 2023]);

    expect(html).toContain('aria-label="Desde"');
    expect(html).toContain('aria-label="Hasta"');
    expect(html).toContain("--from:20%");
    expect(html).toContain("--to:70%");
  });

  it("the button says what it will do", () => {
    expect(markup([2016, 2026])).toContain("Play the trips in order");
    expect(markup([2016, 2026], true)).toContain('aria-label="Pause"');
  });

  it("with nothing to play there is no button: the bar only filters", () => {
    const html = renderToStaticMarkup(<TimeBar min={2016} max={2026} value={[2016, 2026]} onChange={() => {}} />);

    expect(html).not.toContain("time-bar-play");
    expect(html).toContain('aria-label="Desde"');
  });

  it("with a single year there is no range to move", () => {
    const html = renderToStaticMarkup(
      <TimeBar min={2025} max={2025} value={[2025, 2025]} onChange={() => {}} playing={false} onPlay={() => {}} onPause={() => {}} />,
    );

    expect(html.match(/disabled=""/g)).toHaveLength(2);
  });
});

describe("the figures", () => {
  it("each one is a term with its value", () => {
    const html = renderToStaticMarkup(<MapFigures figures={[{ label: "Countries", value: "12" }]} />);

    expect(html).toContain("<dt>Countries</dt><dd>12</dd>");
  });
});

describe("a half route", () => {
  const line = {
    type: "LineString" as const,
    coordinates: Array.from({ length: 11 }, (_, i) => [i, 0]),
  };

  it("grows with progress and ends full", () => {
    expect(partOf(line, 0.5).coordinates).toHaveLength(6);
    expect(partOf(line, 1)).toBe(line);
    expect(partOf(line, 0).coordinates.length).toBeGreaterThanOrEqual(2);
  });
});

describe("no colour comes from the component", () => {
  it("the map writes no colour itself: all are --map-* tokens", () => {
    const source = readFileSync(new URL("../src/world-map.tsx", import.meta.url), "utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");

    expect(code).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(code.match(/rgba?\([^)]*\)/g) ?? []).toEqual(["rgb(${r}, ${g}, ${bl})", "rgba(0, 0, 0, 0)"]);
  });

  it("the map tokens exist in light and both darks", () => {
    const tokens = readFileSync(new URL("../tokens.css", import.meta.url), "utf8");

    for (const token of ["--map-water", "--map-slept-high", "--map-home", "--map-route", "--map-selected"]) {
      expect(tokens.match(new RegExp(`${token}:`, "g"))).toHaveLength(3);
    }
  });
});
