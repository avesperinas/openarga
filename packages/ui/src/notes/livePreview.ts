import { syntaxTree } from "@codemirror/language";
import { type EditorState, type Range, RangeSetBuilder } from "@codemirror/state";
import {
  Decoration,
  type DecorationSet,
  type EditorView,
  ViewPlugin,
  type ViewUpdate,
  WidgetType,
} from "@codemirror/view";

import { wikilink } from "./markdown";

const HIDDEN_MARKS = new Set(["HeaderMark", "EmphasisMark", "CodeMark", "StrikethroughMark", "LinkMark", "URL"]);
const LINE_CLASS: Record<string, string> = {
  ATXHeading1: "cm-mn-h1",
  ATXHeading2: "cm-mn-h2",
  ATXHeading3: "cm-mn-h3",
  ATXHeading4: "cm-mn-h4",
  ATXHeading5: "cm-mn-h5",
  ATXHeading6: "cm-mn-h6",
  Blockquote: "cm-mn-quote",
  FencedCode: "cm-mn-codeblock",
};

const WIKILINK = /(!?)\[\[([^[\]\n]+?)\]\]/g;
const TAG = /(^|\s)(#[\p{L}\p{N}_/-]*[\p{L}_/-][\p{L}\p{N}_/-]*)/gu;
const HIGHLIGHT = /==([^=\n]+)==/g;

class CheckboxWidget extends WidgetType {
  constructor(
    readonly done: boolean,
    readonly at: number,
  ) {
    super();
  }
  eq(other: CheckboxWidget) {
    return other.done === this.done && other.at === this.at;
  }
  toDOM(view: EditorView) {
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = this.done;
    box.className = "cm-mn-check";
    box.setAttribute("aria-label", this.done ? "Hecha" : "Por hacer");
    box.addEventListener("mousedown", (event) => {
      event.preventDefault();
      view.dispatch({ changes: { from: this.at + 1, to: this.at + 2, insert: this.done ? " " : "x" } });
    });
    return box;
  }
  ignoreEvent() {
    return false;
  }
}

function activeLines(state: EditorState): Set<number> {
  const lines = new Set<number>();
  for (const range of state.selection.ranges) {
    const first = state.doc.lineAt(range.from).number;
    const last = state.doc.lineAt(range.to).number;
    for (let n = first; n <= last; n += 1) lines.add(n);
  }
  return lines;
}

function inCode(state: EditorState, at: number): boolean {
  for (let node: ReturnType<typeof syntaxTree>["topNode"] | null = syntaxTree(state).resolveInner(at, 1); node; node = node.parent) {
    if (node.name === "InlineCode" || node.name === "FencedCode" || node.name === "CodeBlock") return true;
  }
  return false;
}

export function decorations(view: EditorView): DecorationSet {
  const { state } = view;
  const active = view.hasFocus ? activeLines(state) : new Set<number>();
  const ranges: Range<Decoration>[] = [];
  const lineOf = (at: number) => state.doc.lineAt(at).number;

  for (const { from, to } of view.visibleRanges) {
    const text = state.doc.sliceString(from, to);
    const links = [...text.matchAll(WIKILINK)]
      .map((match) => ({ match, start: from + match.index!, end: from + match.index! + match[0].length }))
      .filter(({ start }) => !inCode(state, start));
    const insideLink = (a: number, b: number) => links.some(({ start, end }) => a < end && b > start);

    syntaxTree(state).iterate({
      from,
      to,
      enter: (node) => {
        if ((node.name === "Link" || HIDDEN_MARKS.has(node.name)) && insideLink(node.from, node.to)) return false;
        if (node.name === "Link" && state.doc.sliceString(node.from, node.from + 2) === "[!") return false;
        const lineClass = LINE_CLASS[node.name];
        if (lineClass) {
          const first = lineOf(node.from);
          const last = lineOf(node.to);
          for (let n = first; n <= last; n += 1) {
            ranges.push(Decoration.line({ class: lineClass }).range(state.doc.line(n).from));
          }
        }
        if (node.name === "TaskMarker" && !active.has(lineOf(node.from))) {
          const done = state.doc.sliceString(node.from + 1, node.from + 2).toLowerCase() === "x";
          ranges.push(Decoration.replace({ widget: new CheckboxWidget(done, node.from) }).range(node.from, node.to));
          return;
        }
        if (!HIDDEN_MARKS.has(node.name) || active.has(lineOf(node.from))) return;
        if (node.name === "URL" && node.node.parent?.name !== "Link") return;
        let end = node.to;
        if (node.name === "HeaderMark" && state.doc.sliceString(end, end + 1) === " ") end += 1;
        if (node.name === "CodeMark" && node.node.parent?.name === "FencedCode") return;
        ranges.push(Decoration.replace({}).range(node.from, end));
      },
    });

    for (const { match, start, end } of links) {
      const link = wikilink(match[2]!, match[1] === "!");
      if (!link) continue;
      const attributes: Record<string, string> = { "data-target": link.target };
      if (link.heading) attributes["data-heading"] = link.heading;
      const open = start + match[1]!.length + 2;
      const close = end - 2;
      if (active.has(lineOf(start))) {
        ranges.push(Decoration.mark({ class: "cm-mn-link-raw" }).range(start, end));
        continue;
      }
      const inner = state.doc.sliceString(open, close);
      const bar = inner.search(/\\?\|/);
      const shownFrom = bar >= 0 ? open + bar + (inner[bar] === "\\" ? 2 : 1) : open;
      ranges.push(Decoration.replace({}).range(start, shownFrom));
      ranges.push(
        Decoration.mark({ class: link.embed ? "cm-mn-link cm-mn-embed" : "cm-mn-link", attributes }).range(shownFrom, close),
      );
      ranges.push(Decoration.replace({}).range(close, end));
    }
    for (const match of text.matchAll(TAG)) {
      const start = from + match.index! + match[1]!.length;
      if (inCode(state, start) || insideLink(start, start + 1)) continue;
      ranges.push(
        Decoration.mark({ class: "cm-mn-tag", attributes: { "data-tag": match[2]!.slice(1) } }).range(start, start + match[2]!.length),
      );
    }
    for (const match of text.matchAll(HIGHLIGHT)) {
      const start = from + match.index!;
      const end = start + match[0].length;
      if (inCode(state, start) || insideLink(start, end)) continue;
      if (active.has(lineOf(start))) {
        ranges.push(Decoration.mark({ class: "cm-mn-mark" }).range(start, end));
      } else {
        ranges.push(Decoration.replace({}).range(start, start + 2));
        ranges.push(Decoration.mark({ class: "cm-mn-mark" }).range(start + 2, end - 2));
        ranges.push(Decoration.replace({}).range(end - 2, end));
      }
    }
  }
  return Decoration.set(ranges, true);
}

export const livePreview = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;
    constructor(view: EditorView) {
      this.decorations = safe(view);
    }
    update(update: ViewUpdate) {
      const parsed = syntaxTree(update.startState) !== syntaxTree(update.state);
      if (update.docChanged || update.viewportChanged || update.selectionSet || update.focusChanged || parsed) {
        this.decorations = safe(update.view);
      }
    }
  },
  { decorations: (plugin) => plugin.decorations },
);

function safe(view: EditorView): DecorationSet {
  try {
    return decorations(view);
  } catch {
    return new RangeSetBuilder<Decoration>().finish();
  }
}
