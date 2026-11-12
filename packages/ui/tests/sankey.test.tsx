import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Sankey, sankeyLayout } from "../src/index";

const nodes = [
  { id: "salary", name: "Nómina", column: 0, kind: "income" as const },
  { id: "me", name: "Tú", column: 1, kind: "you" as const },
  { id: "rent", name: "Alquiler", column: 2, kind: "expense" as const },
  { id: "food", name: "Súper", column: 2, kind: "expense" as const },
];
const links = [
  { source: "salary", target: "me", value: 2000 },
  { source: "me", target: "rent", value: 1500 },
  { source: "me", target: "food", value: 500 },
];

describe("el diagrama de flujo", () => {
  const { placed, bands } = sankeyLayout(nodes, links);
  const at = (id: string) => placed.find((node) => node.id === id)!;

  it("con menos alto por nudo, el diagrama entero es más bajo", () => {
    const crowded = Array.from({ length: 12 }, (_, i) => ({ id: `x${i}`, name: `X${i}`, column: 2, kind: "expense" as const }));
    const many = [...nodes, ...crowded];
    const out = [...links, ...crowded.map((n) => ({ source: "me", target: n.id, value: 10 }))];
    expect(sankeyLayout(many, out, 28).height).toBeLessThan(sankeyLayout(many, out).height);
  });

  it("una cantidad mide lo mismo en cualquier columna", () => {
    expect(at("salary").height).toBeCloseTo(at("me").height);
    expect(at("rent").height / at("food").height).toBeCloseTo(3);
  });

  it("las bandas que salen de un nudo van una bajo otra, sin pisarse", () => {
    const out = bands.filter((band) => band.source.id === "me").sort((a, b) => a.from - b.from);
    expect(out[1]!.from - out[0]!.from).toBeCloseTo((out[0]!.width + out[1]!.width) / 2);
  });

  it("cada banda dice de dónde a dónde y cuánto, y hay tabla", () => {
    const html = renderToStaticMarkup(<Sankey label="Flujo" nodes={nodes} links={links} format={(v) => `${v} €`} />);
    expect(html).toContain("<title>Tú → Alquiler: 1500 €</title>");
    expect(html).toContain("<summary>Ver como tabla</summary>");
    expect(html).toContain('data-kind="income"');
  });

  it("sin nada que enseñar lo dice", () => {
    expect(renderToStaticMarkup(<Sankey label="x" nodes={[]} links={[]} />)).toContain("Sin movimientos");
  });
});

describe("las ramas", () => {
  it("las hojas van junto a su rama, y dentro de ella por importe", () => {
    const tree = [
      { id: "me", name: "Tú", column: 0, kind: "you" as const },
      { id: "spent", name: "Gasto", column: 1, kind: "expense" as const },
      { id: "saved", name: "Ahorro", column: 1, kind: "saving" as const },
      { id: "fun", name: "Ocio", column: 2, kind: "expense" as const },
      { id: "fund", name: "Fondo", column: 2, kind: "saving" as const },
      { id: "food", name: "Súper", column: 2, kind: "expense" as const },
    ];
    const edges = [
      { source: "me", target: "spent", value: 700 },
      { source: "me", target: "saved", value: 600 },
      { source: "spent", target: "fun", value: 200 },
      { source: "spent", target: "food", value: 500 },
      { source: "saved", target: "fund", value: 600 },
    ];
    const { placed } = sankeyLayout(tree, edges);
    const order = placed.filter((node) => node.column === 2).sort((a, b) => a.y - b.y).map((node) => node.id);
    expect(order).toEqual(["food", "fun", "fund"]);
  });
});

