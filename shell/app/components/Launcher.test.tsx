import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ModuleSummary } from "../lib/kernel";
import { Launcher, orderModules } from "./Launcher";

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
  const names = (html: string) => [...html.matchAll(/launcher-name">([^<]+)</g)].map((match) => match[1]);

  it("one grid, family after family, with the calendar first and System last", () => {
    expect(orderModules(installed).map((m) => m.id)).toEqual([
      "planner",
      "training",
      "vitals",
      "shopping",
      "money",
      "study",
      "travel",
      "newcomer",
      "hub",
    ]);
  });

  it("inside a family, what is used every day goes first, whatever the language", () => {
    const health = [app("recipes", "Recetas", "health"), app("vitals", "Constantes", "health"), app("macros", "Macros", "health")];

    expect(orderModules(health).map((m) => m.id)).toEqual(["macros", "vitals", "recipes"]);
  });

  it("an app with an unknown family is not lost: it goes before System", () => {
    const ids = orderModules([...installed, app("atlas", "Atlas", "world")]).map((m) => m.id);

    expect(ids.slice(-3)).toEqual(["atlas", "newcomer", "hub"]);
  });

  it("the companion is one more app in the grid, with its dot when there is something unseen", () => {
    const insights = { ...app("insights", "Insights", "companion"), badge: "/api/insights/badge" };
    const html = renderToStaticMarkup(<Launcher modules={[...installed, insights]} />);

    expect(names(html)).toContain("Insights");
    expect(names(html).indexOf("Insights")).toBeGreaterThan(names(html).indexOf("Travel"));
    expect(html).not.toContain("launcher-dot");
  });

  it("the search sits alone above the grid", () => {
    const html = renderToStaticMarkup(
      <Launcher modules={installed} search={<button className="launcher-search" aria-label="Buscar en arga" />} />,
    );

    expect(html).toMatch(/launcher-top"><button class="launcher-search".*launcher-all/);
    expect(names(html)[0]).toBe("Planner");
    expect(html).not.toContain("<h3");
  });

  it("each icon in the finish chosen in Settings; without a choice, colour (ADR-0170)", () => {
    const html = renderToStaticMarkup(<Launcher modules={installed} />);
    const ink = renderToStaticMarkup(<Launcher modules={installed} iconStyle="ink" />);

    expect(html).toContain('src="/vitals/icon-solid.svg?v=');
    expect(ink).toContain('src="/vitals/icon-ink.svg?v=');
    expect(ink).not.toContain("icon-solid.svg");
  });
});
