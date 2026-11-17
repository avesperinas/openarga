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
  app("newcomer", "Newcomer"),
  app("study", "Study", "growth"),
  app("travel", "Travel", "wellbeing"),
];

describe("the launcher by families", () => {
  it("puts the calendar apart, the families in their order and Finance and System as fillers", () => {
    const groups = groupModules(installed);

    expect(groups.pinned.map((m) => m.id)).toEqual(["planner"]);
    expect(groups.families.map((f) => [f.label, f.modules.map((m) => m.id)])).toEqual([
      ["Health", ["training", "vitals"]],
      ["Goals", ["shopping"]],
      ["Growth", ["study"]],
      ["Wellbeing", ["travel"]],
    ]);
    expect(groups.fillers.map((m) => m.id)).toEqual(["money", "hub", "newcomer"]);
  });

  it("an app with an old family is not lost: it fills after the others", () => {
    const groups = groupModules([...installed, app("library", "Library", "world")]);

    expect(groups.fillers.map((m) => m.id)).toEqual(["money", "hub", "library", "newcomer"]);
  });

  it("the calendar in its band, with the date, and not in the grid", () => {
    const html = renderToStaticMarkup(<Launcher modules={installed} />);

    expect(html).toMatch(/launcher-band".*launcher-band-name">Planner</);
    expect(html).toContain("launcher-band-date");
    const grid = html.slice(html.indexOf("launcher-all"));
    expect(grid).not.toContain(">Planner<");
  });

  it("a companion goes on the right of the band, icon only, and not in the grid", () => {
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

  it("the search glass goes in the band, between the calendar and the companion", () => {
    const insights = app("insights", "Insights", "companion");
    const html = renderToStaticMarkup(
      <Launcher modules={[...installed, insights]} search={<button className="launcher-search" aria-label="Buscar en arga" />} />,
    );
    const top = html.slice(html.indexOf("launcher-top"), html.indexOf("launcher-all"));
    expect(top).toMatch(/launcher-band".*launcher-search".*launcher-companion"/);
  });

  it("a single grid without titles: each family in its block, gaps filled", () => {
    const html = renderToStaticMarkup(<Launcher modules={installed} />);

    const order = ["Training", "Vitals", "Money", "Hub", "Shopping", "Newcomer", "Study", "Travel"];
    const found = [...html.matchAll(/launcher-name">([^<]+)</g)].map((match) => match[1]);
    expect(found).toEqual(order);
    expect(html).not.toContain("<h3");
  });

  it("each icon in the finish chosen in Settings; without a choice, colour (ADR-0170)", () => {
    const html = renderToStaticMarkup(<Launcher modules={installed} />);
    const ink = renderToStaticMarkup(<Launcher modules={installed} iconStyle="ink" />);

    expect(html).toContain('src="/vitals/icon-solid.svg?v=');
    expect(ink).toContain('src="/vitals/icon-ink.svg?v=');
    expect(ink).not.toContain("icon-solid.svg");
  });

  it("today's: 4 × 4 on the phone and 8 × 2 on the computer, with a gap for Outings", () => {
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

  it("with Outings, Wellbeing fills its row and Hub stays in its gap", () => {
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

  it("what does not fit in a gap opens a block at the end", () => {
    const { placed } = placeBlocks([[app("a", "A", "health"), app("b", "B", "health"), app("c", "C", "health"), app("d", "D", "health")]], [app("x", "X", "system")]);

    expect(placed.get("x")).toEqual({ phone: [1, 2], desktop: [5, 1] });
  });
});
