import { describe, expect, it } from "vitest";

import { closeness, fold, ranked } from "./search";

describe("buscar sin tildes (T-V26)", () => {
  it("quita mayúsculas, tildes, diéresis y virgulilla", () => {
    expect(fold("Ñoquis de CALABAZA, pequeños, pingüino")).toBe("noquis de calabaza, pequenos, pinguino");
  });

  it("la misma escala que la API", () => {
    expect(closeness("platano", "Plátano")).toBe(0);
    expect(closeness("plat", "Plátano")).toBe(1);
    expect(closeness("plat", "Batido de plátano")).toBe(2);
    expect(closeness("tano", "Batido de plátano")).toBe(3);
    expect(closeness("kiwi", "Plátano")).toBeNull();
  });

  it("lo que empieza igual, antes; por el alias o por el nombre de la fuente", () => {
    const foods = [
      { alias: null, name: "Batido de plátano" },
      { alias: "Plátano", name: "Bananas, raw" },
      { alias: null, name: "Chocolate con plátano" },
      { alias: null, name: "Kiwi" },
    ];
    const label = (one: (typeof foods)[number]) => one.alias ?? one.name;
    expect(ranked(foods, "platano", (one) => [one.alias, one.name], label).map(label)).toEqual([
      "Plátano",
      "Batido de plátano",
      "Chocolate con plátano",
    ]);
    expect(ranked(foods, "banana", (one) => [one.alias, one.name], label).map(label)).toEqual(["Plátano"]);
  });
});
