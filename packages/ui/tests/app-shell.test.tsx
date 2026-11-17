import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppShell } from "../src/index";

const tabs = [
  { id: "shelf" as const, label: "Shelf", icon: "book" as const },
  { id: "stats" as const, label: "Stats", icon: "chart" as const },
];

describe("AppShell", () => {
  it("with detail, it renders it next to the list and marks it for the CSS", () => {
    const html = renderToString(
      <AppShell label="Secciones" tabs={tabs} active="shelf" onSelect={() => undefined} detail={<p>Un libro</p>}>
        <p>The shelf</p>
      </AppShell>,
    );
    expect(html).toContain('data-detail="true"');
    expect(html).toContain('class="app-shell-main"><p>The shelf</p>');
    expect(html).toContain('class="app-shell-detail"><p>Un libro</p>');
    expect(html).toContain('aria-label="Secciones"');
  });

  it("without detail (or with `false`), the section takes everything", () => {
    const html = renderToString(
      <AppShell label="Secciones" tabs={tabs} active="stats" onSelect={() => undefined} detail={false}>
        <p>Cifras</p>
      </AppShell>,
    );
    expect(html).not.toContain("data-detail");
    expect(html).not.toContain("app-shell-detail");
  });

  it("without sections there is no bar or rail, and the detail is named", () => {
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
