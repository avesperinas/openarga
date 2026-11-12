import {
  Button,
  ChoiceChips,
  Collapsible,
  DateField,
  Hint,
  RecurrencePicker,
  type RecurrenceRule,
  SegmentedControl,
  SelectField,
  Sheet,
  TextField,
} from "@openarga/ui";
import { useState } from "react";

import {
  type Assessment,
  type AssessmentIn,
  type Course,
  type Schedule,
  type Session,
  type Subject,
  api,
} from "./api";
import {
  ASSESSMENT_KINDS,
  atTime,
  grade,
  hhmm,
  isoDate,
  localIso,
  parseNumber,
  ruleFromServer,
  ruleToServer,
  todayIso,
} from "./words";

function useSaving(onError: (error: unknown) => void) {
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState("");
  const run = async (action: () => Promise<void>) => {
    setSaving(true);
    setProblem("");
    try {
      await action();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "No se pudo guardar.");
      onError(error);
    } finally {
      setSaving(false);
    }
  };
  return { saving, problem, setProblem, run };
}

function SheetProblem({ text }: { text: string }) {
  return text ? (
    <Hint tone="warning">
      {text}
    </Hint>
  ) : null;
}

const NONE = "__none__";

function subjectOptions(subjects: Pick<Subject, "id" | "name">[], none = "Del estudio entero") {
  return [{ value: NONE, label: none }, ...subjects.map((s) => ({ value: s.id, label: s.name }))];
}

export function SubjectSheet({
  courseId,
  subject,
  onClose,
  onSaved,
  onError,
}: {
  courseId: string;
  subject: Subject | null;
  onClose: () => void;
  onSaved: () => void;
  onError: (error: unknown) => void;
}) {
  const [name, setName] = useState(subject?.name ?? "");
  const [teacher, setTeacher] = useState(subject?.teacher ?? "");
  const [credits, setCredits] = useState(subject?.credits?.toString().replace(".", ",") ?? "");
  const [period, setPeriod] = useState(subject?.period ?? "");
  const { saving, problem, setProblem, run } = useSaving(onError);

  const save = () =>
    run(async () => {
      if (!name.trim()) return setProblem("Ponle un nombre.");
      const body = {
        name: name.trim(),
        teacher: teacher.trim() || null,
        credits: parseNumber(credits),
        period: period.trim() || null,
      };
      if (subject) await api.updateSubject(subject.id, body);
      else await api.addSubject(courseId, body);
      onSaved();
    });

  return (
    <Sheet
      title={subject ? "Editar asignatura" : "Nueva asignatura"}
      onClose={onClose}
      action={{ label: subject ? "Guardar" : "Añadir asignatura", onClick: () => void save(), disabled: saving }}
    >
      <div className="study-form">
        <TextField label="Nombre" value={name} onChange={setName} autoFocus={!subject} onSubmit={() => void save()} />
        <div className="study-pair">
          <TextField label="Créditos" value={credits} onChange={setCredits} inputMode="decimal" placeholder="6" />
          <TextField label="Periodo" value={period} onChange={setPeriod} placeholder="1.er cuatrimestre" />
        </div>
        <TextField label="Profesor o profesora" value={teacher} onChange={setTeacher} />
        <SheetProblem text={problem} />
      </div>
    </Sheet>
  );
}

