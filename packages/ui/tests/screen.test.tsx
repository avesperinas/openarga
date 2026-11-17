import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";

import { Card, CreateButton, EmptyState, GroupLabel, Hint, Notice, Screen, Section } from "../src/index";

const css = readFileSync(new URL("../controls.css", import.meta.url), "utf8");

describe("an app's screen", () => {
  it("is a column that does not overflow on the right", () => {
    expect(renderToStaticMarkup(<Screen>x</Screen>)).toContain('<main class="screen"');
    expect(css).toMatch(/\.screen \{[^}]*grid-template-columns: minmax\(0, 1fr\)/);
  });

  it("leaves room below for the tabs and the create button", () => {
    expect(css).toMatch(/\.screen \{[^}]*var\(--tap-target\) \* 2\)/);
  });
});

describe("a section", () => {
  it("carries its title in bold, the count and the action", () => {
    const html = renderToStaticMarkup(
      <Section title="Pronto" count={2} action={{ label: "Ver todo", onClick: () => undefined }}>
        <p>fila</p>
      </Section>,
    );
    expect(html).toContain('<h2 class="section-title">Pronto<span class="section-count">2</span></h2>');
    expect(html).toContain("Ver todo");
    expect(css).toMatch(/\.section-title \{[^}]*font-weight: var\(--weight-bold\)/);
  });

  it("the small-caps grey belongs only to the row group", () => {
    expect(renderToStaticMarkup(<GroupLabel>Lácteos</GroupLabel>)).toContain('<h2 class="group-label"');
    expect(css).toMatch(/\.group-label \{[^}]*text-transform: uppercase/);
    expect(css).not.toMatch(/\.section-title \{[^}]*text-transform/);
  });
});

describe("a card", () => {
  it("is a whole control only if it leads somewhere", () => {
    expect(renderToStaticMarkup(<Card>x</Card>)).toMatch(/^<div class="surface card"/);
    expect(renderToStaticMarkup(<Card onClick={() => undefined}>x</Card>)).toMatch(/^<button class="surface card"[^>]*data-pressable/);
    expect(renderToStaticMarkup(<Card href="/a">x</Card>)).toMatch(/^<a class="surface card"[^>]*href="\/a"/);
  });
});

describe("the empty state", () => {
  it("says what is missing, why, and offers the action", () => {
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

describe("the helper line", () => {
  it("with `lines`, hand-written text keeps its line breaks", () => {
    expect(renderToStaticMarkup(<Hint lines>{"Primera\nSegunda"}</Hint>)).toContain('data-lines="true"');
    expect(renderToStaticMarkup(<Hint>Sin más</Hint>)).not.toContain("data-lines");
    expect(css).toMatch(/\.hint\[data-lines\] \{ white-space: pre-line; \}/);
  });
});

describe("create and notify", () => {
  it("create carries the name of what it creates", () => {
    expect(renderToStaticMarkup(<CreateButton label="Receta" onClick={() => undefined} />)).toContain("Receta");
  });

  it("an error notice is announced; a normal one does not interrupt", () => {
    expect(renderToStaticMarkup(<Notice tone="negative">Sin conexión</Notice>)).toContain('role="alert"');
    expect(renderToStaticMarkup(<Notice tone="warning">Caduca</Notice>)).toContain('role="status"');
  });
});

describe("a block with its actions behind a button", () => {
  it("puts the menu in the header, with its name, and without a title too", () => {
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

describe("what wraps the whole screen", () => {
  it("pull to refresh and sideways swipe keep the screen's column and gap", () => {
    expect(css).toMatch(/\.pull-to-refresh,\s*\.pull-to-refresh-content,\s*\.swipe-area \{[^}]*gap: inherit/);
  });
});
