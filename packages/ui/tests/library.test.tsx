import { readFileSync } from "node:fs";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  IconBadge,
  Widget,
  WidgetBars,
  WidgetCalendar,
  WidgetChart,
  WidgetHeatmap,
  WidgetKpi,
  WidgetKpiDelta,
  WidgetProgress,
  WidgetRing,
  WidgetShortcuts,
  WidgetStats,
  WidgetStreak,
  WidgetUpNext,
  fitsUncertaintyLine,
  isCompact,
  kpiStep,
  spanOf,
} from "../src/index";

const render = (element: React.ReactElement): string => renderToStaticMarkup(element);

describe("el vocabulario de tamaños", () => {
  it("los cuatro nuevos y los dos viejos siguen resolviendo", () => {
    expect(spanOf("1x1")).toEqual([1, 1]);
    expect(spanOf("1x2")).toEqual([1, 2]);
    expect(spanOf("2x2")).toEqual([2, 2]);
    expect(spanOf("2x4")).toEqual([2, 4]);
    expect(spanOf("4x2")).toEqual([4, 2]);
    expect(spanOf("4x4")).toEqual([4, 4]);
  });

  it("un tamaño desconocido cae al más pequeño que siempre cabe, no rompe", () => {
    expect(spanOf("9x9")).toEqual([2, 2]);
  });

  it("la cifra crece con el hueco, que es lo que hace que un KPI grande se sienta grande", () => {
    const steps = ["1x1", "2x2", "2x4", "4x4"].map(kpiStep);
    expect(new Set(steps).size).toBe(4);
  });

  it("lo pequeño no finge que tiene sitio", () => {
    expect(isCompact("1x1")).toBe(true);
    expect(isCompact("1x2")).toBe(true);
    expect(isCompact("2x2")).toBe(false);
    expect(fitsUncertaintyLine("1x1")).toBe(false);
    expect(fitsUncertaintyLine("2x2")).toBe(false);
    expect(fitsUncertaintyLine("4x2")).toBe(true);
  });
});

describe("la cifra", () => {
  it("el servidor pinta el número de verdad, no un cero que luego sube", () => {
    expect(render(<WidgetKpi value={1240} />)).toContain("1.240");
  });

  it("abrevia solo cuando el ancho lo pide", () => {
    expect(render(<WidgetKpi value={9870} />)).toContain("9.870");
    expect(render(<WidgetKpi value={124000} />)).toContain("124");
  });

  it("la unidad va aparte de la cifra", () => {
    const html = render(<WidgetKpi value={1240} unit="km" />);
    expect(html).toContain('class="kpi-unit"');
    expect(html).toContain("km");
  });

  it("un valor que ya viene formateado se pinta tal cual", () => {
    expect(render(<WidgetKpi value="v0.4.1" />)).toContain("v0.4.1");
  });

  it("hereda el paso de cifra del tamaño del widget que la contiene", () => {
    const html = render(
      <Widget title="Pasos" hue={1} size="4x4" shape="number" state="ready">
        <WidgetKpi value={12} />
      </Widget>,
    );
    expect(html).toContain("--kpi-step:var(--text-kpi-xl)");
  });
});

describe("la comparación contra el periodo anterior", () => {
  it("el signo va siempre, también en positivo", () => {
    expect(render(<WidgetKpiDelta value={112} previous={100} />)).toContain("+12%");
    expect(render(<WidgetKpiDelta value={88} previous={100} />)).toContain("-12%");
  });

  it("la flecha dice la dirección sin depender del color", () => {
    expect(render(<WidgetKpiDelta value={112} previous={100} />)).toContain('data-direction="1"');
    expect(render(<WidgetKpiDelta value={88} previous={100} />)).toContain('data-direction="-1"');
    expect(render(<WidgetKpiDelta value={100} previous={100} />)).toContain('data-direction="0"');
  });

  it("subir es bueno o malo según el dominio, no según el componente", () => {
    const pasos = render(<WidgetKpiDelta value={112} previous={100} goodWhen="up" />);
    const gasto = render(<WidgetKpiDelta value={112} previous={100} goodWhen="down" />);

    expect(pasos).toContain('data-tone="good"');
    expect(gasto).toContain('data-tone="bad"');
  });

  it("sin dirección buena la variación no se tiñe", () => {
    expect(render(<WidgetKpiDelta value={112} previous={100} goodWhen="neutral" />)).toContain(
      'data-tone="neutral"',
    );
  });

  it("de cero a cinco no es un 500% más", () => {
    const html = render(<WidgetKpiDelta value={5} previous={0} />);

    expect(html).toContain("sin dato anterior");
    expect(html).not.toContain("%");
  });
});

