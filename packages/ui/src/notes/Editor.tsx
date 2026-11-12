import { type Completion, type CompletionContext, autocompletion, closeBrackets, closeBracketsKeymap, completionKeymap } from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { highlightSelectionMatches, search, searchKeymap } from "@codemirror/search";
import { EditorState, type Extension, RangeSetBuilder, StateField } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView, drawSelection, keymap, placeholder as placeholderText } from "@codemirror/view";
import { tags } from "@lezer/highlight";
import * as React from "react";

import { livePreview } from "./livePreview";
import { argaBlock } from "./markdown";

const style = HighlightStyle.define([
  { tag: tags.strong, class: "cm-mn-strong" },
  { tag: tags.emphasis, class: "cm-mn-em" },
  { tag: tags.strikethrough, class: "cm-mn-strike" },
  { tag: tags.monospace, class: "cm-mn-code" },
  { tag: tags.link, class: "cm-mn-mdlink" },
  { tag: tags.url, class: "cm-mn-url" },
  { tag: tags.quote, class: "cm-mn-quote-text" },
  { tag: tags.processingInstruction, class: "cm-mn-faint" },
  { tag: tags.meta, class: "cm-mn-faint" },
]);

export interface Suggestions {
  notes: { title: string; folder: string }[];
  tags: string[];
  links?: { target: string; title: string; kind: string }[];
}

export function protectArgaBlock(): Extension {
  const lines = StateField.define<DecorationSet>({
    create: (state) => argaLines(state.doc.toString(), state),
    update: (value, tr) => (tr.docChanged ? argaLines(tr.state.doc.toString(), tr.state) : value),
    provide: (field) => EditorView.decorations.from(field),
  });
  return [
    EditorState.changeFilter.of((tr) => {
      const found = argaBlock(tr.startState.doc.toString());
      if (!found) return true;
      return [found.start, Math.max(found.start, found.end - 1)];
    }),
    lines,
  ];
}

function argaLines(text: string, state: EditorState): DecorationSet {
  const found = argaBlock(text);
  const builder = new RangeSetBuilder<Decoration>();
  if (!found) return builder.finish();
  const mark = Decoration.line({ class: "cm-mn-arga" });
  const last = state.doc.lineAt(Math.max(found.start, found.end - 1)).number;
  for (let number = state.doc.lineAt(found.start).number; number <= last; number += 1) {
    const line = state.doc.line(number);
    builder.add(line.from, line.from, mark);
  }
  return builder.finish();
}

