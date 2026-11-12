import { invalidate } from "@openarga/app";
import { Button, Collapsible, IconButton, SyncMark, type SyncState } from "@openarga/ui";
import { Editor, insertBlock, render, toggleLinePrefix, toggleTask, wrapSelection } from "@openarga/ui/notes";
import { type MouseEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { type Note, api } from "./api";
import { pathOf, useNavigate } from "./App";
import { reading } from "./order";
import { dateShort, plural } from "./words";

type EditorView = Parameters<typeof wrapSelection>[0];

const NO_SUGGESTIONS = () => ({ notes: [], tags: [] });

export interface NotePlace {
  course_id: string;
  subject_id?: string | null;
  session_id?: string | null;
}

const SAVE_AFTER_MS = 700;

export function continueList(text: string, caret: number): { text: string; caret: number } | null {
  const lineStart = text.lastIndexOf("\n", caret - 1) + 1;
  const line = text.slice(lineStart, caret);
  const match = /^(\s*)([-*+]|\d+[.)])\s+(\[[ xX]\]\s+)?(.*)$/.exec(line);
  if (!match) return null;
  const [, indent, bullet, task, rest] = match;
  if (!rest?.trim()) {
    const next = text.slice(0, lineStart) + text.slice(caret);
    return { text: next, caret: lineStart };
  }
  const number = /^\d+/.exec(bullet!);
  const nextBullet = number ? `${Number(number[0]) + 1}${bullet!.slice(number[0].length)}` : bullet;
  const insert = `\n${indent}${nextBullet} ${task ? "[ ] " : ""}`;
  return { text: text.slice(0, caret) + insert + text.slice(caret), caret: caret + insert.length };
}

export function wrap(text: string, start: number, end: number, mark: string) {
  const selected = text.slice(start, end);
  const next = text.slice(0, start) + mark + selected + mark + text.slice(end);
  return { text: next, start: start + mark.length, end: end + mark.length };
}

export function prefixLine(text: string, caret: number, prefix: string) {
  const lineStart = text.lastIndexOf("\n", caret - 1) + 1;
  if (text.startsWith(prefix, lineStart)) {
    return { text: text.slice(0, lineStart) + text.slice(lineStart + prefix.length), caret: caret - prefix.length };
  }
  return { text: text.slice(0, lineStart) + prefix + text.slice(lineStart), caret: caret + prefix.length };
}

