import { describe, expect, it } from "vitest";

import { pathOf, route } from "./routes";

describe("las direcciones", () => {
  it("cada pantalla va y vuelve", () => {
    const id = "0a0a0a0a-0000-4000-8000-00000000a0a0";
    for (const to of [
      { screen: "home" as const },
      { screen: "note" as const, id },
      { screen: "search" as const, q: "präfix", tag: "deutsch" },
      { screen: "trash" as const },
      { screen: "today" as const },
      { screen: "import" as const },
      { screen: "graph" as const },
      { screen: "review" as const },
      { screen: "settings" as const },
    ]) {
      const path = pathOf(to);
      const [pathname, search] = path.split("?");
      expect(route(pathname!, search ? `?${search}` : "")).toEqual(to);
    }
  });

  it("al abrir, y con lo que no conoce, el grafo; la lista de notas tiene su dirección", () => {
    expect(route("/notebook")).toEqual({ screen: "graph" });
    expect(route("/notebook/")).toEqual({ screen: "graph" });
    expect(route("/notebook/grafo")).toEqual({ screen: "graph" });
    expect(route("/notebook/nada")).toEqual({ screen: "graph" });
    expect(route("/notebook/notas")).toEqual({ screen: "home" });
  });
});
