import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";

import { Card, CreateButton, EmptyState, GroupLabel, Hint, Notice, Screen, Section } from "../src/index";

const css = readFileSync(new URL("../controls.css", import.meta.url), "utf8");

describe("la pantalla de una app", () => {
  it("es una columna que no se sale por la derecha", () => {
    expect(renderToStaticMarkup(<Screen>x</Screen>)).toContain('<main class="screen"');
    expect(css).toMatch(/\.screen \{[^}]*grid-template-columns: minmax\(0, 1fr\)/);
  });

  it("deja sitio abajo para las pestañas y el botón de crear", () => {
    expect(css).toMatch(/\.screen \{[^}]*var\(--tap-target\) \* 2\)/);
  });
});

describe("una sección", () => {
  it("lleva su título en negrita, la cuenta y la acción", () => {
    const html = renderToStaticMarkup(
      <Section title="Pronto" count={2} action={{ label: "Ver todo", onClick: () => undefined }}>
        <p>fila</p>
      </Section>,
    );
    expect(html).toContain('<h2 class="section-title">Pronto<span class="section-count">2</span></h2>');
    expect(html).toContain("Ver todo");
    expect(css).toMatch(/\.section-title \{[^}]*font-weight: var\(--weight-bold\)/);
  });

  it("el gris en versalitas es solo del grupo de filas", () => {
    expect(renderToStaticMarkup(<GroupLabel>Lácteos</GroupLabel>)).toContain('<h2 class="group-label"');
    expect(css).toMatch(/\.group-label \{[^}]*text-transform: uppercase/);
    expect(css).not.toMatch(/\.section-title \{[^}]*text-transform/);
  });
});

describe("una tarjeta", () => {
  it("es un control entero solo si lleva a algún sitio", () => {
    expect(renderToStaticMarkup(<Card>x</Card>)).toMatch(/^<div class="surface card"/);
    expect(renderToStaticMarkup(<Card onClick={() => undefined}>x</Card>)).toMatch(/^<button class="surface card"[^>]*data-pressable/);
    expect(renderToStaticMarkup(<Card href="/a">x</Card>)).toMatch(/^<a class="surface card"[^>]*href="\/a"/);
  });
});

describe("el estado vacío", () => {
  it("dice qué falta, por qué, y ofrece la acción", () => {
    const html = renderToStaticMarkup(
      <EmptyState icon="book" title="Todavía no hay libros" action={{ label: "Añadir libro", onClick: () => undefined }}>
        Busca el que estás leyendo.
      </EmptyState>,
    );
    expect(html).toContain("icon-badge");
    expect(html).toContain('<p class="empty-state-title">Todavía no hay libros</p>');
    expect(html).toContain("Añadir libro");
  });
});

describe("la línea que ayuda", () => {
  it("con `lines`, un texto escrito a mano guarda sus saltos de línea", () => {
    expect(renderToStaticMarkup(<Hint lines>{"Primera\nSegunda"}</Hint>)).toContain('data-lines="true"');
    expect(renderToStaticMarkup(<Hint>Sin más</Hint>)).not.toContain("data-lines");
    expect(css).toMatch(/\.hint\[data-lines\] \{ white-space: pre-line; \}/);
  });
});

describe("crear y avisar", () => {
  it("crear lleva el nombre de lo que crea", () => {
    expect(renderToStaticMarkup(<CreateButton label="Receta" onClick={() => undefined} />)).toContain("Receta");
  });

  it("un aviso de error se anuncia; uno normal, no interrumpe", () => {
    expect(renderToStaticMarkup(<Notice tone="negative">Sin conexión</Notice>)).toContain('role="alert"');
    expect(renderToStaticMarkup(<Notice tone="warning">Caduca</Notice>)).toContain('role="status"');
  });
});

describe("un bloque con sus acciones detrás de un botón", () => {
  it("pone el menú en la cabecera, con su nombre, y sin título también", () => {
    const html = renderToStaticMarkup(
      <Section title="07:45 · 400 kcal" menu={{ label: "Acciones de las 07:45", items: [{ label: "Borrar", onSelect: () => undefined }] }}>
        dentro
      </Section>,
    );
    expect(html).toContain('class="section-head"');
    expect(html).toContain("Acciones de las 07:45");
    const bare = renderToStaticMarkup(
      <Section menu={{ label: "Acciones", items: [{ label: "Borrar", onSelect: () => undefined }] }}>dentro</Section>,
    );
    expect(bare).toContain('class="section-head"');
  });
});

describe("lo que envuelve la pantalla entera", () => {
  it("tirar para refrescar y deslizar de lado guardan la columna y el hueco de la pantalla", () => {
    expect(css).toMatch(/\.pull-to-refresh,\s*\.pull-to-refresh-content,\s*\.swipe-area \{[^}]*gap: inherit/);
  });
});