export function AssessmentSheet({
  course,
  subjects,
  assessment,
  subjectId,
  onClose,
  onSaved,
  onDelete,
  onError,
}: {
  course: Pick<Course, "id" | "scale_max">;
  subjects: Pick<Subject, "id" | "name">[];
  assessment: Assessment | null;
  subjectId?: string | null;
  onClose: () => void;
  onSaved: () => void;
  onDelete?: () => void;
  onError: (error: unknown) => void;
}) {
  const [title, setTitle] = useState(assessment?.title ?? "");
  const [kind, setKind] = useState<AssessmentIn["kind"]>(assessment?.kind ?? "assignment");
  const [subject, setSubject] = useState(assessment?.subject_id ?? subjectId ?? NONE);
  const [dueOn, setDueOn] = useState(assessment?.due_on ?? "");
  const [dueTime, setDueTime] = useState(hhmm(assessment?.due_time ?? null));
  const [weight, setWeight] = useState(assessment?.weight?.toString().replace(".", ",") ?? "");
  const [minimum, setMinimum] = useState(assessment?.min_grade?.toString().replace(".", ",") ?? "");
  const [status, setStatus] = useState<"pending" | "submitted" | "graded">(assessment?.status ?? "pending");
  const [mark, setMark] = useState(assessment?.grade?.toString().replace(".", ",") ?? "");
  const [note, setNote] = useState(assessment?.note ?? "");
  const { saving, problem, setProblem, run } = useSaving(onError);

  const save = () =>
    run(async () => {
      if (!title.trim()) return setProblem("Ponle un título.");
      const given = parseNumber(mark);
      if (status === "graded" && given === null) return setProblem("Calificado es con nota.");
      const body: AssessmentIn = {
        title: title.trim(),
        kind,
        subject_id: subject === NONE ? null : subject,
        due_on: dueOn || null,
        due_time: dueOn && dueTime ? dueTime : null,
        weight: parseNumber(weight),
        min_grade: parseNumber(minimum),
        status: status === "graded" ? "graded" : status,
        grade: status === "graded" ? given : null,
        note: note.trim() || null,
      };
      if (assessment) await api.updateAssessment(assessment.id, body);
      else await api.addAssessment(course.id, body);
      onSaved();
    });

  return (
    <Sheet
      title={assessment ? assessment.title : "Nuevo evaluable"}
      onClose={onClose}
      action={{ label: assessment ? "Guardar" : "Añadir", onClick: () => void save(), disabled: saving }}
    >
      <div className="study-form">
        <TextField label="Título" value={title} onChange={setTitle} autoFocus={!assessment} placeholder="Práctica 1" />
        <ChoiceChips label="Tipo" options={ASSESSMENT_KINDS} value={kind} onChange={setKind} />
        {subjects.length > 0 && (
          <SelectField label="Asignatura" options={subjectOptions(subjects)} value={subject} onChange={setSubject} />
        )}
        <div className="study-pair">
          <DateField label="Fecha" value={dueOn} onChange={setDueOn} />
          <TextField label="Hora" type="time" value={dueTime} onChange={setDueTime} hint="Sin hora, todo el día" />
        </div>
        <div className="study-pair">
          <TextField label="Peso" value={weight} onChange={setWeight} inputMode="decimal" placeholder="%" hint="De la nota de la asignatura" />
          <TextField label="Nota mínima" value={minimum} onChange={setMinimum} inputMode="decimal" placeholder="—" hint="Para hacer media" />
        </div>
        <SegmentedControl
          label="Estado"
          options={[
            { value: "pending", label: "Pendiente" },
            { value: "submitted", label: "Entregado" },
            { value: "graded", label: "Calificado" },
          ]}
          value={status}
          onChange={setStatus}
        />
        {status === "graded" && (
          <TextField
            label={`Nota, de 0 a ${grade(course.scale_max, 100)}`}
            value={mark}
            onChange={setMark}
            inputMode="decimal"
            autoFocus
          />
        )}
        <TextField label="Nota para ti" value={note} onChange={setNote} placeholder="Enunciado, formato, lo que pidió" />
        <SheetProblem text={problem} />
        {assessment && onDelete && (
          <Button variant="destructive" size="small" icon="trash" onClick={onDelete}>
            Borrar evaluable
          </Button>
        )}
      </div>
    </Sheet>
  );
}

export function GradeSheet({
  assessment,
  onClose,
  onSaved,
  onError,
}: {
  assessment: Assessment;
  onClose: () => void;
  onSaved: () => void;
  onError: (error: unknown) => void;
}) {
  const [mark, setMark] = useState(assessment.grade?.toString().replace(".", ",") ?? "");
  const { saving, problem, run } = useSaving(onError);
  const save = () =>
    run(async () => {
      await api.gradeAssessment(assessment.id, parseNumber(mark));
      onSaved();
    });
  return (
    <Sheet title={`Nota de ${assessment.title}`} onClose={onClose} action={{ label: "Guardar nota", onClick: () => void save(), disabled: saving }}>
      <div className="study-form">
        <TextField
          label={`De 0 a ${grade(assessment.scale_max, 100)}`}
          value={mark}
          onChange={setMark}
          inputMode="decimal"
          autoFocus
          onSubmit={() => void save()}
          hint={assessment.min_grade !== null ? `Mínimo para hacer media: ${grade(assessment.min_grade, assessment.scale_max)}` : "Vacía, la quita"}
        />
        <SheetProblem text={problem} />
      </div>
    </Sheet>
  );
}

