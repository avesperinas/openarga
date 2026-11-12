import "@openarga/ui/notes.css";

import { Button, CANNOT_UNDO, ChoiceChips, ConfirmDelete, GroupLabel, Hint, Sheet, TextField } from "@openarga/ui";
import { Editor, render } from "@openarga/ui/notes";
import { useEffect, useMemo, useState } from "react";

import {
  type NoteCategory,
  type NoteIn,
  type TripNote,
  Unauthorised,
  addNote,
  readNotes,
  removeNote,
  signIn,
  updateNote,
} from "./api";
import { Queued } from "./offline";

export const NOTE_CATEGORIES: Record<NoteCategory, string> = {
  general: "General",
  visa: "Visado y papeles",
  culture: "Costumbres",
  tips: "Consejos",
  health: "Salud",
  other: "Otras",
};

export function NotesSection({ tripId }: { tripId: string }) {
  const [found, setFound] = useState<TripNote[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [editing, setEditing] = useState<TripNote | "new" | null>(null);
  const [removing, setRemoving] = useState<TripNote | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    readNotes(tripId)
      .then(setFound)
      .catch((error: unknown) => {
        if (error instanceof Unauthorised) return signIn();
        setFound([]);
      });
  }, [tripId]);

  const apply = async (change: Promise<TripNote[]>) => {
    try {
      setFound(await change);
      setProblem("");
      return true;
    } catch (error) {
      if (error instanceof Queued) {
        setProblem(error.message);
        return true;
      }
      setProblem(error instanceof Error ? error.message : "No se ha podido guardar.");
      return false;
    }
  };

  if (found === null) return null;
  return (
    <section className="travel-group">
      <GroupLabel>Notas</GroupLabel>
      {problem && <Hint tone="warning">{problem}</Hint>}
      <ol className="surface travel-day">
        {found.map((note) => (
          <li key={note.id} className="travel-note-item">
            <button
              type="button"
              className="travel-block-body"
              aria-expanded={open === note.id}
              onClick={() => setOpen(open === note.id ? null : note.id)}
            >
              <span className="travel-step-text">
                <span className="travel-step-title">{note.title}</span>
                <span className="travel-step-detail">{NOTE_CATEGORIES[note.category]}</span>
              </span>
            </button>
            {open === note.id && (
              <div className="travel-note-open">
                <NoteBody body={note.body} />
                <div className="travel-actions">
                  <Button variant="secondary" size="small" icon="edit" onClick={() => setEditing(note)}>
                    Editar
                  </Button>
                  <Button variant="plain" size="small" icon="trash" onClick={() => setRemoving(note)}>
                    Quitar
                  </Button>
                </div>
              </div>
            )}
          </li>
        ))}
        {found.length === 0 && <li className="travel-day-empty">Visado, costumbres, consejos, salud…</li>}
        <li className="travel-day-add">
          <Button variant="plain" size="small" icon="plus" onClick={() => setEditing("new")}>
            Nota
          </Button>
        </li>
      </ol>
      {editing && (
        <NoteSheet
          note={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSave={async (data) => {
            const saved =
              editing === "new" ? await apply(addNote(tripId, data)) : await apply(updateNote(tripId, editing.id, data));
            if (saved) setEditing(null);
          }}
        />
      )}
      {removing && (
        <ConfirmDelete
          title="¿Quitar la nota?"
          subject={removing.title}
          consequence={CANNOT_UNDO}
          action="Quitar nota"
          onCancel={() => setRemoving(null)}
          onConfirm={async () => {
            await apply(removeNote(tripId, removing.id));
            setRemoving(null);
          }}
        />
      )}
    </section>
  );
}

function NoteBody({ body }: { body: string }) {
  const html = useMemo(() => render(body), [body]);
  if (!body.trim()) return <p className="travel-step-detail">Sin texto.</p>;
  return <div className="mn-prose travel-note-prose" dangerouslySetInnerHTML={{ __html: html }} />;
}

const NO_SUGGESTIONS = () => ({ notes: [], tags: [] });
const ignore = () => {};
const noImages = async () => "";

const CATEGORY_OPTIONS = (Object.keys(NOTE_CATEGORIES) as NoteCategory[]).map((value) => ({
  value,
  label: NOTE_CATEGORIES[value],
}));

function NoteSheet({
  note,
  onClose,
  onSave,
}: {
  note: TripNote | null;
  onClose: () => void;
  onSave: (data: NoteIn) => Promise<void>;
}) {
  const [title, setTitle] = useState(note?.title ?? "");
  const [category, setCategory] = useState<NoteCategory>(note?.category ?? "general");
  const [body, setBody] = useState(note?.body ?? "");
  const [busy, setBusy] = useState(false);
  return (
    <Sheet
      title={note ? "Editar nota" : "Nueva nota"}
      onClose={onClose}
      action={{
        label: note ? "Guardar" : "Añadir nota",
        disabled: !title.trim() || busy,
        onClick: () => {
          setBusy(true);
          void onSave({ title: title.trim(), category, body }).finally(() => setBusy(false));
        },
      }}
    >
      <div className="travel-sheet-stack">
        <TextField label="Título" value={title} onChange={setTitle} placeholder="Visado, propinas, vacunas…" autoFocus />
        <ChoiceChips label="Categoría" value={category} onChange={setCategory} options={CATEGORY_OPTIONS} />
        <div className="surface travel-note-editor">
          <Editor
            id={note?.id ?? "nueva"}
            value={body}
            onChange={setBody}
            suggestions={NO_SUGGESTIONS}
            onOpenLink={ignore}
            onTag={ignore}
            onImage={noImages}
            placeholder="Escribe. Markdown: **negrita**, - listas, [enlaces](https://…)."
          />
        </div>
      </div>
    </Sheet>
  );
}
