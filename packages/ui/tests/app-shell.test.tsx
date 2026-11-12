import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppShell } from "../src/index";

const tabs = [
  { id: "shelf" as const, label: "Estantería", icon: "book" as const },
  { id: "stats" as const, label: "Estadísticas", icon: "chart" as const },
];

describe("AppShell", () => {
  it("con detalle, lo pinta al lado de la lista y lo marca para el CSS", () => {
    const html = renderToString(
      <AppShell label="Secciones" tabs={tabs} active="shelf" onSelect={() => undefined} detail={<p>Un libro</p>}>
        <p>La estantería</p>
      </AppShell>,
    );
    expect(html).toContain('data-detail="true"');
    expect(html).toContain('class="app-shell-main"><p>La estantería</p>');
    expect(html).toContain('class="app-shell-detail"><p>Un libro</p>');
    expect(html).toContain('aria-label="Secciones"');
  });

  it("sin detalle (o con `false`), la sección ocupa todo", () => {
    const html = renderToString(
      <AppShell label="Secciones" tabs={tabs} active="stats" onSelect={() => undefined} detail={false}>
        <p>Cifras</p>
      </AppShell>,
    );
    expect(html).not.toContain("data-detail");
    expect(html).not.toContain("app-shell-detail");
  });

  it("sin secciones no hay barra ni rail, y el detalle se nombra", () => {
    const html = renderToString(
      <AppShell fill detail={<p>Cena</p>} detailLabel="Evento">
        <p>La semana</p>
      </AppShell>,
    );
    expect(html).toContain('data-bare="true"');
    expect(html).toContain('data-fill="true"');
    expect(html).not.toContain("tab-bar");
    expect(html).toContain('role="region" aria-label="Evento"><p>Cena</p>');
  });
});