export function RecordSheet({
  subject,
  scale,
  onClose,
  onSaved,
  onError,
}: {
  subject: Subject;
  scale: number;
  onClose: () => void;
  onSaved: () => void;
  onError: (error: unknown) => void;
}) {
  const [mark, setMark] = useState(subject.final_grade?.toString().replace(".", ",") ?? "");
  const { saving, problem, run } = useSaving(onError);
  const save = () =>
    run(async () => {
      await api.recordGrade(subject.id, parseNumber(mark));
      onSaved();
    });
  return (
    <Sheet title="Nota de acta" onClose={onClose} action={{ label: "Guardar", onClick: () => void save(), disabled: saving }}>
      <div className="study-form">
        <p className="study-muted">
          La oficial, la que sale en el expediente. Manda sobre la que calcula Study con tus evaluables. Vacía, vuelve a mandar
          la calculada.
        </p>
        <TextField label={`De 0 a ${grade(scale, 100)}`} value={mark} onChange={setMark} inputMode="decimal" autoFocus onSubmit={() => void save()} />
        <SheetProblem text={problem} />
      </div>
    </Sheet>
  );
}

export function ScheduleSheet({
  course,
  subjects,
  schedule,
  subjectId,
  onClose,
  onSaved,
  onDelete,
  onError,
}: {
  course: Pick<Course, "id" | "starts_on" | "ends_on">;
  subjects: Pick<Subject, "id" | "name">[];
  schedule: Schedule | null;
  subjectId?: string | null;
  onClose: () => void;
  onSaved: (schedule: Schedule) => void;
  onDelete?: () => void;
  onError: (error: unknown) => void;
}) {
  const firstDay = schedule?.starts_on ?? course.starts_on ?? todayIso();
  const [subject, setSubject] = useState(schedule?.subject_id ?? subjectId ?? subjects[0]?.id ?? NONE);
  const [startsOn, setStartsOn] = useState(firstDay);
  const [start, setStart] = useState(hhmm(schedule?.start_time ?? "18:00"));
  const [end, setEnd] = useState(hhmm(schedule?.end_time ?? "20:00"));
  const [rule, setRule] = useState<RecurrenceRule | null>(
    schedule
      ? ruleFromServer(schedule.rule)
      : { freq: "weekly", interval: 1, byDay: [], byMonthDay: [], byMonth: [], ...(course.ends_on ? { until: course.ends_on } : {}) },
  );
  const [place, setPlace] = useState(schedule?.place ?? "");
  const [url, setUrl] = useState(schedule?.url ?? "");
  const { saving, problem, setProblem, run } = useSaving(onError);

  const save = () =>
    run(async () => {
      if (!rule) return setProblem("Un horario se repite: elige cada cuánto.");
      if (!startsOn) return setProblem("Di desde qué día.");
      const body = {
        subject_id: subject === NONE ? null : subject,
        rule: ruleToServer(rule),
        starts_on: startsOn,
        start_time: start,
        end_time: end,
        place: place.trim() || null,
        url: url.trim() || null,
      };
      const saved = schedule ? await api.updateSchedule(schedule.id, body) : await api.addSchedule(course.id, body);
      onSaved(saved);
    });

  return (
    <Sheet
      title={schedule ? "Cambiar el horario" : "Añadir al horario"}
      onClose={onClose}
      action={{ label: schedule ? "Guardar y mover las clases" : "Añadir y crear las clases", onClick: () => void save(), disabled: saving }}
    >
      <div className="study-form">
        {subjects.length > 0 && (
          <SelectField label="Asignatura" options={subjectOptions(subjects, "Del estudio")} value={subject} onChange={setSubject} />
        )}
        <div className="study-pair">
          <TextField label="De" type="time" value={start} onChange={setStart} />
          <TextField label="A" type="time" value={end} onChange={setEnd} />
        </div>
        <DateField label="Desde" value={startsOn} onChange={setStartsOn} />
        <RecurrencePicker date={startsOn || todayIso()} value={rule} onChange={setRule} label="Se repite" />
        <div className="study-pair">
          <TextField label="Study" value={place} onChange={setPlace} placeholder="Study 2.3" />
          <TextField label="Enlace" value={url} onChange={setUrl} placeholder="Si es en línea" />
        </div>
        {schedule && (
          <p className="study-muted">
            Las clases que ya pasaron y las que tienen apuntes, asistencia o se movieron a mano se quedan como están.
          </p>
        )}
        <SheetProblem text={problem} />
        {schedule && onDelete && (
          <Button variant="destructive" size="small" icon="trash" onClick={onDelete}>
            Quitar del horario
          </Button>
        )}
      </div>
    </Sheet>
  );
}

