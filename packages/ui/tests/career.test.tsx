import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import {
  MonthDots,
  PeriodBars,
  SeriesChart,
  SpanRibbon,
  Waterfall,
  monthRange,
  spanPlaces,
  stepPath,
  waterfallBars,
} from "../src/index";

const render = (node: React.ReactElement) => renderToStaticMarkup(node);

describe("los meses", () => {
  it("van de un mes a otro, los dos incluidos, cruzando de año", () => {
    expect(monthRange("2025-11", "2026-02")).toEqual(["2025-11", "2025-12", "2026-01", "2026-02"]);
    expect(monthRange("2026-03", "2026-02")).toEqual([]);
  });
});

describe("la cinta de contratos", () => {
  const months = monthRange("2025-01", "2025-12");
  it("cada tramo cae en sus meses; uno que sigue llega al final y uno de fuera no sale", () => {
    const places = spanPlaces(
      [
        { key: "a", name: "Antigua", hue: 1, from: "2024-06", to: "2025-03" },
        { key: "b", name: "Hoy", hue: 2, from: "2025-07", to: null },
        { key: "c", name: "Fuera", hue: 3, from: "2023-01", to: "2023-05" },
      ],
      months,
    );
    expect(places.map((one) => one.span.key)).toEqual(["a", "b"]);
    expect(places[0]!.left).toBe(0);
    expect(places[0]!.width).toBeCloseTo(3 / 12);
    expect(places[1]!.left).toBeCloseTo(6 / 12);
    expect(places[1]!.width).toBeCloseTo(6 / 12);
  });

  it("un tramo estrecho no enseña su nombre, pero lo dice", () => {
    const html = render(
      <SpanRibbon months={months} label="Contratos" spans={[{ key: "p", name: "Paro", hue: 8, from: "2025-05", to: "2025-05", muted: true }]} />,
    );
    expect(html).toContain("data-hidden");
    expect(html).toContain("Paro, de 2025-05 a 2025-05");
    expect(html).toContain("data-muted");
  });
});

describe("las barras de cada mes", () => {
  const groups = [
    { key: "old", name: "Antigua", hue: 1 as const },
    { key: "new", name: "Hoy", hue: 2 as const },
  ];
  it("parte cada mes por quien pagó, con trama lo reconstruido, claro lo previsto y una línea en hoy", () => {
    const html = render(
      <PeriodBars
        label="Neto de cada mes"
        groups={groups}
        periods={[
          { key: "2025-12", label: "diciembre de 2025", parts: [{ group: "old", value: 1500, estimated: true }] },
          { key: "2026-01", label: "enero de 2026", parts: [{ group: "old", value: 800 }, { group: "new", value: 900 }] },
          { key: "2026-02", label: "febrero de 2026", parts: [{ group: "new", value: 1800 }], projected: true },
        ]}
        format={(value) => `${value} €`}
      />,
    );
    expect(html.match(/class="period-bars-bar"/g)).toHaveLength(4);
    expect(html).toContain("period-bars-estimated");
    expect(html).toContain("data-projected");
    expect(html).toContain("period-bars-today");
    expect(html).toContain("enero de 2026: 1700 €");
    expect(html).toContain("febrero de 2026, previsto: 1800 €");
    expect(html).toContain("Reconstruido");
    expect(html).toContain("Previsto");
  });

  it("sin meses, lo dice", () => {
    expect(render(<PeriodBars label="Nada" groups={groups} periods={[]} />)).toContain("Sin datos todavía");
  });
});

describe("el cuadre de cada mes", () => {
  it("un punto por mes con su estado; lo previsto no se toca", () => {
    const html = render(
      <MonthDots
        label="Nóminas de 2026"
        onSelect={() => undefined}
        items={[
          { key: "2026-01", label: "e", state: "matched", description: "enero: cuadra" },
          { key: "2026-02", label: "f", state: "differs", description: "febrero: el banco trae 38 € menos" },
          { key: "2026-03", label: "m", state: "projected", description: "marzo: prevista" },
        ]}
      />,
    );
    expect(html.match(/<button/g)).toHaveLength(2);
    expect(html).toContain('data-state="differs"');
    expect(html).toContain("marzo: prevista");
  });
});

describe("la cascada", () => {
  it("cada paso sale de donde se quedó el anterior y los totales desde cero", () => {
    const bars = waterfallBars([
      { key: "due", label: "Cuota", value: 9420, kind: "total" },
      { key: "min", label: "Mínimo", value: -1084, kind: "change" },
      { key: "work", label: "Trabajo", value: -400, kind: "change" },
      { key: "net", label: "Líquida", value: 7936, kind: "total" },
      { key: "held", label: "Retenido", value: -6556, kind: "change" },
      { key: "result", label: "Falta", value: 1380, kind: "result" },
    ]);
    expect(bars.map((one) => [one.from, one.to])).toEqual([
      [0, 9420],
      [9420, 8336],
      [8336, 7936],
      [0, 7936],
      [7936, 1380],
      [0, 1380],
    ]);
  });

  it("cada barra dice su cifra, con signo en los pasos; un resultado negativo pinta el cero", () => {
    const html = render(
      <Waterfall
        label="De la cuota al resultado"
        format={(value) => `${value} €`}
        steps={[
          { key: "due", label: "Cuota", value: 1000, kind: "total" },
          { key: "held", label: "Retenido", value: -1300, kind: "change", tone: "positive" },
          { key: "result", label: "A devolver", value: -300, kind: "result", tone: "positive" },
        ]}
      />,
    );
    expect(html).toContain("Retenido: −1300 €");
    expect(html).toContain("A devolver: -300 €");
    expect(html).toContain("waterfall-zero");
  });
});

describe("los escalones", () => {
  it("cada valor es un tramo plano, unido al anterior; un hueco corta", () => {
    const path = stepPath([10, 10, 20, Number.NaN, 30], 10, (value) => 100 - value);
    expect(path).toBe("M0,90 H10 V90 H20 V80 H30 M40,70 H50");
  });

  it("la gráfica en escalones dice una raya en los huecos", () => {
    const html = render(
      <SeriesChart
        kind="step"
        label="Bruto anual"
        labels={["ene", "feb", "mar"]}
        series={[{ key: "gross", name: "Bruto anual", values: [24000, Number.NaN, 27000] }]}
      />,
    );
    expect(html).toContain("series-chart-line");
    expect(html).toContain("<td>—</td>");
  });
});