export function NoteEditor({
  note,
  place,
  autoFocus = false,
  startIn = "write",
  resolve,
  onSaved,
  onError,
}: {
  note: Note | null;
  place: NotePlace;
  autoFocus?: boolean;
  startIn?: "write" | "read";
  resolve?: (target: string) => string | null;
  onSaved?: (note: Note) => void;
  onError: (error: unknown) => void;
}) {
  const [title, setTitle] = useState(note?.title ?? "");
  const [body, setBody] = useState(note?.body ?? "");
  const [mode, setMode] = useState<"write" | "read">(note && note.body ? startIn : "write");
  const [sync, setSync] = useState<SyncState>("saved");
  const [focus, setFocus] = useState(false);
  const [uploading, setUploading] = useState(0);
  const [updatedAt, setUpdatedAt] = useState(note?.updated_at ?? null);
  const view = useRef<EditorView | null>(null);
  const titleField = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const field = titleField.current;
    if (!field) return;
    field.style.setProperty("height", "auto");
    field.style.setProperty("height", `${field.scrollHeight}px`);
  }, [title, mode]);
  const id = useRef<string | null>(note?.id ?? null);
  const latest = useRef({ title, body });
  const chain = useRef<Promise<unknown>>(Promise.resolve());
  const timer = useRef<number | null>(null);
  const dirty = useRef(false);

  latest.current = { title, body };

  const flush = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    if (!dirty.current) return chain.current;
    dirty.current = false;
    setSync("sending");
    chain.current = chain.current
      .then(async () => {
        const { title: t, body: b } = latest.current;
        if (!id.current && !t.trim() && !b.trim()) return;
        const saved = id.current
          ? await api.updateNote(id.current, { title: t, body: b })
          : await api.addNote({ ...place, title: t, body: b });
        id.current = saved.id;
        setUpdatedAt(saved.updated_at);
        for (const prefix of ["notes", "subject:", "course:"]) invalidate(prefix);
        onSaved?.(saved);
        if (!dirty.current) setSync("saved");
      })
      .catch((error) => {
        dirty.current = true;
        setSync("pending");
        onError(error);
      });
    return chain.current;
  }, [onError, onSaved, place]);

  const touch = useCallback(() => {
    dirty.current = true;
    setSync("pending");
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void flush(), SAVE_AFTER_MS);
  }, [flush]);

  useEffect(() => {
    const hide = () => document.visibilityState === "hidden" && void flush();
    document.addEventListener("visibilitychange", hide);
    return () => {
      document.removeEventListener("visibilitychange", hide);
      void flush();
    };
  }, [flush]);

  useEffect(() => {
    if (!focus) return;
    const escape = (event: globalThis.KeyboardEvent) => event.key === "Escape" && setFocus(false);
    window.addEventListener("keydown", escape);
    document.documentElement.dataset.studyFocus = "true";
    return () => {
      window.removeEventListener("keydown", escape);
      delete document.documentElement.dataset.studyFocus;
    };
  }, [focus]);

  const upload = async (file: File): Promise<string> => {
    setUploading((n) => n + 1);
    try {
      const saved = await api.uploadFile(file, file.name || "imagen.png", {});
      const name = file.name && !/^image\.\w+$/.test(file.name) ? file.name.replace(/\.[^.]+$/, "") : "imagen";
      return `![${name}](${saved.url})`;
    } finally {
      setUploading((n) => n - 1);
    }
  };

  const uploadImages = async (files: File[]) => {
    for (const file of files.filter((one) => one.type.startsWith("image/"))) {
      try {
        const written = await upload(file);
        if (view.current) insertBlock(view.current, written);
      } catch (error) {
        onError(error);
      }
    }
  };

  const tool = (action: "heading" | "bold" | "list" | "task" | "code") => {
    const editor = view.current;
    if (!editor) return;
    if (action === "bold") wrapSelection(editor, "**");
    else if (action === "code") wrapSelection(editor, "`");
    else toggleLinePrefix(editor, { heading: "## ", list: "- ", task: "- [ ] " }[action]);
  };

  const navigate = useNavigate();
  const html = useMemo(
    () => (mode === "read" ? render(body, { tasks: true, title, resolve, noteHref: (to) => pathOf({ tab: "note", id: to }) }) : ""),
    [body, mode, title, resolve],
  );
  const toggle = (event: MouseEvent) => {
    const link = (event.target as HTMLElement).closest<HTMLAnchorElement>("a.mn-link");
    if (link && !link.getAttribute("href")?.startsWith("#")) {
      event.preventDefault();
      const to = /\/apuntes\/([^/?#]+)$/.exec(link.pathname)?.[1];
      if (to && !link.hasAttribute("data-missing")) {
        void flush();
        navigate({ tab: "note", id: to });
      }
      return;
    }
    const box = (event.target as HTMLElement).closest<HTMLInputElement>("input[data-task]");
    if (!box) return;
    setBody(toggleTask(body, Number(box.dataset.task)));
    touch();
  };

  const picker = useRef<HTMLInputElement>(null);

  return (
    <section className="study-editor" data-focus={focus || undefined} aria-label="Apuntes">
      <div className="study-editor-bar">
        <span className="study-editor-state">
          {uploading > 0 && <span className="study-muted">Subiendo imagen…</span>}
          <SyncMark state={sync} />
        </span>
        {mode === "read" ? (
          <Button size="small" icon="edit" onClick={() => setMode("write")}>
            Editar
          </Button>
        ) : (
          body.trim() && (
            <Button
              size="small"
              icon="done"
              onClick={() => {
                void flush();
                setMode("read");
              }}
            >
              Leer
            </Button>
          )
        )}
        <IconButton
          icon={focus ? "close" : "expand"}
          label={focus ? "Salir de pantalla completa" : "Pantalla completa"}
          variant="plain"
          size="small"
          onClick={() => setFocus(!focus)}
        />
      </div>

      <textarea
        ref={titleField}
        className="study-editor-title"
        value={title}
        rows={1}
        placeholder="Título"
        aria-label="Título de los apuntes"
        maxLength={200}
        onChange={(event) => {
          setTitle(event.target.value.replace(/\n/g, " "));
          touch();
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            event.currentTarget.blur();
          }
        }}
        onBlur={() => void flush()}
      />

      {mode === "read" && body.trim() && <Meta body={body} updatedAt={updatedAt} />}

      {mode === "write" ? (
        <>
          <div className="study-editor-tools" role="toolbar" aria-label="Formato">
            <button type="button" className="study-tool" onClick={() => tool("heading")} aria-label="Título de sección">
              <span className="study-tool-heading">T</span>
            </button>
            <button type="button" className="study-tool" onClick={() => tool("bold")} aria-label="Negrita">
              <span className="study-tool-bold">N</span>
            </button>
            <button type="button" className="study-tool" onClick={() => tool("list")} aria-label="Lista">
              <span aria-hidden="true">•</span>
            </button>
            <button type="button" className="study-tool" onClick={() => tool("task")} aria-label="Casilla">
              <span aria-hidden="true">☐</span>
            </button>
            <button type="button" className="study-tool" onClick={() => tool("code")} aria-label="Código">
              <span className="study-tool-code">{"</>"}</span>
            </button>
            <button type="button" className="study-tool" onClick={() => picker.current?.click()} aria-label="Imagen">
              <span aria-hidden="true">▣</span>
            </button>
            <input
              ref={picker}
              type="file"
              accept="image/*"
              multiple
              hidden
              onChange={(event) => {
                void uploadImages(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />
          </div>
          <div className="study-editor-body" onBlur={() => void flush()}>
            <Editor
              id={note?.id ?? "nuevo"}
              value={body}
              onChange={(next) => {
                setBody(next);
                touch();
              }}
              suggestions={NO_SUGGESTIONS}
              onOpenLink={() => undefined}
              onTag={() => undefined}
              onImage={upload}
              placeholder="Escribe aquí. Pega una foto de la pizarra y se queda en los apuntes."
              autoFocus={autoFocus}
              onReady={(editor) => {
                view.current = editor;
              }}
            />
          </div>
        </>
      ) : (
        <Reader html={html} empty={!body.trim()} onToggle={toggle} onEdit={() => setMode("write")} />
      )}
    </section>
  );
}

function Meta({ body, updatedAt }: { body: string; updatedAt: string | null }) {
  const { words, minutes } = reading(body);
  return (
    <p className="study-editor-meta">
      {plural(words, "palabra", "palabras")} · {minutes} min de lectura
      {updatedAt && ` · editado ${dateShort(updatedAt.slice(0, 10))}`}
    </p>
  );
}

interface Heading {
  text: string;
  level: number;
}

const HEADINGS = "h1, h2, h3";

function Reader({ html, empty, onToggle, onEdit }: { html: string; empty: boolean; onToggle: (event: MouseEvent) => void; onEdit: () => void }) {
  const prose = useRef<HTMLDivElement>(null);
  const [headings, setHeadings] = useState<Heading[]>([]);
  const [current, setCurrent] = useState(0);
  const elements = () => Array.from(prose.current?.querySelectorAll<HTMLElement>(HEADINGS) ?? []);

  useLayoutEffect(() => {
    setHeadings(elements().map((el) => ({ text: el.textContent ?? "", level: Number(el.tagName[1]) })));
  }, [html]);

  useEffect(() => {
    if (headings.length < 3) return;
    const update = () => {
      let last = 0;
      elements().forEach((el, index) => {
        if (el.getBoundingClientRect().top < 120) last = index;
      });
      setCurrent(last);
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, [headings]);

  if (empty) {
    return (
      <div className="study-editor-read" onDoubleClick={onEdit}>
        <p className="study-muted">Sin apuntes todavía.</p>
      </div>
    );
  }

  const top = Math.min(...headings.map((h) => h.level));
  const go = (index: number) => elements()[index]?.scrollIntoView({ behavior: "smooth", block: "start" });
  const list = (
    <ul className="study-toc-list">
      {headings.map((heading, index) => (
        <li key={index} data-level={heading.level - top} data-current={index === current || undefined}>
          <button type="button" onClick={() => go(index)}>
            {heading.text}
          </button>
        </li>
      ))}
    </ul>
  );
  const toc = headings.length >= 3;

  return (
    <div className="study-editor-read" data-toc={toc || undefined}>
      {toc && (
        <div className="study-toc-inline">
          <Collapsible title="Índice" subtitle={plural(headings.length, "sección", "secciones")}>
            {list}
          </Collapsible>
        </div>
      )}
      <div ref={prose} className="mn-prose study-prose" onClick={onToggle} onDoubleClick={onEdit} dangerouslySetInnerHTML={{ __html: html }} />
      {toc && (
        <nav className="study-toc study-toc-side" aria-label="Índice">
          <p className="study-toc-heading">En estos apuntes</p>
          {list}
        </nav>
      )}
    </div>
  );
}
