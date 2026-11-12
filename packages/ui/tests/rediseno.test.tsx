import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  HourStrip,
  Panes,
  PhotoTile,
  Sparkline,
  SplitBar,
  Tile,
  ToggleGroup,
  ToggleRow,
  TrendTile,
  VitalCard,
  hourLevel,
  plain,
  ringMark,
} from "../src/index";

describe("lo principal y su apoyo", () => {
  it("lo principal va antes que el apoyo en el DOM, y el apoyo dice su nombre", () => {
    const html = renderToStaticMarkup(<Panes main={<p>uno</p>} aside={<p>dos</p>} asideLabel="Atajos" />);
    expect(html.indexOf("uno")).toBeLessThan(html.indexOf("dos"));
    expect(html).toContain('aria-label="Atajos"');
    expect(html).not.toContain("data-aside-first");
  });

  it("con asideFirst lo marca para el móvil sin cambiar el orden del DOM", () => {
    const html = renderToStaticMarkup(<Panes main={<p>uno</p>} aside={<p>dos</p>} asideLabel="El plan" asideFirst />);
    expect(html).toContain('data-aside-first="true"');
    expect(html.indexOf("uno")).toBeLessThan(html.indexOf("dos"));
  });
});

describe("las filas que se ven o no", () => {
  it("la fila dice qué hace, lleva su tono y, apagada, se dice", () => {
    const html = renderToStaticMarkup(<ToggleRow name="Plan" tone={2} checked={false} onChange={() => undefined} detail="De fondo" />);
    expect(html).toContain('aria-label="Mostrar Plan"');
    expect(html).toContain('data-tone="2"');
    expect(html).toContain('data-state="off"');
    expect(html).toContain("De fondo");
  });

  it("el grupo a medias lleva su casilla a medias, y cerrado no pinta sus filas", () => {
    const html = renderToStaticMarkup(
      <ToggleGroup name="Viajes" count="1 de 3" state="mixed" onChange={() => undefined} open={false} onOpen={() => undefined}>
        <li>fila</li>
      </ToggleGroup>,
    );
    expect(html).toContain('aria-checked="mixed"');
    expect(html).toContain("1 de 3");
    expect(html).not.toContain("fila");
  });

  it("a medias, la casilla ofrece mostrarlo todo", () => {
    const html = renderToStaticMarkup(
      <ToggleGroup name="Viajes" state="mixed" onChange={() => undefined} open onOpen={() => undefined}>
        <li>fila</li>
      </ToggleGroup>,
    );
    expect(html).toContain('aria-label="Mostrar todo Viajes"');
    expect(html).toContain("fila");
  });
});

describe("de un vistazo", () => {
  it("con acción, la tarjeta es un botón con su nombre y su veredicto, y la «i» va fuera", () => {
    const html = renderToStaticMarkup(
      <VitalCard label="Sueño" icon="moon" ring={{ value: 81, target: 100, display: "81" }} verdict="Buena" tone="good" info="qué es" onOpen={() => undefined} />,
    );
    expect(html).toContain('aria-label="Sueño: Buena"');
    expect(html).toContain('data-tone="good"');
    expect(html.indexOf("info-button")).toBeGreaterThan(html.indexOf("</button>"));
  });

  it("la marca del anillo cae en su ángulo", () => {
    const half = ringMark(0.5);
    expect(half.x1).toBeCloseTo(50);
    expect(half.y1).toBeGreaterThan(50);
    const quarter = ringMark(0.25);
    expect(quarter.y1).toBeCloseTo(50);
    expect(quarter.x1).toBeGreaterThan(50);
  });

  it("una cifra con su línea; sin acción no es un botón", () => {
    const html = renderToStaticMarkup(<TrendTile label="Reposo" value="60 lpm" weeks={[60, null, 58, 57]} />);
    expect(html).toContain("60 lpm");
    expect(html).not.toContain("<button");
  });
});

describe("la línea pequeña", () => {
  it("un hueco corta la línea en dos tramos y no se rellena", () => {
    const html = renderToStaticMarkup(<Sparkline series={[1, 2, null, 3, 4]} />);
    expect((html.match(/M /g) ?? []).length).toBe(2);
    expect(html).not.toContain("chart-area");
  });

  it("las marcas son rayas en su sitio", () => {
    const html = renderToStaticMarkup(<Sparkline series={[1, 2, 3]} marks={[1]} />);
    expect(html).toContain("sparkline-mark");
  });
});

describe("las 24 horas", () => {
  it("cinco niveles, y lo que aún no ha llegado, vacío", () => {
    expect([0, 3, 10, 20, 45].map(hourLevel)).toEqual([0, 1, 2, 3, 4]);
    const html = renderToStaticMarkup(<HourStrip values={Array(24).fill(10)} label="Tensión" format={(v) => `${v} min`} now={12} />);
    expect((html.match(/data-future/g) ?? []).length).toBe(11);
    expect((html.match(/<tr>/g) ?? []).length).toBe(24);
  });
});

describe("variantes de lo que ya había", () => {
  it("la barra repartida con su hueco y con los colores de las zonas", () => {
    const html = renderToStaticMarkup(
      <SplitBar label="Kcal" palette="zones" parts={[{ label: "A", value: "1", share: 1, hue: 1 }]} rest={{ label: "Queda", value: "2", share: 2 }} />,
    );
    expect(html).toContain('data-palette="zones"');
    expect(html).toContain("data-rest");
    expect(html).toContain("Queda");
  });

  it("las tarjetas apagadas y la compartida", () => {
    expect(renderToStaticMarkup(<Tile title="X" hue={1} muted />)).toContain("data-muted");
    const photo = renderToStaticMarkup(<PhotoTile title="Y" hue={2} icon="paw" shared badge="Vencido" badgeTone="warning" />);
    expect(photo).toContain("Compartido");
    expect(photo).toContain('data-tone="warning"');
  });

  it("los miles llevan punto también en cuatro cifras", () => {
    expect(plain(1560)).toBe("1.560");
  });
});
