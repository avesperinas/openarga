import { EditorState } from "@codemirror/state";
import { describe, expect, it } from "vitest";

import { endEmptyItem, insertBlock, protectArgaBlock, toggleLinePrefix, wrapSelection } from "../src/notes/Editor";

function fake(doc: string, anchor: number, head = anchor) {
  let state = EditorState.create({ doc, selection: { anchor, head } });
  const view = {
    get state() {
      return state;
    },
    dispatch: (spec: Parameters<typeof state.update>[0]) => (state = state.update(spec).state),
    focus: () => undefined,
  };
  return view as never as Parameters<typeof wrapSelection>[0] & { state: EditorState };
}

describe("el editor", () => {
  it("Intro en una casilla vacía la quita", () => {
    let state = EditorState.create({ doc: "- [ ] uno\n- [ ] " });
    state = state.update({ selection: { anchor: state.doc.length } }).state;
    const view = { state, dispatch: (spec: Parameters<typeof state.update>[0]) => (state = state.update(spec).state) };

    expect(endEmptyItem(view as never)).toBe(true);
    expect(state.doc.toString()).toBe("- [ ] uno\n");
  });

  it("envuelve lo seleccionado y pone o quita un prefijo de línea", () => {
    const bold = fake("uno dos", 4, 7);
    wrapSelection(bold, "**");
    expect(bold.state.doc.toString()).toBe("uno **dos**");

    const heading = fake("título", 2);
    toggleLinePrefix(heading, "## ");
    expect(heading.state.doc.toString()).toBe("## título");
    toggleLinePrefix(heading, "## ");
    expect(heading.state.doc.toString()).toBe("título");
  });

  it("un bloque va en su propia línea", () => {
    const view = fake("texto", 5);
    insertBlock(view, "![foto](/x.png)");
    expect(view.state.doc.toString()).toBe("texto\n![foto](/x.png)\n");
  });

  it("no deja cambiar lo que escribe una app, y sí lo de antes y lo de después", () => {
    const doc = "Mío.\n\n%% arga %%\n### Training\n- Torso A\n%% /arga %%\n";
    let state = EditorState.create({ doc, extensions: [protectArgaBlock()] });
    const inside = doc.indexOf("Torso");
    state = state.update({ changes: { from: inside, to: inside + 5, insert: "Pierna" } }).state;
    expect(state.doc.toString()).toBe(doc);
    state = state.update({ changes: { from: 0, to: state.doc.length, insert: "" } }).state;
    expect(state.doc.toString()).toContain("%% arga %%\n### Training\n- Torso A\n%% /arga %%");
    state = EditorState.create({ doc, extensions: [protectArgaBlock()] });
    state = state.update({ changes: { from: 4, insert: " Y más." } }).state;
    state = state.update({ changes: { from: state.doc.length, insert: "Al final." } }).state;
    expect(state.doc.toString()).toBe("Mío. Y más.\n\n%% arga %%\n### Training\n- Torso A\n%% /arga %%\nAl final.");
  });
});
