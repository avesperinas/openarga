import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { ensureSyntaxTree } from "@codemirror/language";
import { EditorState } from "@codemirror/state";
import { describe, expect, it } from "vitest";

import { decorations } from "../src/notes/livePreview";

function shown(doc: string, focusedLine: number | null = null): string[] {
  let state = EditorState.create({ doc, extensions: [markdown({ base: markdownLanguage })] });
  ensureSyntaxTree(state, state.doc.length, 5000);
  state = state.update(focusedLine === null ? {} : { selection: { anchor: state.doc.line(focusedLine).from } }).state;
  const view = {
    state,
    hasFocus: focusedLine !== null,
    visibleRanges: [{ from: 0, to: state.doc.length }],
  } as unknown as Parameters<typeof decorations>[0];
  const hidden: [number, number][] = [];
  decorations(view).between(0, state.doc.length, (from, to, value) => {
    if (value.spec.widget === undefined && !value.spec.class && !value.spec.attributes && from !== to) hidden.push([from, to]);
  });
  let out = "";
  for (let i = 0; i < doc.length; i += 1) if (!hidden.some(([a, b]) => i >= a && i < b)) out += doc[i];
  return out.split("\n");
}

describe("la vista viva", () => {
  it("esconde las marcas de un encabezado, la negrita y un enlace", () => {
    expect(shown("# Título\n\nEs **clave** y [[DE 1.1 Kasus|Kasus]] y [[Otra]] y ==esto==.")).toEqual([
      "Título",
      "",
      "Es clave y Kasus y Otra y esto.",
    ]);
  });

  it("en la línea del cursor, todo es texto", () => {
    expect(shown("# Título\n\nEs **clave**.", 3)).toEqual(["Título", "", "Es **clave**."]);
  });

  it("la cabecera de un callout no es un enlace", () => {
    expect(shown("> [!tip] Truco\n> Texto")).toEqual(["> [!tip] Truco", "> Texto"]);
  });

  it("no toca lo que está en código", () => {
    expect(shown("`[[no]]` y **sí**")).toEqual(["[[no]] y sí"]);
  });
});
