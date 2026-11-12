import { Writable } from "node:stream";

import * as React from "react";
import { renderToPipeableStream, renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { DesktopLayout } from "../lib/kernel";
import type { Contributor } from "../lib/panels";
import { Dashboard } from "./Dashboard";
import { Ask, HomeProvider, PanelPage } from "./Home";
import { HomePanelsSettings } from "./Settings";

const money: Contributor = {
  source: "money",
  name: "Money",
  panel: {
    area: "money",
    headlines: [{ text: "Llegas a fin de mes con 420 € de margen", emphasis: "420 €", tone: "positive", status: "+420 €" }],
    tabs: [
      { id: "resumen", label: "Resumen", blocks: [{ type: "figure", label: "Patrimonio", value: "48.200 €" }] },
      { id: "gasto", label: "Gasto", blocks: [{ type: "figure", label: "Este mes", value: "1.240 €" }] },
    ],
  },
};

const layout: DesktopLayout = { updated_at: null, default: true, placements: {}, pages: [{ id: "una", items: [] }] };

const stream = (element: React.ReactElement, arrive: () => void) =>
  new Promise<{ first: string; all: string }>((resolve, reject) => {
    let html = "";
    let first = "";
    const sink = new Writable({
      write(chunk, _encoding, done) {
        html += chunk.toString();
        done();
      },
      final(done) {
        resolve({ first, all: html });
        done();
      },
    });
    const { pipe } = renderToPipeableStream(element, {
      onShellReady() {
        pipe(sink);
        setTimeout(() => {
          first = html;
          arrive();
        }, 20);
      },
      onShellError: reject,
      onError: reject,
    });
  });

describe("los paneles como páginas", () => {
  it("un panel es un widget más: comparte pantalla con los otros y da nombre a su pestaña", async () => {
    let arrive!: (found: Contributor[]) => void;
    const pending = new Promise<Contributor[]>((resolve) => (arrive = resolve));
    const mixed: DesktopLayout = {
      ...layout,
      pages: [
        {
          id: "dinero",
          items: [
            { instance_id: "p", source: "panel", widget: "money", size: "4x6" },
            { instance_id: "t", source: "panel", widget: "money.tab", size: "2x2", option: "money.gasto" },
          ],
        },
        { id: "otra", items: [] },
      ],
    };
    const { first, all } = await stream(
      <HomeProvider>
        <Dashboard desks={{ mobile: mixed, desktop: mixed }} device="mobile" catalogue={[]} panels={{ money: pending }} />
      </HomeProvider>,
      () => arrive([money]),
    );
    const tabs = [...first.matchAll(/class="page-tab"[^>]*>(?:<span[^>]*>.*?<\/span>)?([^<]+)<\/button>/g)].map((match) => match[1]);
    expect(tabs).toEqual(["Dinero", "Widgets"]);
    expect(first).toContain('aria-busy="true"');
    expect(first).not.toContain("420 €");
    expect(all).toContain("Llegas a fin de mes con");
    expect(all).toContain("1.240 €");
    expect((all.match(/data-single=""/g) ?? []).length).toBe(1);
  });

  it("en el móvil, una pestaña cada vez; en el ordenador, todas a la vez en columnas", async () => {
    const ready = Promise.resolve([money]);
    const mobile = await stream(<PanelPage area="money" initial={ready} board={false} />, () => {});
    const desktop = await stream(<PanelPage area="money" initial={ready} board />, () => {});
    expect(mobile.all).toContain('role="tablist"');
    expect(mobile.all).toContain("48.200 €");
    expect(mobile.all).not.toContain("1.240 €");
    expect(desktop.all).toContain("area-panel-board");
    expect(desktop.all).toContain("48.200 €");
    expect(desktop.all).toContain("1.240 €");
  });

  it("en edición, cada página de panel se mueve y se quita", () => {
    const html = renderToStaticMarkup(<PanelPage area="health" board={false} editing first />);
    expect(html).toContain("Quitar el panel de Salud");
    expect(html).toMatch(/disabled=""[^>]*aria-label="Mover Salud a la izquierda"/);
  });

  it("la pregunta sale arriba sin pedir nada al abrir", () => {
    const html = renderToStaticMarkup(
      <HomeProvider>
        <Ask />
      </HomeProvider>,
    );
    expect(html).toContain('aria-label="Pregunta a tus apps"');
  });
});

describe("ajustes del inicio", () => {
  it("las siete áreas en el orden guardado; sin elegir, encendidas solo las de partida", () => {
    const chosen = renderToStaticMarkup(
      <HomePanelsSettings
        preferences={{ theme: "system", wallpaper: "", glass_opacity: 1, home_panels: { order: ["money"], hidden: ["mind"] } }}
        onChange={() => {}}
      />,
    );
    expect(chosen.indexOf("Dinero")).toBeLessThan(chosen.indexOf("Día"));
    expect((chosen.match(/role="switch"/g) ?? []).length).toBe(7);
    expect((chosen.match(/aria-checked="true"/g) ?? []).length).toBe(6);

    const fresh = renderToStaticMarkup(<HomePanelsSettings preferences={{ theme: "system", wallpaper: "", glass_opacity: 1 }} onChange={() => {}} />);
    expect((fresh.match(/aria-checked="true"/g) ?? []).length).toBe(3);
  });
});
