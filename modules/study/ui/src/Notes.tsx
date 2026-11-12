import { Button, ConfirmDelete, CreateButton, EmptyState, GroupLabel, Hint, List, ListRow, OfflineNotice, Screen, SearchField, SelectField, Sheet } from "@openarga/ui";
import { useEffect, useMemo, useState } from "react";

import { type Course, type Hit, type NoteBrief, type Subject, api } from "./api";
import { useNavigate } from "./App";
import { Pending, Problem, Section, changed, useLoad } from "./Bits";
import { ScreenHeader } from "./Header";
import { NoteEditor } from "./LazyEditor";
import { byName, codeColumn, neighbours, resolver, splitCode } from "./order";
import { dateShort, isoDate, plural } from "./words";

export function NoteList({ notes, showCourse = true }: { notes: (NoteBrief | Hit)[]; showCourse?: boolean }) {
  const navigate = useNavigate();
  const titles = notes.map((note) => note.title);
  const codes = codeColumn(titles);
  return (
    <List>
      {notes.map((note, index) => {
        const when = note.session_start ? dateShort(isoDate(new Date(note.session_start))) : dateShort(note.updated_at.slice(0, 10));
        const fragment = "fragment" in note ? note.fragment : null;
        const code = codes[index];
        const name = code ? `${code} ${splitCode(note.title)!.name}` : note.title;
        const where = [showCourse ? (note.subject ?? note.course) : null, note.session_start ? `clase del ${when}` : null]
          .filter(Boolean)
          .join(" · ");
        return (
          <ListRow
            key={note.id}
            title={name || (note.session_start ? `Clase del ${when}` : "Sin título")}
            subtitle={fragment ?? ([where, note.excerpt].filter(Boolean).join(" · ") || undefined)}
            detail={fragment ? where || undefined : undefined}
            onClick={() => navigate(note.session_id ? { tab: "session", id: note.session_id } : { tab: "note", id: note.id })}
          />
        );
      })}
    </List>
  );
}

export function NoteGroups({ notes, showCourse = false }: { notes: NoteBrief[]; showCourse?: boolean }) {
  const groups = useMemo(() => {
    const byFolder = new Map<string, NoteBrief[]>();
    for (const note of notes) byFolder.set(note.folder ?? "", [...(byFolder.get(note.folder ?? "") ?? []), note]);
    return [...byFolder.entries()]
      .map(([folder, list]) => [folder, [...list].sort((a, b) => byName(a.title, b.title))] as const)
      .sort(([a], [b]) => (a === "" ? -1 : b === "" ? 1 : byName(a, b)));
  }, [notes]);
  const single = groups.length === 1;
  return (
    <>
      {groups.map(([folder, list]) => (
        <div key={folder || "/"} className="study-note-folder">
          {folder && <GroupLabel count={single ? undefined : list.length}>{folder}</GroupLabel>}
          <NoteList notes={list} showCourse={showCourse} />
        </div>
      ))}
    </>
  );
}

export function NotesScreen() {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [creating, setCreating] = useState(false);
  const { data, found, problem, fail } = useLoad("notes", async () => {
    const [notes, courses] = await Promise.all([api.notes(), api.courses("all")]);
    return { notes, courses };
  });

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) {
      setHits(null);
      return;
    }
    const timer = window.setTimeout(() => {
      void api.search(text).then(setHits).catch(fail);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, fail]);

  const groups = useMemo(() => {
    const byCourse = new Map<string, { name: string; notes: NoteBrief[] }>();
    for (const note of data?.notes ?? []) {
      const group = byCourse.get(note.course_id) ?? { name: note.course, notes: [] };
      group.notes.push(note);
      byCourse.set(note.course_id, group);
    }
    return [...byCourse.entries()];
  }, [data]);

  return (
    <Screen>
      <ScreenHeader title="Apuntes" />
      <OfflineNotice />
      <SearchField
        label="Buscar en todos tus apuntes"
        value={query}
        onChange={setQuery}
        placeholder="derivadas, «regresión lineal», -examen"
      />
      {data && data.courses.length > 0 && <CreateButton label="Apuntes" onClick={() => setCreating(true)} />}
      <Problem text={problem} />
      {data === null && <Pending found={found} />}

      {hits !== null && (
        <Section title={hits.length ? `${plural(hits.length, "resultado", "resultados")}` : "Nada encontrado"}>
          {hits.length > 0 ? (
            <NoteList notes={hits} />
          ) : (
            <Hint>Prueba con otra palabra: se busca en castellano, con plurales y formas del verbo.</Hint>
          )}
        </Section>
      )}

      {hits === null && data && data.notes.length === 0 && (
        <EmptyState
          icon="edit"
          title="Sin apuntes todavía"
          action={data.courses.length > 0 ? { label: "Nuevos apuntes", icon: "plus", onClick: () => setCreating(true) } : undefined}
        >
          <p>Los de cada clase se escriben en la propia clase. Los sueltos de una asignatura, aquí.</p>
        </EmptyState>
      )}

      {hits === null &&
        groups.map(([courseId, group]) => (
          <Section key={courseId} title={group.name} count={group.notes.length}>
            <NoteGroups notes={group.notes} />
          </Section>
        ))}

      {creating && data && <NewNoteSheet courses={data.courses} onClose={() => setCreating(false)} onError={fail} />}
    </Screen>
  );
}

