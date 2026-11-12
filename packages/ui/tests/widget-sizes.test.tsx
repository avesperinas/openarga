import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  SIZES,
  Widget,
  WidgetCalendar,
  WidgetHeatmap,
  WidgetKpiDelta,
  WidgetList,
  WidgetProgress,
  WidgetStats,
  WidgetUpNext,
  type WidgetSize,
  dayLabel,
  fitsUncertaintyLine,
  layoutOf,
} from "../src/index";

const card = (size: WidgetSize, body: React.ReactNode) =>
  renderToStaticMarkup(
    <Widget title="Prueba" hue={1} size={size} shape="list" state="ready">
      {body}
    </Widget>,
  );

describe("la forma de cada tamaño (ADR-0086)", () => {
  it("las tiras son de una fila de alto", () => {
    expect(layoutOf("2x1")).toBe("strip");
    expect(layoutOf("4x1")).toBe("strip");
  });

  it("cada tamaño tiene su forma, y una desconocida cae a la de un 2x2", () => {
    expect(SIZES.map(layoutOf)).toEqual([
      "tiny",
      "strip",
      "strip",
      "narrow",
      "square",
      "tall",
      "wide",
      "large",
      "large",
]);
    expect(layoutOf("9x9")).toBe("square");
  });

  it("la tarjeta dice su forma, que es lo que lee el CSS", () => {
    expect(card("4x1", null)).toContain('data-layout="strip"');
  });

  it("una tira no tiene alto para la línea que cuantifica la duda", () => {
    expect(fitsUncertaintyLine("4x1")).toBe(false);
    expect(fitsUncertaintyLine("4x2")).toBe(true);
  });
});

const ROWS = [
  { label: "Pasar la ITV del coche", value: "hace 3 días", tone: "warning" as const },
  { label: "Llamar al fontanero", value: "10:00" },
  { label: "Devolver el libro", value: "hoy" },
];

describe("una lista según el hueco", () => {
  it("en media tarjeta, con un valor largo, cada fila va en dos líneas en vez de cortarse", () => {
    expect(card("2x2", <WidgetList rows={ROWS} />)).toContain("data-stacked");
    expect(card("2x2", <WidgetList rows={ROWS.slice(1)} />)).not.toContain("data-stacked");
  });

  it("en un 1x1 dice cuántas hay y avisa si alguna pide algo", () => {
    const html = card("1x1", <WidgetList rows={ROWS} />);
    expect(html).toContain(">3<");
    expect(html).toContain('data-tone="warning"');
  });

  it("en una tira, la primera y cuántas quedan", () => {
    const html = card("4x1", <WidgetList rows={ROWS} />);
    expect(html).toContain("Pasar la ITV del coche");
    expect(html).not.toContain("Llamar al fontanero");
    expect(html).toContain("+2");
  });

  it("en una ancha con muchas filas, dos columnas", () => {
    const many = Array.from({ length: 6 }, (_, index) => ({ label: `Fila ${index}`, value: "1" }));
    expect(card("4x2", <WidgetList rows={many} />)).toContain("data-columns");
  });
});

const NOW = new Date(2026, 8, 29, 10, 0);
const at = (days: number, hour: number) => new Date(2026, 8, 29 + days, hour, 0);

describe("lo siguiente según el hueco", () => {
  const events = [
    { at: at(0, 12), title: "Dentista" },
    { at: at(0, 18), title: "Cena" },
    { at: at(1, 10), title: "Taller" },
  ];

  it("en alto agrupa por día y dice el día una sola vez", () => {
    const html = card("2x4", <WidgetUpNext events={events} />);
    expect(html.match(/upnext-day-label/g)).toHaveLength(2);
  });

  it("en una tira es una sola línea", () => {
    const html = card("4x1", <WidgetUpNext events={events} />);
    expect(html).toContain("Dentista");
    expect(html).not.toContain("Cena");
  });

  it("el día se dice como se dice", () => {
    expect(dayLabel(at(0, 9), NOW)).toBe("Hoy");
    expect(dayLabel(at(1, 9), NOW)).toBe("Mañana");
    expect(dayLabel(at(2, 9), NOW)).toBe("Jueves");
  });
});

describe("el resto de cuerpos en sus tamaños nuevos", () => {
  it("una variación con serie dibuja su forma", () => {
    const html = card(
      "4x2",
      <WidgetKpiDelta value={74} previous={75} series={[76, 75, 74]} />,
    );
    expect(html).toContain("sparkline");
  });

  it("la barra marca por dónde tocaría ir", () => {
    const html = card("2x2", <WidgetProgress value={600} target={900} expected={450} />);
    expect(html).toContain("progress-pace");
    expect(html).toContain("--pace:0.5");
  });

  it("el mapa de constancia en una tira son los últimos días en fila", () => {
    const html = card("4x1", <WidgetHeatmap values={Array.from({ length: 100 }, () => 1)} />);
    expect(html.match(/heatmap-cell/g)).toHaveLength(21);
  });

  it("el calendario en una tira es la semana, y en un 1x1 el día de hoy", () => {
    expect(card("4x1", <WidgetCalendar marked={[1]} />).match(/calendar-week-day/g)).toHaveLength(7);
    expect(card("1x1", <WidgetCalendar marked={[1]} />)).toContain("calendar-today-date");
  });

  it("el mes con lo que hay no pinta nada en los días: lo cuenta en la columna de al lado", () => {
    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    const entries = [{ title: "Dentista", start: today, allDay: true, tone: 2 }];
    for (const size of ["4x2", "4x4", "2x4"] as WidgetSize[]) {
      const html = card(size, <WidgetCalendar entries={entries} />);
      expect(html).toContain("month-split");
      expect(html).not.toContain("entry-chip");
      expect(html).not.toContain("week-dot");
      expect(html).toContain("Dentista");
      expect(html).toMatch(/class="month-cell"[^>]*data-today="true"/);
    }
    const square = card("2x2", <WidgetCalendar entries={entries} />);
    expect(square).not.toContain("Dentista");
    expect(square).not.toContain("week-dot");
  });

  it("las cifras en un 1x1 se quedan en la primera", () => {
    const html = card(
      "1x1",
      <WidgetStats items={[{ label: "A", value: 1 }, { label: "B", value: 2 }]} />,
    );
    expect(html).toContain('data-count="1"');
  });
});

describe("una barra con techo (ADR-0086)", () => {
  it("pasarse de un presupuesto no es cumplirlo: se dice cuánto de más", () => {
    const html = card("2x2", <WidgetProgress value={1000} target={900} unit="€" goodWhen="down" />);
    expect(html).not.toContain("Objetivo cumplido");
    expect(html).toContain('data-standing="over"');
    expect(html).toContain("100 € de más");
  });

  it("ir por delante del ritmo se avisa antes de pasarse", () => {
    const html = card(
      "2x2",
      <WidgetProgress value={600} target={900} expected={450} goodWhen="down" />,
    );
    expect(html).toContain('data-standing="ahead"');
  });
});