describe("las gráficas", () => {
  it("una serie vacía lo dice en vez de pintar un lienzo en blanco", () => {
    expect(render(<WidgetChart series={[]} />)).toContain("Sin serie");
    expect(render(<WidgetBars series={[]} />)).toContain("Sin serie");
  });

  it("un solo punto no rompe la proyección", () => {
    const html = render(<WidgetChart series={[7]} />);
    expect(html).toContain("chart-line");
    expect(html).not.toContain("NaN");
  });

  it("una serie plana no divide entre cero al escalar", () => {
    const html = render(<WidgetChart series={[5, 5, 5, 5]} />);
    expect(html).not.toContain("NaN");
  });

  it("el trazo no se deforma al estirar el lienzo", () => {
    expect(render(<WidgetChart series={[1, 4, 2]} />)).toContain('vector-effect="non-scaling-stroke"');
  });

  it("las etiquetas solo se pintan si hay una por barra", () => {
    const bien = render(<WidgetBars series={[1, 2]} labels={["L", "M"]} />);
    const mal = render(<WidgetBars series={[1, 2, 3]} labels={["L", "M"]} />);

    expect(bien).toContain("chart-labels");
    expect(mal).not.toContain("chart-labels");
  });

  it("la barra de hoy se distingue de las demás", () => {
    expect(render(<WidgetBars series={[1, 2, 3]} highlight={1} />)).toContain("data-highlight");
  });

  it("las barras se escalan con transform y no con altura", () => {
    expect(render(<WidgetBars series={[5, 10]} />)).toContain("--bar:");
  });

  it("en el mapa de constancia, cero es su propio escalón", () => {
    const html = render(<WidgetHeatmap values={[0, 1, 4]} />);

    expect(html).toContain('data-level="0"');
    expect(html).toContain('data-level="4"');
  });
});

describe("el avance", () => {
  it("pasarse del objetivo llena la barra pero no la estira", () => {
    const html = render(<WidgetProgress value={140} target={100} />);

    expect(html).toContain("--filled:1");
    expect(html).toContain("data-done");
    expect(html).toContain("Objetivo cumplido");
  });

  it("sin objetivo no se inventa una fracción", () => {
    expect(render(<WidgetProgress value={50} target={0} />)).toContain("--filled:0");
  });

  it("la barra se anuncia como barra de progreso", () => {
    const html = render(<WidgetProgress value={25} target={100} />);
    expect(html).toContain('role="progressbar"');
    expect(html).toContain('aria-valuenow="25"');
  });

  it("el anillo descubre la porción que toca, sin pasarse", () => {
    const medio = render(<WidgetRing value={50} target={100} />);
    const pasado = render(<WidgetRing value={300} target={100} />);

    expect(medio).toContain("stroke-dashoffset");
    expect(pasado).toContain("stroke-dashoffset:0");
  });

  it("el anillo puede enseñar el porcentaje en vez del valor", () => {
    expect(render(<WidgetRing value={25} target={100} show="percent" />)).toContain("25%");
  });
});

describe("la racha", () => {
  it("concuerda el singular y el plural", () => {
    expect(render(<WidgetStreak current={1} />)).toContain("día");
    expect(render(<WidgetStreak current={4} />)).toContain("días");
  });

  it("los puntos cuentan tanto como el número", () => {
    const html = render(<WidgetStreak current={3} days={[true, false, true]} />);
    expect(html.match(/class="streak-day"/g)).toHaveLength(3);
  });

  it("no pinta más días de los que caben", () => {
    const html = render(<WidgetStreak current={40} days={Array(60).fill(true)} />);
    expect(html.match(/class="streak-day"/g)).toHaveLength(14);
  });
});

