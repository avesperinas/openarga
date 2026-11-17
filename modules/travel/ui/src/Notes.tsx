import "@openarga/ui/notes.css";

import { Button, ChoiceChips, ConfirmDelete, GroupLabel, Hint, Sheet, TextField, cannotUndo } from "@openarga/ui";
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
import { t } from "./lang";

export const NOTE_CATEGORIES = {} as Record<NoteCategory, string>;
for (const key of ["general", "visa", "culture", "tips", "health", "other"] as const) {
  Object.defineProperty(NOTE_CATEGORIES, key, { enumerable: true, get: () => t(`note.category.${key}`) });
}

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
      setProblem(error instanceof Error ? error.message : t("error.save"));
      return false;
    }
  };

  if (found === null) return null;
  return (
    <section className="travel-group">
      <GroupLabel>{t("editor.notes")}</GroupLabel>
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
                    {t("action.edit")}
                  </Button>
                  <Button variant="plain" size="small" icon="trash" onClick={() => setRemoving(note)}>
                    {t("action.remove")}
                  </Button>
                </div>
              </div>
            )}
          </li>
        ))}
        {found.length === 0 && <li className="travel-day-empty">{t("note.empty")}</li>}
        <li className="travel-day-add">
          <Button variant="plain" size="small" icon="plus" onClick={() => setEditing("new")}>
            {t("editor.note")}
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
          title={t("note.remove_confirm")}
          subject={removing.title}
          consequence={cannotUndo()}
          action={t("note.remove")}
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
  if (!body.trim()) return <p className="travel-step-detail">{t("note.no_text")}</p>;
  return <div className="mn-prose travel-note-prose" dangerouslySetInnerHTML={{ __html: html }} />;
}

const NO_SUGGESTIONS = () => ({ notes: [], tags: [] });
const ignore = () => {};
const noImages = async () => "";

const categoryOptions = () =>
  (Object.keys(NOTE_CATEGORIES) as NoteCategory[]).map((value) => ({ value, label: NOTE_CATEGORIES[value] }));

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
      title={note ? t("note.edit") : t("note.new")}
      onClose={onClose}
      action={{
        label: note ? t("action.save") : t("note.add"),
        disabled: !title.trim() || busy,
        onClick: () => {
          setBusy(true);
          void onSave({ title: title.trim(), category, body }).finally(() => setBusy(false));
        },
      }}
    >
      <div className="travel-sheet-stack">
        <TextField label={t("editor.title")} value={title} onChange={setTitle} placeholder={t("note.title_example")} autoFocus />
        <ChoiceChips label={t("expense.category")} value={category} onChange={setCategory} options={categoryOptions()} />
        <div className="surface travel-note-editor">
          <Editor
            id={note?.id ?? "new"}
            value={body}
            onChange={setBody}
            suggestions={NO_SUGGESTIONS}
            onOpenLink={ignore}
            onTag={ignore}
            onImage={noImages}
            placeholder={t("note.body_hint")}
          />
        </div>
      </div>
    </Sheet>
  );
}
