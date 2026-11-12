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

describe("la búsqueda global", () => {
  it("encuentra las apps por su nombre, sin tildes, primero las que empiezan así", () => {
    expect(appMatches(installed, "training").map((m) => m.id)).toEqual(["training"]);
    expect(appMatches(installed, "os").map((m) => m.id)).toEqual(["macros"]);
    expect(appMatches(installed, "on").map((m) => m.id)).toEqual(["money"]);
    expect(appMatches(installed, "  ")).toEqual([]);
  });

  it("funciona sin ninguna app que declare `ui.search`: solo las apps por nombre", () => {
    const groups = searchGroups(installed, "notas", []);

    expect(groups.map((g) => [g.label, g.items.map((i) => i.label)])).toEqual([["Apps", ["Notas"]]]);
  });

  it("lo de cada app sale con el nombre que le has puesto", () => {
    const groups = searchGroups(installed, "proteina", [
      { app: "notebook", name: "Notebook", results: [{ title: "Proteína", detail: "Nutrición", href: "/notebook/n/1" }] },
    ]);

    expect(groups.map((g) => g.label)).toEqual(["Apps", "Notas"]);
    expect(groups[1]?.items[0]).toMatchObject({ label: "Proteína", detail: "Nutrición" });
  });

  it("de lo que contesta una app solo se fía de lo que tiene forma y lleva dentro de arga", () => {
    const found = readFound({
      results: [
        { title: "Bien", href: "/notebook/n/1", detail: "Carpeta" },
        { title: "Fuera", href: "https://otro.ejemplo.com/" },
        { title: "Protocolo", href: "//otro.ejemplo.com/" },
        { title: "Script", href: "javascript:alert(1)" },
        { title: "", href: "/sin-titulo" },
        { href: "/sin-nada" },
        "basura",
      ],
    });

    expect(found).toEqual([{ title: "Bien", href: "/notebook/n/1", detail: "Carpeta" }]);
    expect(readFound(null)).toEqual([]);
    expect(readFound({ results: "no" })).toEqual([]);
  });

  it("no enseña más de ocho por app", () => {
    const many = Array.from({ length: 20 }, (_, n) => ({ title: `N${n}`, href: `/notebook/${n}` }));
    expect(readFound({ results: many })).toHaveLength(8);
  });

  it("la lupa de Módulos es solo el icono, y se llama como lo que hace", () => {
    const html = renderToStaticMarkup(<SearchField onOpen={() => undefined} />);
    expect(html).toContain('aria-label="Buscar en arga"');
    expect(html).toContain("<button");
    expect(html).not.toMatch(/>Buscar en arga</);
  });
});