describe("el calendario", () => {
  it("la semana empieza en lunes", () => {
    const html = render(<WidgetCalendar month={new Date(2026, 8, 1)} />);
    const week = [...html.matchAll(/calendar-weekday"[^>]*>(\w)</g)].map((match) => match[1]);

    expect(week).toEqual(["L", "M", "X", "J", "V", "S", "D"]);
  });

  it("el día 1 cae en su columna", () => {
    const html = render(<WidgetCalendar month={new Date(2026, 8, 1)} />);
    expect(html.match(/data-empty="true"/g)).toHaveLength(1);
  });

  it("cuenta los días del mes sin tabla de longitudes", () => {
    const febrero = render(<WidgetCalendar month={new Date(2024, 1, 1)} />);
    expect(febrero.match(/role="gridcell"/g)).toHaveLength(29);
  });

  it("hoy gana al marcado", () => {
    const html = render(<WidgetCalendar month={new Date(2026, 8, 1)} marked={[4]} today={4} />);
    expect(html).toContain('data-marked="true" data-today="true"');
  });
});

describe("lo siguiente y los accesos", () => {
  it("sin nada a la vista lo dice", () => {
    expect(render(<WidgetUpNext events={[]} />)).toContain("Nada a la vista");
  });

  it("una fecha ilegible no rompe la fila", () => {
    const html = render(<WidgetUpNext events={[{ at: "no es una fecha", title: "Algo" }]} />);
    expect(html).toContain("Algo");
    expect(html).toContain("—");
  });

  it("los accesos directos son enlaces, no botones que ejecutan", () => {
    const html = render(
      <WidgetShortcuts actions={[{ label: "Entrenar", href: "/fitness", icon: "bolt" }]} />,
    );

    expect(html).toContain('href="/fitness"');
    expect(html).not.toContain("<button");
  });

  it("ni los accesos ni las cifras pequeñas pasan de cuatro", () => {
    const accesos = render(
      <WidgetShortcuts
        actions={Array.from({ length: 7 }, (_, index) => ({
          label: `A${index}`,
          href: `/a${index}`,
        }))}
      />,
    );
    const stats = render(
      <WidgetStats
        items={Array.from({ length: 7 }, (_, index) => ({ label: `S${index}`, value: index }))}
      />,
    );

    expect(accesos.match(/class="shortcut"/g)).toHaveLength(4);
    expect(stats.match(/class="stat"/g)).toHaveLength(4);
  });
});

describe("la tarjeta con símbolo", () => {
  it("pinta el símbolo del tono que se le pide, y no un color suyo", () => {
    const html = render(<WidgetKpi value="Pull" detail="rotación 7" icon="pull" hue={2} />);

    expect(html).toContain("kpi-icon");
    expect(html).toContain('data-hue="2"');
    expect(html).toContain("Pull");
  });

  it("sin símbolo, la tarjeta es la de siempre", () => {
    const html = render(<WidgetKpi value={1284} unit="pasos" />);

    expect(html).not.toContain("kpi-icon");
    expect(html).not.toContain("data-with-icon");
  });

  it("con símbolo, la cifra baja un paso para que no compitan", () => {
    const html = render(<WidgetKpi value="Push" icon="push" hue={4} />);

    expect(html).toContain("data-with-icon");
  });
});

describe("dónde se apoya una cifra", () => {
  it("una cifra va centrada en su tarjeta, con lo que la explica debajo", () => {
    const css = readFileSync(new URL("../library.css", import.meta.url), "utf8");
    const kpi = /\.kpi \{([^}]*)\}/.exec(css)?.[1] ?? "";

    expect(kpi).toContain("align-items: center");
    expect(kpi).toContain("justify-content: center");
    expect(kpi).toContain("text-align: center");
  });
});

describe("el objetivo cumplido se ve", () => {
  it("el anillo pasa a hecho: tick en el centro y la frase, sin la cifra", () => {
    const html = render(<WidgetRing value={3} target={3} label="de 3 esta semana" />);

    expect(html).toContain("data-done");
    expect(html).toContain("ring-check");
    expect(html).toContain("Cumplido · 3 de 3");
    expect(html).not.toContain("ring-figure");
    expect(html).toContain("objetivo cumplido");
  });

  it("a medias sigue siendo la cifra y la etiqueta del módulo", () => {
    const html = render(<WidgetRing value={2} target={3} label="de 3 esta semana" />);

    expect(html).not.toContain("data-done");
    expect(html).toContain("ring-figure");
    expect(html).toContain("de 3 esta semana");
  });

  it("donde hay sitio lo dice entero, y en un 1x1 solo queda el anillo", () => {
    const grande = render(
      <Widget title="Entreno" hue={4} size="4x2" shape="number" state="ready">
        <WidgetRing value={5} target={4} label="de 4 esta semana" />
      </Widget>,
    );
    const pequeno = render(
      <Widget title="Entreno" hue={4} size="1x1" shape="number" state="ready">
        <WidgetRing value={1} target={4} label="de 4 esta semana" />
      </Widget>,
    );

    expect(grande).toContain("Objetivo cumplido · 5 de 4");
    expect(pequeno).not.toContain("ring-label");
  });

  it("sin objetivo no hay nada que cumplir", () => {
    expect(render(<WidgetRing value={0} target={0} />)).not.toContain("data-done");
  });
});

describe("la placa de un icono", () => {
  it("lleva el tono y el icono dentro", () => {
    const html = render(<IconBadge name="kettlebell" hue={5} />);

    expect(html).toContain('class="icon-badge" data-hue="5"');
    expect(html).toContain("<svg");
  });
});

describe("un nombre en vez de una cifra", () => {
  it("se marca para partir en líneas en vez de salirse", () => {
    expect(render(<WidgetKpi value="Cuerpo entero" />)).toContain("data-text");
    expect(render(<WidgetKpi value={12} />)).not.toContain("data-text");
    expect(render(<WidgetKpi value="12" />)).not.toContain("data-text");
  });
});

describe("tres cifras", () => {
  it("en una tarjeta ancha van en fila, y en una estrecha no dejan una sola abajo", () => {
    const items = [
      { label: "Bancos", value: 2 },
      { label: "Cuentas", value: 5 },
      { label: "Última sincronización", value: "hace 2 h" },
    ];
    const ancha = render(
      <Widget title="Bancos" hue={2} size="4x2" shape="number" state="ready">
        <WidgetStats items={items} />
      </Widget>,
    );
    const estrecha = render(<WidgetStats items={items} />);

    expect(ancha).toContain("data-wide");
    expect(estrecha).not.toContain("data-wide");
    expect(readFileSync(new URL("../library.css", import.meta.url), "utf8")).toMatch(
      /\.stats\[data-count="3"\] > \.stat:first-child \{ grid-column: 1 \/ -1; \}/,
    );
  });
});