function NewNoteSheet({ courses, onClose, onError }: { courses: Course[]; onClose: () => void; onError: (e: unknown) => void }) {
  const navigate = useNavigate();
  const open = courses.filter((c) => c.status === "active" || c.status === "planned");
  const list = open.length ? open : courses;
  const [course, setCourse] = useState(list[0]?.id ?? "");
  const [subject, setSubject] = useState("__none__");
  const [subjects, setSubjects] = useState<Subject[]>([]);

  useEffect(() => {
    if (!course) return;
    void api
      .course(course)
      .then((detail) => setSubjects(detail.subjects))
      .catch(onError);
    setSubject("__none__");
  }, [course, onError]);

  const create = async () => {
    try {
      const note = await api.addNote({ course_id: course, subject_id: subject === "__none__" ? null : subject, title: "" });
      changed();
      navigate({ tab: "note", id: note.id });
    } catch (error) {
      onError(error);
    }
  };

  return (
    <Sheet title="Nuevos apuntes" onClose={onClose} action={{ label: "Empezar a escribir", onClick: () => void create(), disabled: !course }}>
      <div className="study-form">
        <SelectField label="Estudio" options={list.map((c) => ({ value: c.id, label: c.name }))} value={course} onChange={setCourse} />
        {subjects.length > 0 && (
          <SelectField
            label="Asignatura"
            options={[{ value: "__none__", label: "Del estudio entero" }, ...subjects.map((s) => ({ value: s.id, label: s.name }))]}
            value={subject}
            onChange={setSubject}
          />
        )}
      </div>
    </Sheet>
  );
}

export function NoteScreen({ id }: { id: string }) {
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(false);
  const { data, found, problem, fail } = useLoad(`note:${id}`, async () => {
    const note = await api.note(id);
    const siblings = await api.notes({ courseId: note.course_id }).catch(() => []);
    return { note, siblings };
  }, { fresh: true });

  if (!data) {
    return (
      <Screen>
        <ScreenHeader back={{ label: "Apuntes", onClick: () => navigate({ tab: "notes" }) }} />
        <OfflineNotice />
        <Problem text={problem} />
        <Pending found={found} />
      </Screen>
    );
  }

  const { note } = data;
  const back = note.subject_id
    ? { label: note.subject ?? "Asignatura", onClick: () => navigate({ tab: "subject", id: note.subject_id! }) }
    : { label: note.course, onClick: () => navigate({ tab: "course", id: note.course_id, section: "notes" }) };
  const { previous, next } = neighbours(data.siblings, note);
  const resolve = resolver(data.siblings);

  return (
    <Screen>
      <ScreenHeader back={back} eyebrow={note.folder || (note.subject ? undefined : note.course)} />
      <OfflineNotice />
      <Problem text={problem} />
      <NoteEditor
        key={note.id}
        note={note}
        place={{ course_id: note.course_id, subject_id: note.subject_id }}
        autoFocus={!note.body}
        startIn={note.body ? "read" : "write"}
        resolve={resolve}
        onError={fail}
      />
      {(previous || next) && (
        <List>
          {previous && <PagerLink note={previous} label="Anterior" />}
          {next && <PagerLink note={next} label="Siguiente" />}
        </List>
      )}
      <footer className="study-footer-actions">
        {note.session_id && (
          <Button variant="secondary" onClick={() => navigate({ tab: "session", id: note.session_id! })}>
            Ir a la clase
          </Button>
        )}
        <Button variant="plain" onClick={() => setDeleting(true)}>
          Borrar apuntes
        </Button>
      </footer>
      {deleting && (
        <ConfirmDelete
          title="¿Borrar estos apuntes?"
          subject={note.title || "Sin título"}
          consequence="Se borran también las imágenes que tengan pegadas."
          action="Borrar apuntes"
          onCancel={() => setDeleting(false)}
          onConfirm={async () => {
            await api.deleteNote(note.id);
            changed();
            back.onClick();
          }}
        />
      )}
    </Screen>
  );
}

function PagerLink({ note, label }: { note: NoteBrief; label: string }) {
  const navigate = useNavigate();
  const code = splitCode(note.title);
  return (
    <ListRow
      title={code ? code.name : note.title || "Sin título"}
      subtitle={code ? `${label} · ${code.number}` : label}
      icon={label === "Anterior" ? "chevron-left" : "chevron-right"}
      onClick={() => navigate({ tab: "note", id: note.id })}
    />
  );
}
