import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ModuleSummary } from "../lib/kernel";
import { appMatches, readFound } from "../lib/search";
import { SearchField, searchGroups } from "./Search";

const app = (id: string, name: string): ModuleSummary => ({
  id,
  name,
  version: "0.1.0",
  enabled: true,
  api_prefix: `/api/${id}`,
  view: `/${id}`,
  scopes: [],
  updated_at: "2026-10-29T00:00:00Z",
});

const installed = [app("training", "Training"), app("notebook", "Notas"), app("money", "Money"), app("macros", "Macros")];

describe("global search", () => {
  it("finds apps by name, ignoring accents, those that start that way first", () => {
    expect(appMatches(installed, "training").map((m) => m.id)).toEqual(["training"]);
    expect(appMatches(installed, "os").map((m) => m.id)).toEqual(["macros"]);
    expect(appMatches(installed, "on").map((m) => m.id)).toEqual(["money"]);
    expect(appMatches(installed, "  ")).toEqual([]);
  });

  it("works with no app declaring `ui.search`: only the apps by name", () => {
    const groups = searchGroups(installed, "notas", []);

    expect(groups.map((g) => [g.label, g.items.map((i) => i.label)])).toEqual([["Apps", ["Notas"]]]);
  });

  it("each app's results show with the name you gave it", () => {
    const groups = searchGroups(installed, "proteina", [
      { app: "notebook", name: "Notebook", results: [{ title: "Protein", detail: "Nutrition", href: "/notebook/n/1" }] },
    ]);

    expect(groups.map((g) => g.label)).toEqual(["Apps", "Notas"]);
    expect(groups[1]?.items[0]).toMatchObject({ label: "Protein", detail: "Nutrition" });
  });

  it("of what an app answers it trusts only what is well formed and stays inside arga", () => {
    const found = readFound({
      results: [
        { title: "Bien", href: "/notebook/n/1", detail: "Carpeta" },
        { title: "Fuera", href: "https://otro.ejemplo.com/" },
        { title: "Protocolo", href: "//otro.ejemplo.com/" },
        { title: "Script", href: "javascript:alert(1)" },
        { title: "", href: "/untitled" },
        { href: "/nothing" },
        "basura",
      ],
    });

    expect(found).toEqual([{ title: "Bien", href: "/notebook/n/1", detail: "Carpeta" }]);
    expect(readFound(null)).toEqual([]);
    expect(readFound({ results: "no" })).toEqual([]);
  });

  it("shows no more than eight per app", () => {
    const many = Array.from({ length: 20 }, (_, n) => ({ title: `N${n}`, href: `/notebook/${n}` }));
    expect(readFound({ results: many })).toHaveLength(8);
  });

  it("the Modules search glass is only the icon, and is named for what it does", () => {
    const html = renderToStaticMarkup(<SearchField onOpen={() => undefined} />);
    expect(html).toContain('aria-label="Search arga"');
    expect(html).toContain("<button");
    expect(html).not.toMatch(/>Search arga</);
  });
});
