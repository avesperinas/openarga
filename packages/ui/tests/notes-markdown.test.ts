import { describe, expect, it } from "vitest";

import { argaBlock, linkText, render, slug, split, toggleTask, wikilink } from "../src/notes/markdown";

describe("el Markdown de Obsidian", () => {
  it("quita el frontmatter y cuenta sus líneas", () => {
    expect(split("---\na: 1\nb: 2\n---\n# T\n")).toEqual({ frontmatter: "a: 1\nb: 2", body: "# T\n", offset: 4 });
    expect(split("# Sin\n").offset).toBe(0);
  });

  it("parte un enlace con carpeta, parte y alias, y el \\| de una tabla", () => {
    expect(wikilink("B1/DE 2.3 Perfekt#Formen|Perfekt")).toEqual({
      target: "B1/DE 2.3 Perfekt",
      heading: "Formen",
      alias: "Perfekt",
      embed: false,
    });
    expect(wikilink("Dativ\\|el dativo")?.alias).toBe("el dativo");
    expect(linkText(wikilink("B1/Nota#Parte")!)).toBe("Nota › Parte");
  });

  it("pinta un enlace resuelto como enlace a su nota y uno que falta como que falta", () => {
    const html = render("Ver [[Uno]] y [[Dos|el dos]].", { resolve: (t) => (t === "Uno" ? "id-1" : null) });

    expect(html).toContain('<a class="mn-link" data-target="Uno" href="/notebook/nota/id-1">Uno</a>');
    expect(html).toContain('data-target="Dos" href="#" data-missing="">el dos</a>');
  });

  it("dentro de una tabla, el enlace con alias no parte la celda", () => {
    const html = render("| a | b |\n|---|---|\n| [[X\\|equis]] | 2 |");

    expect(html).toContain(">equis</a></td>");
    expect(html).toContain("<td>2</td>");
  });

  it("no pinta enlaces ni tags dentro del código", () => {
    const html = render("`[[no]]` y\n\n```\n#no [[no]]\n```\n");

    expect(html).not.toContain("mn-link");
    expect(html).not.toContain("mn-tag");
  });

  it("un tag es un enlace a buscarlo; un número o un encabezado no", () => {
    const html = render("# Título\n\nHola #deutsch/b1 y #42");

    expect(html).toContain('data-tag="deutsch/b1">#deutsch/b1</a>');
    expect(html).not.toContain('data-tag="42"');
    expect(html).toContain('<h1 data-line="0" id="título">Título</h1>');
  });

  it("los callouts llevan su tipo y su título", () => {
    const html = render("> [!warning] Ojo\n> Esto importa.");

    expect(html).toContain('class="mn-callout" data-callout="warning"');
    expect(html).toContain('<p class="mn-callout-title">Ojo</p>');
    expect(html).toContain("Esto importa.");
  });

  it("las casillas, el resaltado y las notas al pie", () => {
    const html = render("- [x] hecho\n- [ ] no\n\nEs ==clave==.[^1]\n\n[^1]: Nota.");

    expect(html).toContain('<input class="mn-check" type="checkbox" disabled checked> hecho');
    expect(html).toContain("<mark>clave</mark>");
    expect(html).toContain('class="footnotes"');
  });

  it("el HTML escrito sale escapado", () => {
    const html = render('<script>alert(1)</script> [x](javascript:alert(1)) [[<img src=x onerror=1>]]');

    expect(html).not.toContain("<script>");
    expect(html).not.toContain('href="javascript:');
    expect(html).not.toContain("<img src=x");
  });

  it("la línea de cada bloque es la del texto entero, frontmatter incluido", () => {
    expect(render("---\na: 1\n---\nUno\n\nDos")).toContain('<p data-line="5">Dos</p>');
  });

  it("los comentarios de Obsidian no se ven", () => {
    expect(render("Sí %%no%% sí")).toBe("<p data-line=\"0\">Sí  sí</p>\n");
  });

  it("un enlace externo se abre fuera", () => {
    expect(render("[x](https://example.org)")).toContain('target="_blank" rel="noopener noreferrer"');
  });

  it("el slug de un encabezado es estable", () => {
    expect(slug("Präpositionen mit Dativ!")).toBe("präpositionen-mit-dativ");
  });

  it("con casillas que se marcan, cada una dice cuál es, y marcarla cambia la suya", () => {
    const text = "- [ ] uno\n```\n- [ ] código\n```\n- [x] dos";

    expect(render(text, { tasks: true })).toContain('data-task="1" checked>');
    expect(toggleTask(text, 0)).toBe("- [x] uno\n```\n- [ ] código\n```\n- [x] dos");
    expect(toggleTask(text, 1)).toBe("- [ ] uno\n```\n- [ ] código\n```\n- [ ] dos");
  });

  it("un enlace a otra app lleva a su sitio con su nombre, y sin saberlo se queda en texto", () => {
    const appLink = (target: string) => (target === "training:v-1" ? { href: "/training/stats?variante=v-1", title: "Press banca" } : null);

    expect(render("[[training:v-1]] y [[training:v-9|otra]]", { appLink })).toContain(
      '<a class="mn-app-link" href="/training/stats?variante=v-1" data-app="training:v-1">Press banca</a>',
    );
    expect(render("[[training:v-9|otra]]", { appLink })).toContain('<span class="mn-app-link" title="training:v-9">otra</span>');
  });

  it("el primer encabezado no se repite si es el título que ya se enseña", () => {
    expect(render("# DE 1.1 Kasus\n\nKern", { title: "de 1.1 kasus" })).toBe('<p data-line="2">Kern</p>\n');
    expect(render("# Otro\n\nKern", { title: "DE 1.1 Kasus" })).toContain("<h1");
  });

  it("encuentra el bloque de arga fuera del frontmatter", () => {
    const text = "---\narga: library:1\n---\n%% arga %%\n**Autor**\n\n## Lectura\n%% /arga %%\n\nMío.";
    const found = argaBlock(text);
    expect(found?.inner).toBe("**Autor**\n\n## Lectura");
    expect(text.slice(found!.end)).toBe("\nMío.");
    expect(argaBlock("Sin bloque %% arga %% en línea")).toBeNull();
  });

  it("un enlace a algo de otra app con ficha lleva a la ficha", () => {
    const html = render("[[library:1|El libro]] y [[training:2]]", {
      resolve: (target) => (target === "library:1" ? "nota-1" : null),
      appLink: (target) => (target === "training:2" ? { href: "/training/2", title: "Press" } : null),
    });
    expect(html).toContain('<a class="mn-link" data-target="library:1" href="/notebook/nota/nota-1">El libro</a>');
    expect(html).toContain('<a class="mn-app-link" href="/training/2" data-app="training:2">Press</a>');
  });
});
