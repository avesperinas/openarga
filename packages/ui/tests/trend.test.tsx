import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { TrendChart, trendDomain, trendX } from "../src/index";

const weights = [
  { day: "2026-09-01", value: 80.4, average: 80.4 },
  { day: "2026-09-02", value: 79.6, average: 80.0 },
  { day: "2026-09-11", value: 79.0, average: 79.0 },
];

describe("la tendencia", () => {
  it("ajusta el eje a los datos y a la banda, no desde cero", () => {
    const { min, max } = trendDomain(weights, { low: 72, high: 76 });

    expect(min).toBeGreaterThan(70);
    expect(min).toBeLessThan(72);
    expect(max).toBeGreaterThan(80.4);
    expect(max).toBeLessThan(82);
  });

  it("un solo valor tiene un eje a su alrededor", () => {
    expect(trendDomain([{ day: "2026-09-01", value: 120 }])).toEqual({ min: 119, max: 121 });
  });

  it("pone cada punto en su fecha, con los huecos como huecos", () => {
    expect(trendX(weights)).toEqual([0, 0.1, 1]);
    expect(trendX([{ day: "2026-09-01", value: 1 }])).toEqual([0.5]);
  });

  it("dibuja la media, lo medido, la banda y marca lo que queda fuera de ella", () => {
    const html = renderToStaticMarkup(
      <TrendChart label="Peso" points={weights} band={{ low: 72, high: 76 }} valueName="Pesada" averageName="Media 7 días" />,
    );

    expect(html).toContain("trend-chart-band");
    expect(html).toContain("trend-chart-raw");
    expect(html).toContain("Media 7 días");
    expect(html.match(/trend-chart-dot/g)).toHaveLength(3);
    expect(html.match(/data-out/g)).toHaveLength(3);
  });

  it("sin media, lo medido es la línea principal, y con muchos puntos no se marca cada uno", () => {
    const many = Array.from({ length: 90 }, (_, index) => ({
      day: `2026-0${1 + Math.floor(index / 30)}-${String(1 + (index % 28)).padStart(2, "0")}`,
      value: 100 + index,
    }));

    const html = renderToStaticMarkup(<TrendChart label="LDL" points={many} />);

    expect(html).not.toContain("trend-chart-raw");
    expect(html).toContain("trend-chart-line");
    expect(html).not.toContain("trend-chart-dot");
  });

  it("sin puntos lo dice", () => {
    expect(renderToStaticMarkup(<TrendChart label="Peso" points={[]} />)).toContain("Sin datos");
  });

  it("marca el día del cambio con su línea y su nombre, solo si cae dentro", () => {
    const marked = renderToStaticMarkup(
      <TrendChart label="VFC" points={weights} marker={{ day: "2026-09-02", label: "Cambio a la pulsera" }} />,
    );
    const outside = renderToStaticMarkup(
      <TrendChart label="VFC" points={weights} marker={{ day: "2026-10-01", label: "Cambio a la pulsera" }} />,
    );

    expect(marked).toContain("trend-chart-marker");
    expect(marked).toContain("Cambio a la pulsera");
    expect(outside).not.toContain("trend-chart-marker");
  });

  it("marca aparte los puntos destacados, con su nombre en la leyenda", () => {
    const html = renderToStaticMarkup(
      <TrendChart
        label="e1RM"
        highlightName="Récord"
        points={[
          { day: "2026-09-01", value: 100 },
          { day: "2026-09-08", value: 104, highlight: true },
        ]}
      />,
    );

    expect(html.match(/data-highlight=""/g)).toHaveLength(1);
    expect(html).toContain('data-key="highlight"');
    expect(html).toContain("Récord");
  });

  it("sin marcar fuera, la banda es solo una referencia", () => {
    const html = renderToStaticMarkup(
      <TrendChart
        label="e1RM"
        flagOutside={false}
        band={{ low: 100, high: 102 }}
        points={[
          { day: "2026-09-01", value: 95 },
          { day: "2026-09-08", value: 110 },
        ]}
      />,
    );

    expect(html).not.toContain("data-out");
  });
});
