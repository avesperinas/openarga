import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { OTHERS, SeriesChart, axisOf, foldSeries, labelStep, niceCeiling } from "../src/index";

const series = (key: string, values: number[]) => ({ key, name: key, values });

describe("las series", () => {
  it("a partir de la sexta se juntan en Otros, sumadas punto a punto", () => {
    const many = ["a", "b", "c", "d", "e", "f", "g"].map((key, index) => series(key, [10 - index, 1]));
    const folded = foldSeries(many);
    expect(folded.map((one) => one.key)).toEqual(["a", "b", "c", "d", "e", OTHERS]);
    expect(folded[5]!.values).toEqual([5 + 4, 2]);
  });

  it("el orden, y con él el color, lo pone la clave y no lo que suma hoy", () => {
    const order = ["ocio", "super", "casa"];
    const today = foldSeries([series("casa", [900]), series("ocio", [10]), series("super", [300])], order);
    expect(today.map((one) => one.key)).toEqual(["ocio", "super", "casa"]);
  });

  it("el eje arranca en cero y acaba en un número redondo, también apilado y con negativos", () => {
    expect(niceCeiling(1830)).toBe(2000);
    expect(niceCeiling(240)).toBe(250);
    expect(axisOf([series("a", [100, 300]), series("b", [200, 50])], "stacked")).toEqual({ min: 0, max: 500 });
    expect(axisOf([series("a", [-120, 300])], "bars")).toEqual({ min: -200, max: 500 });
    expect(labelStep(12)).toBe(2);
  });
});

describe("la gráfica", () => {
  const html = renderToStaticMarkup(
    <SeriesChart
      label="Gasto por categoría"
      labels={["jul", "ago", "sep"]}
      series={[series("super", [300, 280, 310]), series("ocio", [120, 90, 60])]}
      kind="stacked"
      order={["super", "ocio"]}
      format={(value) => `${value} €`}
    />,
  );

  it("cada serie lleva su color por su clave, y hay leyenda con más de una", () => {
    expect(html).toContain('data-series="0"');
    expect(html).toContain('data-series="1"');
    expect(html).toContain("series-chart-legend");
  });

  it("cada punto se lee con el teclado y en la tabla, no solo al pasar el ratón", () => {
    expect(html).toContain('aria-label="ago: super 280 €, ocio 90 €"');
    expect(html).toContain("<summary>Ver como tabla</summary>");
    expect(html).toContain("<td>310 €</td>");
  });

  it("sin datos lo dice en vez de pintar un eje vacío", () => {
    expect(renderToStaticMarkup(<SeriesChart label="x" labels={[]} series={[]} />)).toContain("Sin datos");
  });
});

describe("la línea de referencia", () => {
  const html = renderToStaticMarkup(
    <SeriesChart
      label="Patrimonio"
      kind="stacked"
      labels={["ene", "feb"]}
      series={[series("cash", [100, 200]), series("fund", [300, 400])]}
      overlay={{ key: "put", name: "Aportado", values: [350, 500] }}
    />,
  );

  it("se dibuja encima, discontinua, y entra en la leyenda y en la tabla", () => {
    expect(html).toContain("series-chart-overlay");
    expect(html.match(/Aportado/g)?.length).toBeGreaterThanOrEqual(2);
    expect(html).toContain("<td>500</td>");
  });

  it("el eje llega a la referencia aunque las barras se queden por debajo", () => {
    const tall = renderToStaticMarkup(
      <SeriesChart
        label="x"
        labels={["a"]}
        series={[series("a", [100])]}
        overlay={{ key: "r", name: "Ref", values: [900] }}
      />,
    );
    expect(tall).toContain("1000");
  });
});
