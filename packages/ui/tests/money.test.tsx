import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import {
  AreaTrend,
  BalanceHero,
  DivergingBars,
  GainChart,
  MonthStrip,
  Sankey,
  SeriesChart,
  Treemap,
  areaPath,
  treemapLayout,
} from "../src/index";

const render = (node: React.ReactElement) => renderToStaticMarkup(node);

describe("la cifra con su curva", () => {
  it("la curva se corta donde no hay dato y marca el último punto", () => {
    const { line, fill, last } = areaPath([10, 12, null, 14, 15]);
    expect(line.split("M").length - 1).toBe(2);
    expect(fill).toContain("Z");
    expect(last?.x).toBe(300);
  });

  it("sin datos, sin curva; con ellos, la cifra, el cambio y el principio y el final", () => {
    expect(areaPath([null, null]).line).toBe("");
    const html = render(
      <AreaTrend
        label="Patrimonio"
        value="48.320 €"
        delta={{ text: "+9.140 € en 12 meses", tone: "positive" }}
        points={[
          { label: "dic", value: 39180 },
          { label: "nov", value: 48320 },
        ]}
      />,
    );
    expect(html).toContain("48.320 €");
    expect(html).toContain('data-tone="positive"');
    expect(html).toContain(">dic<");
    expect(html).toContain("area-trend-dot");
  });
});

describe("la tira de meses", () => {
  it("dice cada mes al lector y marca el elegido", () => {
    const html = render(
      <MonthStrip
        label="Meses"
        selected="2026-11"
        onSelect={() => undefined}
        items={[
          { key: "2026-10", label: "oct", value: 2000, description: "octubre, 2.000 €" },
          { key: "2026-11", label: "nov", value: 1000, description: "noviembre, 1.000 €" },
        ]}
      />,
    );
    expect(html).toContain('aria-label="noviembre, 1.000 €"');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("height:50%");
  });
});

describe("quién debe a quién", () => {
  it("con deuda, la flecha; en paz, sin ella", () => {
    const owed = render(<BalanceHero payer={{ name: "Sam", hue: 6 }} payee={{ name: "Alex", hue: 5 }} amount="312 €" />);
    expect(owed).toContain('aria-label="Sam paga a Alex"');
    expect(owed).toContain("<path");
    const even = render(<BalanceHero payer={{ name: "Sam", hue: 6 }} payee={{ name: "Alex", hue: 5 }} amount="0 €" even />);
    expect(even).toContain("Estáis en paz");
    expect(even).not.toContain("<path");
  });
});

describe("lo aportado contra lo que vale", () => {
  it("sombrea la ganancia en verde si vale más, y en rojo si menos", () => {
    const up = render(<GainChart label="Fondos" labels={["ene", "feb"]} value={[100, 130]} contributed={[100, 110]} />);
    expect(up).toContain('class="gain-chart-gain" data-ahead="true"');
    expect(up).toContain("Ganancia");
    const down = render(<GainChart label="Fondos" labels={["ene", "feb"]} value={[100, 90]} contributed={[100, 110]} />);
    expect(down).toContain("Pérdida");
    expect(render(<GainChart label="Nada" labels={[]} value={[]} contributed={[]} />)).toContain("Sin datos");
  });
});

describe("el mapa de bloques", () => {
  const items = [
    { key: "casa", label: "Casa", value: 6, detail: "6 €", hue: 3 as const },
    { key: "super", label: "Súper", value: 3, detail: "3 €", hue: 2 as const },
    { key: "ocio", label: "Ocio", value: 1, detail: "1 €", hue: 7 as const },
    { key: "nada", label: "Nada", value: 0, detail: "0 €", hue: 8 as const },
  ];

  it("cada bloque mide lo que pesa, sin pasarse del rectángulo, y lo que no suma no sale", () => {
    const tiles = treemapLayout(items, 100, 100);
    expect(tiles.map((tile) => tile.key)).toEqual(["casa", "super", "ocio"]);
    const area = (key: string) => tiles.find((tile) => tile.key === key)!;
    expect(area("casa").w * area("casa").h).toBeCloseTo(6000, 0);
    expect(area("ocio").w * area("ocio").h).toBeCloseTo(1000, 0);
    for (const tile of tiles) {
      expect(tile.x + tile.w).toBeLessThanOrEqual(100.0001);
      expect(tile.y + tile.h).toBeLessThanOrEqual(100.0001);
    }
  });

  it("con algo que hacer al tocarlo, cada bloque es un botón con su nombre e importe", () => {
    const html = render(<Treemap label="Gasto" items={items} onSelect={() => undefined} />);
    expect(html).toContain('aria-label="Casa: 6 €"');
    expect(html.match(/<button/g)?.length).toBe(3);
  });
});

describe("contra la media", () => {
  it("lo que sube va a la derecha y lo que baja a la izquierda, en su tono", () => {
    const html = render(
      <DivergingBars
        label="Contra tu media"
        rows={[
          { key: "a", label: "Súper", value: 0.18, text: "+18 %", tone: "negative" },
          { key: "b", label: "Viajes", value: -0.09, text: "−9 %", tone: "positive" },
        ]}
      />,
    );
    expect(html).toContain("left:50%;width:50%");
    expect(html).toContain("right:50%;width:25%");
    expect(html).toContain('data-tone="negative"');
  });
});

describe("el flujo en vertical", () => {
  it("dibuja sin texto dentro y pone los nombres en una lista que enciende un camino", () => {
    const html = render(
      <Sankey
        vertical
        label="Flujo"
        nodes={[
          { id: "n", name: "Nómina", column: 0, kind: "income" },
          { id: "c", name: "Casa", column: 1, kind: "expense" },
          { id: "a", name: "Ahorro", column: 1, kind: "saving" },
        ]}
        links={[
          { source: "n", target: "c", value: 600 },
          { source: "n", target: "a", value: 400 },
        ]}
        share={(_, value) => `${Math.round(value / 10)} %`}
      />,
    );
    expect(html).toContain('data-vertical=""');
    expect(html).not.toContain("<text");
    expect(html).toContain("sankey-legend-item");
    expect(html).toContain("· 60 %");
  });
});

describe("las áreas apiladas", () => {
  it("una por serie, una encima de otra", () => {
    const html = render(
      <SeriesChart
        kind="area"
        label="Patrimonio por tipo"
        labels={["ene", "feb"]}
        series={[
          { key: "cash", name: "Efectivo", values: [10, 12] },
          { key: "fondos", name: "Fondos", values: [20, 25] },
        ]}
      />,
    );
    expect(html.match(/series-chart-area/g)?.length).toBe(2);
  });
});
