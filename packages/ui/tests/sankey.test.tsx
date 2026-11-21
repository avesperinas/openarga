import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Sankey, sankeyLayout } from "../src/index";

const nodes = [
  { id: "salary", name: "Salary", column: 0, kind: "income" as const },
  { id: "me", name: "You", column: 1, kind: "you" as const },
  { id: "rent", name: "Rent", column: 2, kind: "expense" as const },
  { id: "food", name: "Groceries", column: 2, kind: "expense" as const },
];
const links = [
  { source: "salary", target: "me", value: 2000 },
  { source: "me", target: "rent", value: 1500 },
  { source: "me", target: "food", value: 500 },
];

describe("the flow diagram", () => {
  const { placed, bands } = sankeyLayout(nodes, links);
  const at = (id: string) => placed.find((node) => node.id === id)!;

  it("with less height per node, the whole diagram is shorter", () => {
    const crowded = Array.from({ length: 12 }, (_, i) => ({ id: `x${i}`, name: `X${i}`, column: 2, kind: "expense" as const }));
    const many = [...nodes, ...crowded];
    const out = [...links, ...crowded.map((n) => ({ source: "me", target: n.id, value: 10 }))];
    expect(sankeyLayout(many, out, 28).height).toBeLessThan(sankeyLayout(many, out).height);
  });

  it("an amount has the same width in any column", () => {
    expect(at("salary").height).toBeCloseTo(at("me").height);
    expect(at("rent").height / at("food").height).toBeCloseTo(3);
  });

  it("the bands leaving a node stack one under another, without overlapping", () => {
    const out = bands.filter((band) => band.source.id === "me").sort((a, b) => a.from - b.from);
    expect(out[1]!.from - out[0]!.from).toBeCloseTo((out[0]!.width + out[1]!.width) / 2);
  });

  it("each band says from where to where and how much, and there is a table", () => {
    const html = renderToStaticMarkup(<Sankey label="Flujo" nodes={nodes} links={links} format={(v) => `${v} €`} />);
    expect(html).toContain("<title>You → Rent: 1500 €</title>");
    expect(html).toContain("<summary>See as a table</summary>");
    expect(html).toContain('data-kind="income"');
  });

  it("with nothing to show it says so", () => {
    expect(renderToStaticMarkup(<Sankey label="x" nodes={[]} links={[]} />)).toContain("No movements in this range");
  });
});

describe("the branches", () => {
  it("leaves go next to their branch, and inside it by amount", () => {
    const tree = [
      { id: "me", name: "You", column: 0, kind: "you" as const },
      { id: "spent", name: "Gasto", column: 1, kind: "expense" as const },
      { id: "saved", name: "Ahorro", column: 1, kind: "saving" as const },
      { id: "fun", name: "Ocio", column: 2, kind: "expense" as const },
      { id: "fund", name: "Background", column: 2, kind: "saving" as const },
      { id: "food", name: "Groceries", column: 2, kind: "expense" as const },
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

