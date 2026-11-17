import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  Collapsible,
  DataTable,
  FlowMap,
  ShareChart,
  StatTile,
  csvCell,
  foldShares,
  percentOf,
  placeBoxes,
  tableCsv,
  toCsv,
  toneFor,
} from "../src/index";

describe("the compact table", () => {
  const columns = [
    { key: "name", label: "Cuenta", cell: (row: { name: string; value: number }) => row.name },
    {
      key: "value",
      label: "Saldo",
      numeric: true,
      cell: (row: { name: string; value: number }) => `${row.value} €`,
      csv: (row: { name: string; value: number }) => row.value,
    },
  ];
  const rows = [
    { name: "Corriente; la de siempre", value: 1234.5 },
    { name: "Savings", value: 10 },
  ];

  it("renders one row per item and the total, and expandable rows are reachable by keyboard", () => {
    const html = renderToStaticMarkup(
      <DataTable
        label="Saldos"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.name}
        onRowClick={() => undefined}
        footer={["Total", "1244,5 €"]}
      />,
    );
    expect(html.match(/<tr/g)?.length).toBe(4);
    expect(html).toContain('tabindex="0"');
    expect(html).toContain("<tfoot>");
  });

  it("without rows it says so", () => {
    expect(
      renderToStaticMarkup(<DataTable label="x" columns={columns} rows={[]} rowKey={(row) => row.name} empty="Nada" />),
    ).toContain("Nada");
  });

  it("the CSV follows the locale's separators, as a spreadsheet in that locale opens it", () => {
    expect(csvCell(1234.567)).toBe("1234,57");
    expect(csvCell('says "hello"; bye')).toBe('"says ""hello""; bye"');
    expect(toCsv(["a", "b"], [[1.5, null]])).toBe("a;b\n1,5;");
    expect(tableCsv(columns, rows)).toBe('Cuenta;Saldo\n"Corriente; la de siempre";1234,5\nSavings;10');
  });
});

describe("the pie", () => {
  it("joins what does not fit into Others and leaves out negatives", () => {
    const items = ["a", "b", "c", "d", "e", "f", "g"].map((key, index) => ({ key, name: key, value: 10 - index }));
    const folded = foldShares([...items, { key: "loan", name: "Loan", value: -50 }]);
    expect(folded).toHaveLength(6);
    expect(folded.at(-1)).toMatchObject({ name: "Others", value: 9 });
    expect(percentOf(0.5, 100)).toBe("<1 %");
  });

  it("says each part with its weight", () => {
    const html = renderToStaticMarkup(
      <ShareChart
        label="Reparto"
        items={[
          { key: "a", name: "Liquidez", value: 25 },
          { key: "b", name: "Investment", value: 75 },
        ]}
      />,
    );
    expect(html).toContain("Liquidez");
    expect(html).toContain("25 %");
    expect(html).toContain("75 %");
  });
});

describe("the figures at the top", () => {
  it("green if it gets there, amber past half, red otherwise", () => {
    expect(toneFor(120)).toBe("positive");
    expect(toneFor(60)).toBe("warning");
    expect(toneFor(20)).toBe("negative");
    expect(toneFor(null)).toBe("neutral");
    const html = renderToStaticMarkup(
      <StatTile label="Savings" value="12 %" foot="60 % of the goal" tone="warning" progress={0.6} />,
    );
    expect(html).toContain('data-tone="warning"');
    expect(html).toContain("width:60%");
    const explained = renderToStaticMarkup(<StatTile label="Savings" value="12 %" info={<p>How</p>} />);
    expect(explained).toContain('aria-label="How savings is calculated"');
    expect(explained).not.toContain("How</p>");
  });

  it("a folded section keeps its content", () => {
    const html = renderToStaticMarkup(
      <Collapsible title="Accounts" subtitle="3 products">
        <p>dentro</p>
      </Collapsible>,
    );
    expect(html).toContain("<details");
    expect(html).not.toContain("open");
    expect(html).toContain("dentro");
  });
});

describe("the boxes with arrows", () => {
  const nodes = [
    {
      id: "out",
      name: "Entra de fuera",
      kind: "income",
      group: "outside",
      group_name: "Fuera",
      inflow: 0,
      outflow: 2000,
    },
    { id: "a", name: "Salary", kind: "account", group: "i1", group_name: "Bank One", inflow: 2000, outflow: 1600 },
    { id: "b", name: "Home", kind: "common", group: "i1", group_name: "Bank One", inflow: 600, outflow: 80 },
    { id: "c", name: "Savings", kind: "account", group: "i2", group_name: "Bank Two", inflow: 1000, outflow: 0 },
    { id: "spent", name: "Gastos", kind: "expense", group: "spent", group_name: "Gastos", inflow: 80, outflow: 0 },
  ];
  const links = [
    { source: "out", target: "a", value: 2000 },
    { source: "a", target: "b", value: 600 },
    { source: "a", target: "c", value: 1000 },
    { source: "b", target: "spent", value: 80 },
  ];

  it("income on the left, spending on the right, and accounts in the order of the money", () => {
    const { placed } = placeBoxes(nodes, links);
    const column = Object.fromEntries(placed.map((one) => [one.id, one.column]));
    expect(column.out).toBe(0);
    expect(column.a).toBe(1);
    expect(column.b).toBe(2);
    expect(column.c).toBe(2);
    expect(column.spent).toBe(3);
  });

  it("each arrow says its amount and there is a table to read it without the drawing", () => {
    const html = renderToStaticMarkup(
      <FlowMap label="Flujos" nodes={nodes} links={links} format={(value) => `${value} €`} />,
    );
    expect(html).toContain("Salary → Home: 600 €");
    expect(html).toContain("See as a table");
    expect(html).toContain("Bank Two");
  });

  it("with onSelect, each arrow and box is tapped like a button; without it, no", () => {
    const pickable = renderToStaticMarkup(
      <FlowMap label="Flujos" nodes={nodes} links={links} onSelect={() => undefined} />,
    );
    expect(pickable).toContain('role="button"');
    expect(pickable).toContain('aria-label="Salary → Home: 600"');
    const still = renderToStaticMarkup(<FlowMap label="Flujos" nodes={nodes} links={links} />);
    expect(still).not.toContain('role="button"');
  });

  it("if each box brings its column, that rules, and those of one group go together", () => {
    const given = [
      { ...nodes[0]!, column: 0 },
      { ...nodes[1]!, column: 1 },
      { ...nodes[2]!, column: 3 },
      { ...nodes[3]!, column: 1 },
      { ...nodes[4]!, column: 4 },
    ];
    const { placed } = placeBoxes(given, links);
    const column = Object.fromEntries(placed.map((one) => [one.id, one.column]));
    expect(column).toEqual({ out: 0, a: 1, c: 1, b: 3, spent: 4 });
  });
});