export function linkCompletions(suggestions: () => Suggestions) {
  return (context: CompletionContext) => {
    const before = context.matchBefore(/!?\[\[[^\]|#\n]*$/);
    if (!before) return null;
    const open = before.text.indexOf("[[") + 2;
    const after = context.state.sliceDoc(context.pos, context.pos + 2);
    const titles = suggestions().notes;
    const counts = new Map<string, number>();
    for (const note of titles) counts.set(note.title.toLowerCase(), (counts.get(note.title.toLowerCase()) ?? 0) + 1);
    const options: Completion[] = titles.map((note) => {
      const target = (counts.get(note.title.toLowerCase()) ?? 0) > 1 && note.folder ? `${note.folder}/${note.title}` : note.title;
      return {
        label: note.title,
        detail: note.folder || undefined,
        apply: (view: EditorView, _completion: Completion, from: number, to: number) => {
          const insert = after === "]]" ? target : `${target}]]`;
          view.dispatch({ changes: { from, to, insert }, selection: { anchor: from + target.length + 2 } });
        },
        type: "text",
      };
    });
    for (const link of suggestions().links ?? []) {
      const written = `${link.target}|${link.title}`;
      options.push({
        label: link.title,
        detail: link.kind,
        apply: (view: EditorView, _completion: Completion, from: number, to: number) => {
          const insert = after === "]]" ? written : `${written}]]`;
          view.dispatch({ changes: { from, to, insert }, selection: { anchor: from + written.length + 2 } });
        },
        type: "class",
      });
    }
    return { from: before.from + open, options, validFor: /^[^\]|#\n]*$/ };
  };
}

export function tagCompletions(suggestions: () => Suggestions) {
  return (context: CompletionContext) => {
    const before = context.matchBefore(/(?:^|\s)#[\p{L}\p{N}_/-]*$/u);
    if (!before) return null;
    const hash = before.text.lastIndexOf("#");
    if (!context.explicit && before.text.length - hash < 2) return null;
    return {
      from: before.from + hash + 1,
      options: suggestions().tags.map((tag) => ({ label: tag, type: "keyword" })),
      validFor: /^[\p{L}\p{N}_/-]*$/u,
    };
  };
}

export function endEmptyItem(view: EditorView): boolean {
  const { state } = view;
  const range = state.selection.main;
  if (!range.empty) return false;
  const line = state.doc.lineAt(range.head);
  if (range.head !== line.to || !/^\s*(?:[-*+]|\d+[.)])(?: \[[ xX]\])?\s*$/.test(line.text)) return false;
  view.dispatch({ changes: { from: line.from, to: line.to, insert: "" } });
  return true;
}

interface Props {
  id: string;
  value: string;
  onChange: (value: string) => void;
  suggestions: () => Suggestions;
  onOpenLink: (target: string, heading: string | null) => void;
  onTag: (tag: string) => void;
  onImage: (file: File) => Promise<string>;
  autoFocus?: boolean;
  placeholder?: string;
  onReady?: (view: EditorView | null) => void;
}

export function wrapSelection(view: EditorView, mark: string): void {
  const range = view.state.selection.main;
  const selected = view.state.sliceDoc(range.from, range.to);
  view.dispatch({
    changes: { from: range.from, to: range.to, insert: `${mark}${selected}${mark}` },
    selection: { anchor: range.from + mark.length, head: range.to + mark.length },
  });
  view.focus();
}

export function toggleLinePrefix(view: EditorView, prefix: string): void {
  const line = view.state.doc.lineAt(view.state.selection.main.head);
  const has = line.text.startsWith(prefix);
  view.dispatch({
    changes: has ? { from: line.from, to: line.from + prefix.length, insert: "" } : { from: line.from, insert: prefix },
  });
  view.focus();
}

export function insertBlock(view: EditorView, text: string): void {
  const at = view.state.selection.main.head;
  const before = view.state.sliceDoc(Math.max(0, at - 1), at);
  const insert = `${before && before !== "\n" ? "\n" : ""}${text}\n`;
  view.dispatch({ changes: { from: at, insert }, selection: { anchor: at + insert.length } });
  view.focus();
}

export function Editor({
  id,
  value,
  onChange,
  suggestions,
  onOpenLink,
  onTag,
  onImage,
  autoFocus,
  placeholder = "Escribe. [[ enlaza otra nota, # pone un tag.",
  onReady,
}: Props) {
  const host = React.useRef<HTMLDivElement>(null);
  const view = React.useRef<EditorView | null>(null);
  const callbacks = React.useRef({ onChange, suggestions, onOpenLink, onTag, onImage, onReady });
  callbacks.current = { onChange, suggestions, onOpenLink, onTag, onImage, onReady };

  React.useEffect(() => {
    const insertImages = (files: File[], at: number, editor: EditorView) => {
      for (const file of files) {
        void callbacks.current.onImage(file).then((written) => {
          editor.dispatch({ changes: { from: at, insert: `${written}\n` } });
        });
      }
    };
    const state = EditorState.create({
      doc: value,
      extensions: [
        history(),
        drawSelection(),
        EditorView.lineWrapping,
        keymap.of([{ key: "Enter", run: endEmptyItem }]),
        markdown({ base: markdownLanguage, addKeymap: true }),
        syntaxHighlighting(style),
        livePreview,
        protectArgaBlock(),
        closeBrackets(),
        autocompletion({
          override: [linkCompletions(() => callbacks.current.suggestions()), tagCompletions(() => callbacks.current.suggestions())],
          icons: false,
        }),
        search({ top: true }),
        highlightSelectionMatches(),
        placeholderText(placeholder),
        keymap.of([...closeBracketsKeymap, ...completionKeymap, ...searchKeymap, ...historyKeymap, indentWithTab, ...defaultKeymap]),
        EditorView.contentAttributes.of({ "aria-label": "Texto de la nota", spellcheck: "true", autocapitalize: "sentences" }),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) callbacks.current.onChange(update.state.doc.toString());
        }),
        EditorView.domEventHandlers({
          mousedown: (event) => {
            const target = event.target as HTMLElement;
            const link = target.closest<HTMLElement>(".cm-mn-link");
            if (link?.dataset.target !== undefined) {
              event.preventDefault();
              callbacks.current.onOpenLink(link.dataset.target, link.dataset.heading ?? null);
              return true;
            }
            const tag = target.closest<HTMLElement>(".cm-mn-tag");
            if (tag?.dataset.tag && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              callbacks.current.onTag(tag.dataset.tag);
              return true;
            }
            return false;
          },
          paste: (event, editor) => {
            const files = Array.from(event.clipboardData?.files ?? []).filter((file) => file.type.startsWith("image/"));
            if (!files.length) return false;
            event.preventDefault();
            insertImages(files, editor.state.selection.main.head, editor);
            return true;
          },
          drop: (event, editor) => {
            const files = Array.from(event.dataTransfer?.files ?? []).filter((file) => file.type.startsWith("image/"));
            if (!files.length) return false;
            event.preventDefault();
            const at = editor.posAtCoords({ x: event.clientX, y: event.clientY }) ?? editor.state.selection.main.head;
            insertImages(files, at, editor);
            return true;
          },
        }),
      ],
    });
    const created = new EditorView({ state, parent: host.current! });
    view.current = created;
    callbacks.current.onReady?.(created);
    if (autoFocus) created.focus();
    return () => {
      callbacks.current.onReady?.(null);
      created.destroy();
      view.current = null;
    };
  }, [id]);

  React.useEffect(() => {
    const editor = view.current;
    if (!editor || editor.state.doc.toString() === value) return;
    editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: value }, filter: false });
  }, [value]);

  return <div className="mn-editor" ref={host} />;
}
