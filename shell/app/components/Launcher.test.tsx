import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ModuleSummary } from "../lib/kernel";
import { Launcher, groupModules, placeBlocks } from "./Launcher";

const app = (id: string, name: string, family?: string): ModuleSummary => ({
  id,
  name,
  version: "0.1.0",
  enabled: true,
  api_prefix: `/api/${id}`,
  view: `/${id}`,
  family,
  scopes: [],
  updated_at: "2026-09-28T00:00:00Z",
});

const installed = [
  app("vitals", "Vitals", "health"),
  app("hub", "Hub", "system"),
  app("training", "Training", "health"),
  app("planner", "Planner", "calendar"),
  app("money", "Money", "finance"),
  app("shopping", "Shopping", "goals"),
  app("nuevo", "Nuevo"),
  app("study", "Study", "growth"),
  app("travel", "Travel", "wellbeing"),
];

describe("el lanzador por familias", () => {
  it("pone el calendario aparte, las familias en su orden y Finanzas y Sistema de relleno", () => {
    const groups = groupModules(installed);

    expect(groups.pinned.map((m) => m.id)).toEqual(["planner"]);
    expect(groups.families.map((f) => [f.label, f.modules.map((m) => m.id)])).toEqual([
      ["Salud", ["training", "vitals"]],
      ["Objetivos", ["shopping"]],
      ["Crecimiento", ["study"]],
      ["Bienestar", ["travel"]],
    ]);
    expect(groups.fillers.map((m) => m.id)).toEqual(["money", "hub", "nuevo"]);
  });

  it("una app con una familia de antes no se pierde: rellena tras las demás", () => {
    const groups = groupModules([...installed, app("library", "Library", "world")]);

    expect(groups.fillers.map((m) => m.id)).toEqual(["money", "hub", "library", "nuevo"]);
  });

  it("el calendario en su banda, con la fecha, y no en la rejilla", () => {
    const html = renderToStaticMarkup(<Launcher modules={installed} />);

    expect(html).toMatch(/launcher-band".*launcher-band-name">Planner</);
    expect(html).toContain("launcher-band-date");
    const grid = html.slice(html.indexOf("launcher-all"));
    expect(grid).not.toContain(">Planner<");
  });

  it("quien acompaña va a la derecha de la banda, solo con su icono, y no en la rejilla", () => {
    const insights = { ...app("insights", "Insights", "companion"), badge: "/api/insights/badge" };
    const groups = groupModules([...installed, insights]);
    expect(groups.companions.map((m) => m.id)).toEqual(["insights"]);
    expect(groups.fillers.map((m) => m.id)).not.toContain("insights");

    const html = renderToStaticMarkup(<Launcher modules={[...installed, insights]} />);
    const top = html.slice(html.indexOf("launcher-top"), html.indexOf("launcher-all"));
    expect(top).toMatch(/launcher-band".*launcher-companion"[^>]*href="\/insights"[^>]*aria-label="Insights"/);
    expect(top).not.toContain(">Insights<");
    expect(top).not.toContain("launcher-companion-dot");
  });

  it("la lupa va en la banda, entre el calendario y quien acompaña", () => {
    const insights = app("insights", "Insights", "companion");
    const html = renderToStaticMarkup(
      <Launcher modules={[...installed, insights]} search={<button className="launcher-search" aria-label="Buscar en arga" />} />,
    );
    const top = html.slice(html.indexOf("launcher-top"), html.indexOf("launcher-all"));
    expect(top).toMatch(/launcher-band".*launcher-search".*launcher-companion"/);
  });

  it("una sola rejilla sin títulos: cada familia en su bloque, huecos rellenos", () => {
    const html = renderToStaticMarkup(<Launcher modules={installed} />);

    const order = ["Training", "Vitals", "Money", "Hub", "Shopping", "Nuevo", "Study", "Travel"];
    const found = [...html.matchAll(/launcher-name">([^<]+)</g)].map((match) => match[1]);
    expect(found).toEqual(order);
    expect(html).not.toContain("<h3");
  });

  it("cada icono en el acabado elegido en Ajustes; sin elegir, el de color (ADR-0170)", () => {
    const html = renderToStaticMarkup(<Launcher modules={installed} />);
    const ink = renderToStaticMarkup(<Launcher modules={installed} iconStyle="ink" />);

    expect(html).toContain('src="/vitals/icon-solid.svg?v=');
    expect(ink).toContain('src="/vitals/icon-ink.svg?v=');
    expect(ink).not.toContain("icon-solid.svg");
  });

  it("las de hoy: 4 × 4 en el móvil y 8 × 2 en el ordenador, con un hueco para Outings", () => {
    const named = (family: string, ...names: string[]) => names.map((name) => app(name, name, family));
    const { pinned, families, fillers } = groupModules([
      ...named("calendar", "Planner"),
      ...named("health", "Macros", "Vitals", "Training", "Recipes"),
      ...named("goals", "Pantry", "Goals", "Shopping"),
      ...named("growth", "Career", "Study", "Notebook"),
      ...named("wellbeing", "Travel", "Library"),
      ...named("finance", "Money"),
      ...named("system", "Pings", "Hub"),
    ]);

    const { order, placed } = placeBlocks(families.map((family) => family.modules), fillers);

    expect(pinned.map((m) => m.id)).toEqual(["Planner"]);
    expect(order.map((m) => m.id)).toEqual([
      "Macros", "Recipes", "Training", "Vitals",
      "Goals", "Pantry", "Shopping", "Money",
      "Career", "Notebook", "Study", "Hub",
      "Library", "Travel", "Pings",
    ]);
    expect(placed.get("Money")).toEqual({ phone: [4, 2], desktop: [8, 1] });
    expect(placed.get("Hub")).toEqual({ phone: [4, 3], desktop: [4, 2] });
  });

  it("con Outings, Bienestar llena su fila y Hub sigue en su hueco", () => {
    const named = (family: string, ...names: string[]) => names.map((name) => app(name, name, family));
    const { families, fillers } = groupModules([
      ...named("calendar", "Planner"),
      ...named("health", "Macros", "Vitals", "Training", "Recipes"),
      ...named("goals", "Pantry", "Goals", "Shopping"),
      ...named("growth", "Career", "Study", "Notebook"),
      ...named("wellbeing", "Travel", "Library", "Outings"),
      ...named("finance", "Money"),
      ...named("system", "Pings", "Hub"),
    ]);

    const { order } = placeBlocks(families.map((family) => family.modules), fillers);

    expect(order.map((m) => m.id).slice(-4)).toEqual(["Library", "Outings", "Travel", "Pings"]);
  });

  it("lo que no cabe en un hueco abre un bloque al final", () => {
    const { placed } = placeBlocks([[app("a", "A", "health"), app("b", "B", "health"), app("c", "C", "health"), app("d", "D", "health")]], [app("x", "X", "system")]);

    expect(placed.get("x")).toEqual({ phone: [1, 2], desktop: [5, 1] });
  });
});
