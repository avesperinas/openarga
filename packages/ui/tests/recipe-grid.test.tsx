import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { RecipeGrid, ZOOM, layout, zoomStep } from "../src/index";
import type { RecipeGridCell, RecipeGridRow } from "../src/index";

const ROWS: RecipeGridRow[] = [
  { id: 1, amount: "115 g", label: "Mantequilla" },
  { id: 2, amount: "200 g", label: "Azúcar" },
  { id: 3, amount: "2", label: "Huevos" },
];
const CELLS: RecipeGridCell[] = [
  { id: 1, label: "Derretir", column: 1, row: 1, span: 1 },
  { id: 2, label: "Mezclar", column: 2, row: 1, span: 2 },
  { id: 3, label: "Batir", column: 3, row: 1, span: 3, attended: false },
];

describe("las columnas salen donde tienen que salir", () => {
  it("una fila que una celda alta atraviesa no vuelve a pedir esa columna", () => {
    const lines = layout(ROWS, CELLS, 3);

    expect(lines[0]!.map((cell) => cell.label)).toEqual(["Derretir", "Mezclar", "Batir"]);
    expect(lines[1]!.map((cell) => cell.label)).toEqual([""]);
    expect(lines[1]![0]!.column).toBe(1);
    expect(lines[2]!.map((cell) => cell.column)).toEqual([1, 2]);
  });

  it("un hueco de enmedio no corre la celda que viene después", () => {
    const sparse: RecipeGridCell[] = [
      { id: 1, label: "Picar", column: 1, row: 1, span: 1 },
      { id: 2, label: "Pelar", column: 1, row: 3, span: 1 },
      { id: 3, label: "Cocer", column: 3, row: 1, span: 3 },
    ];

    const lines = layout(ROWS, sparse, 3);

    expect(lines[0]!.map((cell) => [cell.column, cell.label])).toEqual([
      [1, "Picar"],
      [2, ""],
      [3, "Cocer"],
    ]);
    expect(lines[2]!.map((cell) => [cell.column, cell.label])).toEqual([
      [1, "Pelar"],
      [2, ""],
    ]);
  });
});

describe("el HTML es una tabla de receta y no una caja de cajas", () => {
  it("cada operación abarca sus filas con rowspan", () => {
    const html = renderToStaticMarkup(
      <RecipeGrid label="El bizcocho" rows={ROWS} cells={CELLS} columns={3} />,
    ).toLowerCase();

    expect(html).toContain('rowspan="2"');
    expect(html).toContain('rowspan="3"');
    expect(html).toContain('scope="row"');
    expect(html).toContain("mantequilla");
    expect(html).toContain('rowspan="3"><span class="recipe-grid-verb">batir');
  });

  it("los pasos que no juntan nada cruzan la rejilla entera", () => {
    const html = renderToStaticMarkup(
      <RecipeGrid
        label="El bizcocho"
        rows={ROWS}
        cells={CELLS}
        columns={3}
        bands={[{ id: "horno", label: "Precalentar el horno", note: "10 min" }]}
      />,
    );

    expect(html.toLowerCase()).toContain('colspan="4"');
    expect(html).toContain("Precalentar el horno");
  });

  it("una receta sin ingredientes no pinta una rejilla vacía", () => {
    const html = renderToStaticMarkup(
      <RecipeGrid label="Nada" rows={[]} cells={[]} columns={0} />,
    );

    expect(html).toBe("");
  });
});

describe("ampliar", () => {
  it("el zoom se mueve por pasos y se para en los extremos", () => {
    expect(zoomStep(1, 1)).toBe(ZOOM[2]);
    expect(zoomStep(ZOOM[ZOOM.length - 1]!, 1)).toBe(ZOOM[ZOOM.length - 1]);
    expect(zoomStep(ZOOM[0], -1)).toBe(ZOOM[0]);
  });

  it("el tamaño llega como variable CSS, que es lo único que el linter de tokens permite", () => {
    const html = renderToStaticMarkup(
      <RecipeGrid label="El bizcocho" rows={ROWS} cells={CELLS} columns={3} />,
    );

    expect(html).toContain("--grid-scale:1");
    expect(html).toContain("Ver más grande");
    expect(html).toContain("Ampliar a pantalla completa");
  });
});