export function SessionSheet({
  course,
  subjects,
  subjectId,
  day,
  onClose,
  onSaved,
  onError,
}: {
  course: Pick<Course, "id">;
  subjects: Pick<Subject, "id" | "name">[];
  subjectId?: string | null;
  day?: string;
  onClose: () => void;
  onSaved: (id: string) => void;
  onError: (error: unknown) => void;
}) {
  const [kind, setKind] = useState<"class" | "tutorial" | "event">(subjectId ? "class" : "tutorial");
  const [title, setTitle] = useState("");
  const [subject, setSubject] = useState(subjectId ?? NONE);
  const [date, setDate] = useState(day ?? todayIso());
  const [start, setStart] = useState("10:00");
  const [end, setEnd] = useState("11:00");
  const [place, setPlace] = useState("");
  const [url, setUrl] = useState("");
  const { saving, problem, setProblem, run } = useSaving(onError);

  const save = () =>
    run(async () => {
      if (kind !== "class" && !title.trim()) return setProblem("Ponle un título.");
      const detail = await api.addSession(course.id, {
        kind,
        title: title.trim() || null,
        subject_id: subject === NONE ? null : subject,
        starts_at: localIso(atTime(date, start)),
        ends_at: localIso(atTime(date, end)),
        place: place.trim() || null,
        url: url.trim() || null,
      });
      onSaved(detail.session.id);
    });

  return (
    <Sheet title="Nueva sesión" onClose={onClose} action={{ label: "Añadir", onClick: () => void save(), disabled: saving }}>
      <div className="study-form">
        <SegmentedControl
          label="Qué es"
          options={[
            { value: "tutorial", label: "Tutoría" },
            { value: "event", label: "Jornada o evento" },
            { value: "class", label: "Clase extra" },
          ]}
          value={kind}
          onChange={setKind}
        />
        <TextField label="Título" value={title} onChange={setTitle} placeholder={kind === "class" ? "La de la asignatura" : "Defensa del TFM"} />
        {subjects.length > 0 && (
          <SelectField label="Asignatura" options={subjectOptions(subjects)} value={subject} onChange={setSubject} />
        )}
        <DateField label="Día" value={date} onChange={setDate} />
        <div className="study-pair">
          <TextField label="De" type="time" value={start} onChange={setStart} />
          <TextField label="A" type="time" value={end} onChange={setEnd} />
        </div>
        <div className="study-pair">
          <TextField label="Lugar" value={place} onChange={setPlace} />
          <TextField label="Enlace" value={url} onChange={setUrl} />
        </div>
        <SheetProblem text={problem} />
      </div>
    </Sheet>
  );
}

export function MoveSheet({
  session,
  onClose,
  onSaved,
  onDelete,
  onError,
}: {
  session: Session;
  onClose: () => void;
  onSaved: () => void;
  onDelete?: () => void;
  onError: (error: unknown) => void;
}) {
  const startDate = new Date(session.starts_at);
  const [date, setDate] = useState(isoDate(startDate));
  const [start, setStart] = useState(hhmm(startDate.toTimeString()));
  const [end, setEnd] = useState(hhmm(new Date(session.ends_at).toTimeString()));
  const [place, setPlace] = useState(session.place ?? "");
  const [url, setUrl] = useState(session.url ?? "");
  const [title, setTitle] = useState(session.kind === "class" ? "" : session.title);
  const { saving, problem, run } = useSaving(onError);

  const save = (status: "scheduled" | "cancelled") =>
    run(async () => {
      await api.updateSession(session.id, {
        starts_at: localIso(atTime(date, start)),
        ends_at: localIso(atTime(date, end)),
        place: place.trim() || null,
        url: url.trim() || null,
        status,
        title: title.trim() || null,
      });
      onSaved();
    });

  const cancelled = session.status === "cancelled";
  return (
    <Sheet title={session.kind === "class" ? "Mover la clase" : "Cambiar la sesión"} onClose={onClose} action={{ label: "Guardar", onClick: () => void save("scheduled"), disabled: saving }}>
      <div className="study-form">
        {session.kind !== "class" && <TextField label="Título" value={title} onChange={setTitle} />}
        <DateField label="Día" value={date} onChange={setDate} />
        <div className="study-pair">
          <TextField label="De" type="time" value={start} onChange={setStart} />
          <TextField label="A" type="time" value={end} onChange={setEnd} />
        </div>
        <div className="study-pair">
          <TextField label="Lugar" value={place} onChange={setPlace} />
          <TextField label="Enlace" value={url} onChange={setUrl} />
        </div>
        <p className="study-muted">Solo cambia esta. El horario y las demás clases siguen igual.</p>
        <SheetProblem text={problem} />
        <div className="study-row-actions">
          {cancelled ? (
            <Button variant="secondary" size="small" onClick={() => void save("scheduled")}>
              Recuperar la clase
            </Button>
          ) : (
            <Button variant="secondary" size="small" onClick={() => void save("cancelled")}>
              Cancelar esta clase
            </Button>
          )}
          {onDelete && (
            <Button variant="destructive" size="small" icon="trash" onClick={onDelete}>
              Borrar sesión
            </Button>
          )}
        </div>
      </div>
    </Sheet>
  );
}

