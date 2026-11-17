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

describe("the live view", () => {
  it("hides the marks of a heading, bold and a link", () => {
    expect(shown("# Title\n\nIt is **key** and [[DE 1.1 Kasus|Kasus]] and [[Other]] and ==this==.")).toEqual([
      "Title",
      "",
      "It is key and Kasus and Other and this.",
    ]);
  });

  it("on the cursor line, everything is text", () => {
    expect(shown("# Title\n\nIt is **key**.", 3)).toEqual(["Title", "", "It is **key**."]);
  });

  it("a callout header is not a link", () => {
    expect(shown("> [!tip] Trick\n> Text")).toEqual(["> [!tip] Trick", "> Text"]);
  });

  it("no toca lo que está en código", () => {
    expect(shown("`[[no]]` y **sí**")).toEqual(["[[no]] y sí"]);
  });
});
