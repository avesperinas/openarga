import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { AreaOrbs, AreaPanel, AreaPanelSkeleton, PageTabs, PanelBlockView, panelValue } from "../src/index";
import type { PanelTab } from "../src/index";

const render = (node: React.ReactElement) => renderToStaticMarkup(node);
const area = { key: "money", label: "Dinero", apps: "Money · Carrera", hue: 2 as const, icon: "€" };

describe("el panel de un área", () => {
  const tabs: PanelTab[] = [
    {
      id: "money.resumen",
      label: "Resumen",
      blocks: [
        { type: "figure", label: "Patrimonio", value: "48.320 €", delta: "+23 %", tone: "positive" },
        { type: "alert", text: "3 movimientos por etiquetar", href: "/money/movimientos" },
        { type: "list", rows: [{ label: "Fondos", value: "21.000 €" }], detail: true },
      ],
      actions: [{ label: "Abrir Money", href: "/money/", primary: true }],
    },
    { id: "study.renta", label: "Renta", blocks: [] },
  ];

  it("dice cómo va, la frase con su trozo destacado, las pestañas, sus bloques y sus botones", () => {
    const html = render(
      <AreaPanel area={area} headline={{ text: "Llegas a fin de mes con unos 420 €", emphasis: "unos 420 €", tone: "positive", status: "Vas bien" }} tabs={tabs} onExpand={() => undefined} />,
    );
    expect(html).toContain("Vas bien");
    expect(html).toContain("<em>unos 420 €</em>");
    expect(html.match(/role="tab"/g)).toHaveLength(2);
    expect(html).toContain("48.320 €");
    expect(html).toContain('href="/money/movimientos"');
    expect(html).toContain("Abrir Money");
    expect(html).toContain("Abrir Dinero en grande");
    expect(html).not.toContain("Fondos");
  });

  it("a pantalla completa enseña también lo de detalle y se cierra", () => {
    const html = render(<AreaPanel area={area} tabs={tabs} focus onExpand={() => undefined} />);
    expect(html).toContain("Fondos");
    expect(html).toContain("Cerrar Dinero");
  });

  it("una pestaña vacía lo dice", () => {
    expect(render(<AreaPanel area={area} tabs={[tabs[1]!]} />)).toContain("Aún no hay nada que contar");
  });
});

describe("los bloques", () => {
  it("las tareas se marcan y se añaden con su widget; sin quien actúe, no", () => {
    const block = { type: "tasks" as const, widget: "today", items: [{ id: "t1", title: "Pagar la comunidad", done: true }], add: "Añadir una tarea" };
    const acting = render(<PanelBlockView block={block} onAct={() => undefined} />);
    expect(acting).toContain('aria-pressed="true"');
    expect(acting).toContain('placeholder="Añadir una tarea"');
    const quiet = render(<PanelBlockView block={block} />);
    expect(quiet).toContain("disabled");
    expect(quiet).not.toContain("placeholder");
  });

  it("la línea dice de dónde a dónde va y se recorre con el teclado", () => {
    const html = render(<PanelBlockView block={{ type: "trend", unit: "money", points: [{ label: "dic", value: 39180 }, { label: "nov", value: 48320 }] }} />);
    expect(html).toContain("de 39.180 € a 48.320 €");
    expect(html).toContain('role="slider"');
  });

  it("los anillos, las barras, la silueta y el día", () => {
    expect(render(<PanelBlockView block={{ type: "rings", items: [{ label: "Sueño", value: "82", share: 0.82, hue: 1 }] }} />)).toContain("Sueño: 82");
    expect(render(<PanelBlockView block={{ type: "bars", labels: ["L", "M"], values: [6, 8], goal: 7.5, unit: "hours" }} />)).toContain("M 8 h");
    expect(render(<PanelBlockView block={{ type: "feature", title: "Pierna, hoy", body: ["legs"], action: "Empezar", href: "/training/" }} />)).toContain("data-on");
    const day = render(<PanelBlockView now={new Date("2026-11-06T17:40:00")} block={{ type: "timeline", items: [{ start: "2026-11-06T18:00:00", end: "2026-11-06T19:30:00", title: "Escalada", hue: 6 }] }} />);
    expect(day).toContain("panel-timeline-now");
    expect(day).toContain("Escalada");
  });

  it("cada unidad se escribe como se lee", () => {
    expect(panelValue(48320, "money")).toBe("48.320 €");
    expect(panelValue(74.2, "kg")).toBe("74,2 kg");
    expect(panelValue(7.2, "hours")).toBe("7 h 12 min");
  });
});

describe("las bolas", () => {
  it("cada área con su estado, para el lector de pantalla", () => {
    const html = render(<AreaOrbs items={[{ key: "money", label: "Dinero", status: "Vas bien", tone: "positive", hue: 2, icon: "€" }]} />);
    expect(html).toContain('aria-label="Dinero: Vas bien"');
    expect(html).toContain('data-tone="positive"');
  });
});

describe("el panel como página del ordenador", () => {
  const tabs: PanelTab[] = [
    { id: "resumen", label: "Resumen", blocks: [{ type: "figure", label: "Patrimonio", value: "48.320 €" }], actions: [{ label: "Abrir Money", href: "/money/" }] },
    { id: "gasto", label: "Gasto", blocks: [{ type: "list", rows: [{ label: "Casa", value: "640 €" }], detail: true }] },
  ];

  it("enseña todas las pestañas a la vez, cada una en su columna con su detalle, sin lista de pestañas", () => {
    const html = render(<AreaPanel area={area} tabs={tabs} board />);
    expect(html).toContain('data-board="true"');
    expect(html).not.toContain('role="tablist"');
    expect(html).toContain("48.320 €");
    expect(html).toContain("640 €");
    expect((html.match(/class="area-panel-column"/g) ?? []).length).toBe(2);
    expect(html).toContain('href="/money/"');
  });

  it("mientras llega, su cabecera de verdad y el cuerpo en reposo", () => {
    const html = render(<AreaPanelSkeleton area={area} />);
    expect(html).toContain("Dinero");
    expect(html).toContain('aria-busy="true"');
  });
});

describe("las pestañas de las páginas", () => {
  it("una por página, la que se mira encendida", () => {
    const html = render(
      <PageTabs items={[{ key: "money", label: "Dinero", hue: 2 }, { key: "widgets", label: "Widgets" }]} current={1} onSelect={() => undefined} />,
    );
    expect(html).toContain('role="tablist"');
    expect(html).toMatch(/aria-selected="true"[^>]*>Widgets/);
    expect(html).toMatch(/aria-selected="false"[^>]*>Dinero/);
  });
});

describe("el mes en un panel", () => {
  it("con entradas, el mes que dice qué hay cada día", () => {
    const html = render(
      <PanelBlockView
        block={{
          type: "month",
          month: "2026-11",
          today: 9,
          marked: [9, 12],
          entries: [
            { start: "2026-11-09T09:00:00+01:00", end: "2026-11-09T10:00:00+01:00", title: "Daily", tone: 1 },
            { start: "2026-11-12", end: "2026-11-13", all_day: true, title: "Viaje", tone: 7 },
          ],
        }}
      />,
    );
    expect(html).toContain("month-entries");
  });

  it("sin entradas, el mes de siempre con sus días marcados", () => {
    const html = render(<PanelBlockView block={{ type: "month", month: "2026-11", today: 9, marked: [3] }} />);
    expect(html).toContain('class="calendar"');
  });
});