export function MaterialSheet({
  courseId,
  subjects,
  subjectId,
  onClose,
  onSaved,
  onError,
}: {
  courseId: string;
  subjects: Pick<Subject, "id" | "name">[];
  subjectId?: string | null;
  onClose: () => void;
  onSaved: () => void;
  onError: (error: unknown) => void;
}) {
  const [kind, setKind] = useState<"link" | "file">("link");
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [subject, setSubject] = useState(subjectId ?? NONE);
  const { saving, problem, setProblem, run } = useSaving(onError);

  const save = () =>
    run(async () => {
      const owner = subject === NONE ? null : subject;
      if (kind === "link") {
        if (!url.trim()) return setProblem("Pega el enlace.");
        await api.addLink(courseId, { title: title.trim() || url.trim(), url: url.trim(), subject_id: owner });
      } else {
        if (!file) return setProblem("Elige un fichero.");
        await api.addFile(courseId, file, owner);
      }
      onSaved();
    });

  return (
    <Sheet title="Nuevo material" onClose={onClose} action={{ label: "Añadir", onClick: () => void save(), disabled: saving }}>
      <div className="study-form">
        <SegmentedControl
          label="Qué es"
          options={[
            { value: "link", label: "Enlace" },
            { value: "file", label: "Fichero" },
          ]}
          value={kind}
          onChange={setKind}
        />
        {kind === "link" ? (
          <>
            <TextField label="Enlace" value={url} onChange={setUrl} placeholder="https://" autoFocus />
            <TextField label="Nombre" value={title} onChange={setTitle} placeholder="Guía docente" />
          </>
        ) : (
          <label className="study-file-pick">
            <span className="text-field-label">Fichero</span>
            <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            <span className="study-muted">Hasta 20 MB: un PDF, unas diapositivas, un libro.</span>
          </label>
        )}
        {subjects.length > 0 && (
          <SelectField label="De" options={subjectOptions(subjects)} value={subject} onChange={setSubject} />
        )}
        <SheetProblem text={problem} />
      </div>
    </Sheet>
  );
}

export function CloseSheet({
  course,
  onClose,
  onSaved,
  onError,
}: {
  course: Course;
  onClose: () => void;
  onSaved: () => void;
  onError: (error: unknown) => void;
}) {
  const [status, setStatus] = useState<"finished" | "abandoned">("finished");
  const [closedOn, setClosedOn] = useState(course.ends_on && course.ends_on < todayIso() ? course.ends_on : todayIso());
  const suggested = course.average.average;
  const [mark, setMark] = useState(
    (course.final_grade ?? suggested)?.toString().replace(".", ",") ?? "",
  );
  const [file, setFile] = useState<File | null>(null);
  const { saving, problem, run } = useSaving(onError);

  const save = () =>
    run(async () => {
      await api.closeCourse(course.id, {
        status,
        closed_on: closedOn || null,
        final_grade: status === "finished" ? parseNumber(mark) : null,
      });
      if (file) await api.uploadCertificate(course.id, file);
      onSaved();
    });

  return (
    <Sheet
      title="Terminar el estudio"
      onClose={onClose}
      action={{ label: status === "finished" ? "Terminar y archivar" : "Abandonar y archivar", onClick: () => void save(), disabled: saving }}
    >
      <div className="study-form">
        <SegmentedControl
          label="Cómo acaba"
          options={[
            { value: "finished", label: "Terminado" },
            { value: "abandoned", label: "Abandonado" },
          ]}
          value={status}
          onChange={setStatus}
        />
        <DateField label="Fecha" value={closedOn} onChange={setClosedOn} />
        {status === "finished" && (
          <>
            <TextField
              label="Nota final"
              value={mark}
              onChange={setMark}
              inputMode="decimal"
              hint={suggested !== null ? `La media de tus asignaturas es ${grade(suggested, course.scale_max)}` : "La del título, si la tiene"}
            />
            <Collapsible title="Título o certificado" subtitle="Un PDF o una foto">
              <label className="study-file-pick">
                <input type="file" accept="application/pdf,image/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
              </label>
            </Collapsible>
          </>
        )}
        <p className="study-muted">Pasa al Archivo con su nota. Sus clases y apuntes se quedan, y se puede reabrir.</p>
        <SheetProblem text={problem} />
      </div>
    </Sheet>
  );
}
