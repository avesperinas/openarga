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

describe("la tabla compacta", () => {
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
    { name: "Ahorro", value: 10 },
  ];

  it("pinta una fila por dato y el total, y las filas que se abren se alcanzan con el teclado", () => {
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

  it("sin filas lo dice", () => {
    expect(
      renderToStaticMarkup(<DataTable label="x" columns={columns} rows={[]} rowKey={(row) => row.name} empty="Nada" />),
    ).toContain("Nada");
  });

  it("el CSV va con punto y coma y coma decimal, como lo abre una hoja en español", () => {
    expect(csvCell(1234.567)).toBe("1234,57");
    expect(csvCell('dice "hola"; adiós')).toBe('"dice ""hola""; adiós"');
    expect(toCsv(["a", "b"], [[1.5, null]])).toBe("a;b\n1,5;");
    expect(tableCsv(columns, rows)).toBe('Cuenta;Saldo\n"Corriente; la de siempre";1234,5\nAhorro;10');
  });
});

describe("el quesito", () => {
  it("junta lo que no cabe en Otros y deja fuera lo negativo", () => {
    const items = ["a", "b", "c", "d", "e", "f", "g"].map((key, index) => ({ key, name: key, value: 10 - index }));
    const folded = foldShares([...items, { key: "loan", name: "Préstamo", value: -50 }]);
    expect(folded).toHaveLength(6);
    expect(folded.at(-1)).toMatchObject({ name: "Otros", value: 9 });
    expect(percentOf(0.5, 100)).toBe("<1 %");
  });

  it("dice cada parte con su peso", () => {
    const html = renderToStaticMarkup(
      <ShareChart
        label="Reparto"
        items={[
          { key: "a", name: "Liquidez", value: 25 },
          { key: "b", name: "Inversión", value: 75 },
        ]}
      />,
    );
    expect(html).toContain("Liquidez");
    expect(html).toContain("25 %");
    expect(html).toContain("75 %");
  });
});

describe("las cifras de arriba", () => {
  it("verde si llega, ámbar si pasa de la mitad, rojo si no", () => {
    expect(toneFor(120)).toBe("positive");
    expect(toneFor(60)).toBe("warning");
    expect(toneFor(20)).toBe("negative");
    expect(toneFor(null)).toBe("neutral");
    const html = renderToStaticMarkup(
      <StatTile label="Ahorro" value="12 %" foot="60 % de la meta" tone="warning" progress={0.6} />,
    );
    expect(html).toContain('data-tone="warning"');
    expect(html).toContain("width:60%");
    const explained = renderToStaticMarkup(<StatTile label="Ahorro" value="12 %" info={<p>Cómo</p>} />);
    expect(explained).toContain('aria-label="Cómo se calcula ahorro"');
    expect(explained).not.toContain("Cómo</p>");
  });

  it("una sección plegada guarda su contenido", () => {
    const html = renderToStaticMarkup(
      <Collapsible title="Cuentas" subtitle="3 productos">
        <p>dentro</p>
      </Collapsible>,
    );
    expect(html).toContain("<details");
    expect(html).not.toContain("open");
    expect(html).toContain("dentro");
  });
});

describe("las cajas con flechas", () => {
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
    { id: "a", name: "Nómina", kind: "account", group: "i1", group_name: "Banco Uno", inflow: 2000, outflow: 1600 },
    { id: "b", name: "Casa", kind: "common", group: "i1", group_name: "Banco Uno", inflow: 600, outflow: 80 },
    { id: "c", name: "Ahorro", kind: "account", group: "i2", group_name: "Banco Dos", inflow: 1000, outflow: 0 },
    { id: "spent", name: "Gastos", kind: "expense", group: "spent", group_name: "Gastos", inflow: 80, outflow: 0 },
  ];
  const links = [
    { source: "out", target: "a", value: 2000 },
    { source: "a", target: "b", value: 600 },
    { source: "a", target: "c", value: 1000 },
    { source: "b", target: "spent", value: 80 },
  ];

  it("lo que entra de fuera a la izquierda, los gastos a la derecha, y las cuentas por el orden del dinero", () => {
    const { placed } = placeBoxes(nodes, links);
    const column = Object.fromEntries(placed.map((one) => [one.id, one.column]));
    expect(column.out).toBe(0);
    expect(column.a).toBe(1);
    expect(column.b).toBe(2);
    expect(column.c).toBe(2);
    expect(column.spent).toBe(3);
  });

  it("cada flecha dice su importe y hay tabla para leerlo sin ver el dibujo", () => {
    const html = renderToStaticMarkup(
      <FlowMap label="Flujos" nodes={nodes} links={links} format={(value) => `${value} €`} />,
    );
    expect(html).toContain("Nómina → Casa: 600 €");
    expect(html).toContain("Ver como tabla");
    expect(html).toContain("Banco Dos");
  });

  it("con onSelect, cada flecha y cada caja se tocan como un botón; sin él, no", () => {
    const pickable = renderToStaticMarkup(
      <FlowMap label="Flujos" nodes={nodes} links={links} onSelect={() => undefined} />,
    );
    expect(pickable).toContain('role="button"');
    expect(pickable).toContain('aria-label="Nómina → Casa: 600"');
    const still = renderToStaticMarkup(<FlowMap label="Flujos" nodes={nodes} links={links} />);
    expect(still).not.toContain('role="button"');
  });

  it("si cada caja trae su columna, manda ella, y las de un mismo grupo van juntas", () => {
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

