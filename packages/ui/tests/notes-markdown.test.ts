import { describe, expect, it } from "vitest";

import { argaBlock, linkText, render, slug, split, toggleTask, wikilink } from "../src/notes/markdown";

describe("Obsidian's Markdown", () => {
  it("strips the frontmatter and counts its lines", () => {
    expect(split("---\na: 1\nb: 2\n---\n# T\n")).toEqual({ frontmatter: "a: 1\nb: 2", body: "# T\n", offset: 4 });
    expect(split("# Sin\n").offset).toBe(0);
  });

  it("splits a link with folder, part and alias, and a table's \\|", () => {
    expect(wikilink("B1/DE 2.3 Perfekt#Formen|Perfekt")).toEqual({
      target: "B1/DE 2.3 Perfekt",
      heading: "Formen",
      alias: "Perfekt",
      embed: false,
    });
    expect(wikilink("Dativ\\|el dativo")?.alias).toBe("el dativo");
    expect(linkText(wikilink("B1/Note#Part")!)).toBe("Note › Part");
  });

  it("renders a resolved link as a link to its note and a missing one as missing", () => {
    const html = render("Ver [[Uno]] y [[Dos|el dos]].", { resolve: (t) => (t === "Uno" ? "id-1" : null) });

    expect(html).toContain('<a class="mn-link" data-target="Uno" href="/notebook/note/id-1">Uno</a>');
    expect(html).toContain('data-target="Dos" href="#" data-missing="">el dos</a>');
  });

  it("inside a table, an aliased link does not split the cell", () => {
    const html = render("| a | b |\n|---|---|\n| [[X\\|equis]] | 2 |");

    expect(html).toContain(">equis</a></td>");
    expect(html).toContain("<td>2</td>");
  });

  it("renders no links or tags inside code", () => {
    const html = render("`[[no]]` y\n\n```\n#no [[no]]\n```\n");

    expect(html).not.toContain("mn-link");
    expect(html).not.toContain("mn-tag");
  });

  it("a tag is a link to search for it; a number or a heading is not", () => {
    const html = render("# T\u00edtulo\n\nHello #deutsch/b1 and #42");

    expect(html).toContain('data-tag="deutsch/b1">#deutsch/b1</a>');
    expect(html).not.toContain('data-tag="42"');
    expect(html).toContain('<h1 data-line="0" id="t\u00edtulo">T\u00edtulo</h1>');
  });

  it("callouts carry their type and title", () => {
    const html = render("> [!warning] Ojo\n> Esto importa.");

    expect(html).toContain('class="mn-callout" data-callout="warning"');
    expect(html).toContain('<p class="mn-callout-title">Ojo</p>');
    expect(html).toContain("Esto importa.");
  });

  it("the checkboxes, highlighting and footnotes", () => {
    const html = render("- [x] hecho\n- [ ] no\n\nEs ==clave==.[^1]\n\n[^1]: Nota.");

    expect(html).toContain('<input class="mn-check" type="checkbox" disabled checked> hecho');
    expect(html).toContain("<mark>clave</mark>");
    expect(html).toContain('class="footnotes"');
  });

  it("written HTML comes out escaped", () => {
    const html = render('<script>alert(1)</script> [x](javascript:alert(1)) [[<img src=x onerror=1>]]');

    expect(html).not.toContain("<script>");
    expect(html).not.toContain('href="javascript:');
    expect(html).not.toContain("<img src=x");
  });

  it("each block's line is that of the whole text, frontmatter included", () => {
    expect(render("---\na: 1\n---\nUno\n\nDos")).toContain('<p data-line="5">Dos</p>');
  });

  it("Obsidian comments are hidden", () => {
    expect(render("Yes %%no%% yes")).toBe("<p data-line=\"0\">Yes  yes</p>\n");
  });

  it("an external link opens outside", () => {
    expect(render("[x](https://example.org)")).toContain('target="_blank" rel="noopener noreferrer"');
  });

  it("a heading's slug is stable", () => {
    expect(slug("Präpositionen mit Dativ!")).toBe("präpositionen-mit-dativ");
  });

  it("with checkable boxes, each says which it is, and ticking it changes its own", () => {
    const text = "- [ ] one\n```\n- [ ] code\n```\n- [x] two";

    expect(render(text, { tasks: true })).toContain('data-task="1" checked>');
    expect(toggleTask(text, 0)).toBe("- [x] one\n```\n- [ ] code\n```\n- [x] two");
    expect(toggleTask(text, 1)).toBe("- [ ] one\n```\n- [ ] code\n```\n- [ ] two");
  });

  it("a link to another app goes to its place with its name, and if unknown stays as text", () => {
    const appLink = (target: string) => (target === "training:v-1" ? { href: "/training/stats?variante=v-1", title: "Press banca" } : null);

    expect(render("[[training:v-1]] y [[training:v-9|otra]]", { appLink })).toContain(
      '<a class="mn-app-link" href="/training/stats?variante=v-1" data-app="training:v-1">Press banca</a>',
    );
    expect(render("[[training:v-9|otra]]", { appLink })).toContain('<span class="mn-app-link" title="training:v-9">otra</span>');
  });

  it("the first heading is not repeated if it is the title already shown", () => {
    expect(render("# DE 1.1 Kasus\n\nKern", { title: "de 1.1 kasus" })).toBe('<p data-line="2">Kern</p>\n');
    expect(render("# Otro\n\nKern", { title: "DE 1.1 Kasus" })).toContain("<h1");
  });

  it("finds the arga block outside the frontmatter", () => {
    const text = "---\narga: library:1\n---\n%% arga %%\n**Author**\n\n## Reading\n%% /arga %%\n\nMine.";
    const found = argaBlock(text);
    expect(found?.inner).toBe("**Author**\n\n## Reading");
    expect(text.slice(found!.end)).toBe("\nMine.");
    expect(argaBlock("No block %% arga %% inline")).toBeNull();
  });

  it("a link to another app's item with a page goes to the page", () => {
    const html = render("[[library:1|El libro]] y [[training:2]]", {
      resolve: (target) => (target === "library:1" ? "nota-1" : null),
      appLink: (target) => (target === "training:2" ? { href: "/training/2", title: "Press" } : null),
    });
    expect(html).toContain('<a class="mn-link" data-target="library:1" href="/notebook/note/nota-1">El libro</a>');
    expect(html).toContain('<a class="mn-app-link" href="/training/2" data-app="training:2">Press</a>');
  });
});
