import { Notice, useToast } from "@openarga/ui";
import * as React from "react";

import { Changed, type Note, moveNote, readNote, uploadFile, writeNote, writeProperties } from "./api";
import { Editor, type Suggestions, split } from "@openarga/ui/notes";
import { owners } from "./NoteView";
import { Properties } from "./Properties";

const SAVE_AFTER = 700;

type Saving = "saved" | "pending" | "saving" | "conflict" | "failed";

interface Props {
  note: Note;
  suggestions: () => Suggestions;
  onSaved: (note: Note) => void;
  onRenamed: (note: Note, relinked: number) => void;
  onOpenLink: (target: string, heading: string | null) => void;
  onTag: (tag: string) => void;
  focusTitle?: boolean;
}

function bodyOf(content: string) {
  const parts = split(content);
  return { head: content.slice(0, content.length - parts.body.length), body: parts.body };
}

export function pastedName(file: File, now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const extension = (file.type.split("/")[1] ?? "png").replace("jpeg", "jpg").replace("svg+xml", "svg");
  return `Pasted image ${stamp}.${extension}`;
}

export function NoteEditor({ note, suggestions, onSaved, onRenamed, onOpenLink, onTag, focusTitle = false }: Props) {
  const toast = useToast();
  const [title, setTitle] = React.useState(note.title);
  const [body, setBody] = React.useState(() => bodyOf(note.content).body);
  const [saving, setSaving] = React.useState<Saving>("saved");
  const current = React.useRef(note);
  const pending = React.useRef<string | null>(null);
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const titleInput = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    current.current = note;
    setTitle(note.title);
  }, [note]);

  React.useEffect(() => {
    if (!focusTitle) return;
    titleInput.current?.focus();
    titleInput.current?.select();
  }, [focusTitle]);

  const save = React.useCallback(
    async (force = false) => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      const text = pending.current;
      if (text === null) return;
      pending.current = null;
      const base = current.current;
      setSaving("saving");
      try {
        let saved: Note;
        try {
          saved = await writeNote(base.id, bodyOf(base.content).head + text, force ? undefined : base.version);
        } catch (error) {
          if (!(error instanceof Changed)) throw error;
          const theirs = await readNote(base.id);
          const onlyAnApp = theirs.updated_by === "import" && theirs.updated_app && theirs.version === base.version + 1;
          if (!onlyAnApp) throw error;
          saved = await writeNote(base.id, bodyOf(theirs.content).head + text, theirs.version);
        }
        current.current = saved;
        onSaved(saved);
        setSaving(pending.current === null ? "saved" : "pending");
      } catch (error) {
        pending.current = text;
        setSaving(error instanceof Changed ? "conflict" : "failed");
      }
    },
    [onSaved],
  );

  React.useEffect(
    () => () => {
      if (pending.current !== null) void save();
    },
    [save],
  );

  const change = (text: string) => {
    setBody(text);
    pending.current = text;
    setSaving("pending");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => void save(), SAVE_AFTER);
  };

  const rename = async () => {
    const next = title.trim();
    if (!next || next === current.current.title) {
      setTitle(current.current.title);
      return;
    }
    try {
      const { note: moved, relinked } = await moveNote(current.current.id, { title: next });
      current.current = moved;
      onRenamed(moved, relinked);
    } catch (error) {
      toast({ message: (error as Error).message, tone: "error" });
      setTitle(current.current.title);
    }
  };

  const properties = async (set: Record<string, unknown>, remove: string[] = []) => {
    await save();
    try {
      const saved = await writeProperties(current.current.id, set, remove);
      current.current = saved;
      onSaved(saved);
    } catch (error) {
      toast({ message: (error as Error).message, tone: "error" });
    }
  };

  const keepTheirs = async () => {
    pending.current = null;
    const theirs = await readNote(current.current.id);
    current.current = theirs;
    setBody(bodyOf(theirs.content).body);
    onSaved(theirs);
    setSaving("saved");
  };

  const status: Record<Saving, string> = {
    saved: "Guardado",
    pending: "Sin guardar",
    saving: "Guardando…",
    conflict: "Sin guardar",
    failed: "No se ha podido guardar",
  };

  return (
    <article className="mn-note-view mn-note-editing">
      <header className="mn-note-head">
        {note.folder && <p className="mn-crumbs">{note.folder}</p>}
        <input
          ref={titleInput}
          className="mn-note-title mn-title-input"
          value={title}
          aria-label="Título"
          onChange={(event) => setTitle(event.target.value)}
          onBlur={() => void rename()}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              (event.target as HTMLInputElement).blur();
            }
            if (event.key === "Escape") {
              setTitle(current.current.title);
              (event.target as HTMLInputElement).blur();
            }
          }}
        />
        <p className="mn-note-meta" data-state={saving} aria-live="polite">
          {status[saving]}
        </p>
      </header>

      {saving === "conflict" && (
        <Notice tone="warning" title="La nota cambió mientras escribías" action={{ label: "Guardar la mía", onClick: () => void save(true) }}>
          Probablemente la cambió Claude. Si guardas la tuya, lo suyo queda en el historial.{" "}
          <button type="button" className="mn-inline-action" onClick={() => void keepTheirs()}>
            Quedarme con la suya
          </button>
        </Notice>
      )}
      {saving === "failed" && (
        <Notice tone="negative" title="No se ha podido guardar" action={{ label: "Reintentar", onClick: () => void save() }}>
          Lo escrito sigue aquí.
        </Notice>
      )}

      {note.arga && (
        <p className="mn-arga-hint">
          Lo enmarcado y las propiedades de {owners(note)} se escriben allí y aquí se rehacen solos. Lo que escribas fuera es
          tuyo.
        </p>
      )}

      <Properties
        values={note.properties}
        onSet={(name, value) => void properties({ [name]: value })}
        onRemove={(name) => void properties({}, [name])}
        locked={note.arga?.properties ?? []}
        lockedBy={owners(note)}
      />

      <Editor
        id={note.id}
        value={body}
        onChange={change}
        suggestions={suggestions}
        onOpenLink={(target, heading) => {
          void save();
          onOpenLink(target, heading);
        }}
        onTag={onTag}
        onImage={async (file) => {
          const name = file.name && !/^image\.\w+$/.test(file.name) ? file.name : pastedName(file);
          const saved = await uploadFile(name, file);
          return `![[${saved.name}]]`;
        }}
        autoFocus={!focusTitle}
      />
    </article>
  );
}
