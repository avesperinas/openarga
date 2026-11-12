import {
  Badge,
  Button,
  type CalendarEvent,
  ConfirmDelete,
  CreateButton,
  GroupLabel,
  Icon,
  List,
  ListRow,
  OfflineNotice,
  Panes,
  Screen,
  TimeGrid,
  addDays,
  mondayOf,
  useToast,
} from "@openarga/ui";
import { useEffect, useState } from "react";

import { AddSheet } from "./AddSheet";

import { type Assessment, type CourseDetail, type Material, type Schedule, type Session, type Subject, api, fileUrl } from "./api";
import { type CourseTab, useNavigate } from "./App";
import { Empty, Pending, Problem, ProgressBar, Section, changed, dueTone, neededLine, rowTone, useLoad } from "./Bits";
import { CourseSheet } from "./CourseSheet";
import { ScreenHeader } from "./Header";
import { NoteGroups } from "./Notes";
import {
  AssessmentSheet,
  CloseSheet,
  GradeSheet,
  MaterialSheet,
  ScheduleSheet,
  SessionSheet,
  SubjectSheet,
} from "./Sheets";
import {
  ASSESSMENT_KINDS,
  KINDS,
  MODALITIES,
  WEEK,
  countdown,
  dateLong,
  dateShort,
  fileSize,
  grade,
  hhmm,
  labelOf,
  percent,
  period,
  plural,
  todayIso,
  verdictLabel,
  verdictTone,
} from "./words";

interface Loaded {
  detail: CourseDetail;
  schedules: Schedule[];
  sessions: Session[];
  materials: Material[];
}

type Open =
  | { sheet: "edit" }
  | { sheet: "close" }
  | { sheet: "delete" }
  | { sheet: "subject"; subject: Subject | null }
  | { sheet: "assessment"; assessment: Assessment | null }
  | { sheet: "grade"; assessment: Assessment }
  | { sheet: "delete-assessment"; assessment: Assessment }
  | { sheet: "schedule"; schedule: Schedule | null }
  | { sheet: "delete-schedule"; schedule: Schedule }
  | { sheet: "session" }
  | { sheet: "material" }
  | { sheet: "delete-material"; material: Material };

export function CourseScreen({ id, section }: { id: string; section: CourseTab }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState<Open | null>(null);
  const [adding, setAdding] = useState(false);
  const toast = useToast();
  const { data, found, problem, fail, refresh } = useLoad<Loaded>(`course:${id}`, async () => {
    const [detail, schedules, sessions, materials] = await Promise.all([
      api.course(id),
      api.schedules(id),
      api.courseSessions(id),
      api.materials(id),
    ]);
    return { detail, schedules, sessions, materials };
  });

  const ready = Boolean(data);
  useEffect(() => {
    if (ready && section !== "subjects") document.getElementById(`estudio-${section}`)?.scrollIntoView({ block: "start" });
  }, [ready, section]);

  const done = () => {
    setOpen(null);
    void refresh();
  };

  if (!data) {
    return (
      <Screen>
        <ScreenHeader back={{ label: "Study", onClick: () => navigate({ tab: "home" }) }} />
        <OfflineNotice />
        <Problem text={problem} />
        <Pending found={found} />
      </Screen>
    );
  }

  const { course, subjects, assessments } = data.detail;
  const closed = course.status === "finished" || course.status === "abandoned";
  const average = course.average.average ?? course.grade?.current ?? null;
  const withCurrent = subjects.filter((s) => (s.grade.final ?? s.grade.current) !== null);
  const provisional = withCurrent.length
    ? withCurrent.reduce((sum, s) => sum + (s.grade.final ?? s.grade.current)! * (s.credits ?? 1), 0) /
      withCurrent.reduce((sum, s) => sum + (s.credits ?? 1), 0)
    : null;
  const eyebrow = [labelOf(KINDS, course.kind), course.institution].filter(Boolean).join(" · ");

  return (
    <Screen wide>
      <ScreenHeader
        back={
          closed
            ? { label: "Archivo", onClick: () => navigate({ tab: "archive" }) }
            : { label: "Study", onClick: () => navigate({ tab: "home" }) }
        }
        eyebrow={eyebrow}
        title={course.name}
      />
      <OfflineNotice />
      <Problem text={problem} />

      <section className="study-hero" data-tone={course.tone} aria-label="Resumen">
        <div className="study-hero-facts">
          <span>
            {[
              period(course.starts_on, course.ends_on),
              labelOf(MODALITIES, course.modality),
              `de 0 a ${grade(course.scale_max, 100)}, aprobado ${grade(course.pass_mark, course.scale_max)}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
          {closed && (
            <Badge tone={course.status === "finished" ? "positive" : "neutral"}>
              {course.status === "finished" ? "Terminado" : "Abandonado"}
              {course.closed_on && ` · ${dateShort(course.closed_on)}`}
            </Badge>
          )}
        </div>
        {course.tracks.length > 0 && (
        <dl className="study-figures">
          {course.tracks.includes("grades") && (
          <div className="study-figure">
            <dt>Media</dt>
            <dd className="study-figure-value">{grade(average, course.scale_max)}</dd>
            <dd className="study-figure-foot">
              {course.average.subjects
                ? average === null && provisional !== null
                  ? `Provisional ${grade(provisional, course.scale_max)}`
                  : `${course.average.counted} de ${plural(course.average.subjects, "asignatura", "asignaturas")}`
                : course.grade?.verdict === "empty"
                  ? "Sin evaluables"
                  : "De lo calificado"}
            </dd>
          </div>
          )}
          {course.tracks.includes("progress") && (
          <div className="study-figure">
            <dt>Progreso</dt>
            <dd className="study-figure-value">{course.progress ? percent(course.progress.ratio * 100) : "—"}</dd>
            <dd className="study-figure-foot">{course.progress?.label ?? "Sin créditos ni horas"}</dd>
          </div>
          )}
          {course.tracks.includes("attendance") && (
          <div className="study-figure">
            <dt>Asistencia</dt>
            <dd className="study-figure-value">
              {course.attendance.ratio === null ? "—" : percent(course.attendance.ratio * 100)}
            </dd>
            <dd className="study-figure-foot">
              {course.attendance.past
                ? `${course.attendance.present} de ${course.attendance.present + course.attendance.absent}` +
                  (course.attendance.unmarked ? ` · ${course.attendance.unmarked} sin marcar` : "")
                : "Aún ninguna clase"}
            </dd>
          </div>
          )}
        </dl>
        )}
        {course.progress && course.tracks.includes("progress") && <ProgressBar ratio={course.progress.ratio} tone={course.tone} label={course.progress.label} />}
        <div className="study-hero-actions">
          {course.campus_url && (
            <a className="button" data-variant="tinted" href={course.campus_url} target="_blank" rel="noreferrer">
              <Icon name="arrow-right" />
              <span className="button-label">Campus</span>
            </a>
          )}
          {course.has_certificate && course.certificate_name && (
            <a className="button" data-variant="secondary" href={certificateUrl(data)} target="_blank" rel="noreferrer">
              <Icon name="done" />
              <span className="button-label">{course.certificate_name}</span>
            </a>
          )}
          <Button variant="secondary" icon="edit" onClick={() => setOpen({ sheet: "edit" })}>
            Editar
          </Button>
        </div>
      </section>

      <Panes
        main={
          <>
            {assessments.length > 0 && (
              <div id="estudio-assessments">
                <AssessmentsSection
                  title="Tareas y exámenes"
                  assessments={assessments}
                  onOpen={(assessment) => setOpen({ sheet: "assessment", assessment })}
                  onGrade={(assessment) => setOpen({ sheet: "grade", assessment })}
                  onAdd={() => setOpen({ sheet: "assessment", assessment: null })}
                />
              </div>
            )}
            <div id="estudio-schedule">
              <ScheduleSection
                loaded={data}
                onBlock={(schedule) => setOpen({ sheet: "schedule", schedule })}
                onAdd={() => setOpen({ sheet: "schedule", schedule: null })}
                onLoose={() => setOpen({ sheet: "session" })}
                onSession={(session) => navigate({ tab: "session", id: session.id })}
              />
            </div>
            {(subjects.length > 0 || course.tracks.includes("grades")) && (
              <div id="estudio-subjects">
                <SubjectsSection
                  subjects={subjects}
                  scale={course.scale_max}
                  onOpen={(subject) => navigate({ tab: "subject", id: subject.id })}
                  onAdd={() => setOpen({ sheet: "subject", subject: null })}
                  courseGrade={course.grade}
                />
              </div>
            )}
          </>
        }
        aside={
          <>
            <div id="estudio-notes">
              <CourseNotes courseId={id} />
            </div>
            <div id="estudio-materials">
              <MaterialsSection
                materials={data.materials}
                onAdd={() => setOpen({ sheet: "material" })}
                onDelete={(material) => setOpen({ sheet: "delete-material", material })}
              />
            </div>
          </>
        }
        asideLabel="Apuntes y materiales"
      />

      {!closed && <CreateButton label="Apuntar" onClick={() => setAdding(true)} />}

      <footer className="study-footer-actions">
        {closed ? (
          <Button
            variant="secondary"
            onClick={() =>
              void api
                .reopenCourse(id)
                .then(() => refresh())
                .catch(fail)
            }
          >
            Reabrir estudio
          </Button>
        ) : (
          <Button variant="secondary" onClick={() => setOpen({ sheet: "close" })}>
            Terminar o abandonar
          </Button>
        )}
        <Button variant="plain" onClick={() => setOpen({ sheet: "delete" })}>
          Borrar estudio
        </Button>
      </footer>

      {adding && (
        <AddSheet
          courses={[course]}
          course={course.id}
          onClose={() => setAdding(false)}
          onSaved={(message, next) => {
            setAdding(false);
            changed();
            void refresh();
            toast({ message });
            if (next) navigate(next);
          }}
        />
      )}
      {open?.sheet === "edit" && (
        <CourseSheet course={course} onClose={() => setOpen(null)} onSaved={done} onError={fail} />
      )}
      {open?.sheet === "close" && (
        <CloseSheet
          course={course}
          onClose={() => setOpen(null)}
          onSaved={() => {
            setOpen(null);
            changed();
            navigate({ tab: "archive" });
          }}
          onError={fail}
        />
      )}
      {open?.sheet === "delete" && (
        <ConfirmDelete
          title="¿Borrar este estudio?"
          subject={course.name}
          consequence={`Se borran sus ${plural(subjects.length, "asignatura", "asignaturas")}, sus clases, sus evaluables con sus notas, sus apuntes y sus ficheros. Si lo has terminado, mejor archívalo.`}
          action="Borrar estudio"
          onCancel={() => setOpen(null)}
          onConfirm={async () => {
            await api.deleteCourse(id);
            changed();
            navigate({ tab: "home" });
          }}
        />
      )}
      {open?.sheet === "subject" && (
        <SubjectSheet courseId={id} subject={open.subject} onClose={() => setOpen(null)} onSaved={done} onError={fail} />
      )}
      {open?.sheet === "assessment" && (
        <AssessmentSheet
          course={course}
          subjects={subjects}
          assessment={open.assessment}
          onClose={() => setOpen(null)}
          onSaved={done}
          onDelete={open.assessment ? () => setOpen({ sheet: "delete-assessment", assessment: open.assessment! }) : undefined}
          onError={fail}
        />
      )}
      {open?.sheet === "grade" && (
        <GradeSheet assessment={open.assessment} onClose={() => setOpen(null)} onSaved={done} onError={fail} />
      )}
      {open?.sheet === "delete-assessment" && (
        <ConfirmDelete
          title="¿Borrar este evaluable?"
          subject={open.assessment.title}
          consequence={open.assessment.grade !== null ? "Se pierde su nota y deja de contar en la media." : undefined}
          action="Borrar evaluable"
          onCancel={() => setOpen(null)}
          onConfirm={async () => {
            await api.deleteAssessment(open.assessment.id);
            done();
          }}
        />
      )}
      {open?.sheet === "schedule" && (
        <ScheduleSheet
          course={course}
          subjects={subjects}
          schedule={open.schedule}
          onClose={() => setOpen(null)}
          onSaved={done}
          onDelete={open.schedule ? () => setOpen({ sheet: "delete-schedule", schedule: open.schedule! }) : undefined}
          onError={fail}
        />
      )}
      {open?.sheet === "delete-schedule" && (
        <ConfirmDelete
          title="¿Quitar este bloque del horario?"
          subject={`${open.schedule.subject ?? course.name} · ${open.schedule.phrase}`}
          consequence="Se quitan sus clases futuras sin tocar. Las que ya pasaron o tienen apuntes o asistencia se quedan."
          action="Quitar del horario"
          onCancel={() => setOpen(null)}
          onConfirm={async () => {
            await api.deleteSchedule(open.schedule.id);
            done();
          }}
        />
      )}
      {open?.sheet === "session" && (
        <SessionSheet
          course={course}
          subjects={subjects}
          onClose={() => setOpen(null)}
          onSaved={(sessionId) => {
            setOpen(null);
            changed();
            navigate({ tab: "session", id: sessionId });
          }}
          onError={fail}
        />
      )}
      {open?.sheet === "material" && (
        <MaterialSheet courseId={id} subjects={subjects} onClose={() => setOpen(null)} onSaved={done} onError={fail} />
      )}
      {open?.sheet === "delete-material" && (
        <ConfirmDelete
          title="¿Quitar este material?"
          subject={open.material.title}
          consequence={open.material.attachment_id ? "Se borra el fichero." : undefined}
          action="Quitar material"
          onCancel={() => setOpen(null)}
          onConfirm={async () => {
            await api.deleteMaterial(open.material.id);
            done();
          }}
        />
      )}
    </Screen>
  );
}

function certificateUrl(data: Loaded): string {
  return `/api/study/courses/${data.detail.course.id}/certificate`;
}

function SubjectsSection({
  subjects,
  scale,
  onOpen,
  onAdd,
  courseGrade,
}: {
  subjects: Subject[];
  scale: number;
  onOpen: (subject: Subject) => void;
  onAdd: () => void;
  courseGrade: CourseDetail["course"]["grade"];
}) {
  return (
    <Section
      title="Asignaturas"
      count={subjects.length}
      action={{ label: "Añadir", icon: "plus", onClick: onAdd }}
    >
      {subjects.length === 0 ? (
        <Empty title="Sin asignaturas">
          <p>
            Un curso corto no las necesita: sus evaluables cuelgan del estudio.
            {courseGrade && courseGrade.verdict !== "empty" && ` ${courseGrade.sentence}`}
          </p>
        </Empty>
      ) : (
        <List>
          {subjects.map((subject) => {
            const hint = neededLine(subject.grade, scale);
            const meta =
              [subject.credits ? `${grade(subject.credits, 100)} créditos` : null, subject.period, subject.teacher]
                .filter(Boolean)
                .join(" · ") || plural(subject.assessments, "evaluable", "evaluables");
            return (
              <ListRow
                key={subject.id}
                title={subject.name}
                subtitle={[hint, meta].filter(Boolean).join(" · ")}
                detail={verdictLabel(subject.grade.verdict)}
                value={grade(subject.grade.final ?? subject.grade.current, scale)}
                tone={rowTone(verdictTone(subject.grade.verdict))}
                accessory="chevron-right"
                onClick={() => onOpen(subject)}
              />
            );
          })}
        </List>
      )}
    </Section>
  );
}

export function scheduleEvents(schedules: Schedule[], tone: CourseDetail["course"]["tone"], week: string[]): CalendarEvent[] {
  const events: CalendarEvent[] = [];
  for (const block of schedules) {
    const days = block.rule.freq === "weekly" && block.rule.by_day.length
      ? block.rule.by_day.map((d) => d.weekday)
      : [WEEK[(new Date(`${block.starts_on}T12:00:00`).getDay() + 6) % 7]!];
    for (const weekday of days) {
      const index = WEEK.indexOf(weekday as (typeof WEEK)[number]);
      const day = week[index];
      if (!day) continue;
      events.push({
        id: `${block.id}:${weekday}`,
        title: block.subject ?? "Clase",
        start: `${day}T${hhmm(block.start_time)}:00`,
        end: `${day}T${hhmm(block.end_time)}:00`,
        tone,
        subtitle: block.place ?? undefined,
        recurring: true,
      });
    }
  }
  return events;
}

function ScheduleSection({
  loaded,
  onBlock,
  onAdd,
  onLoose,
  onSession,
}: {
  loaded: Loaded;
  onBlock: (schedule: Schedule) => void;
  onAdd: () => void;
  onLoose: () => void;
  onSession: (session: Session) => void;
}) {
  const { course } = loaded.detail;
  const monday = addDays(mondayOf(todayIso()), 7);
  const week = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
  const events = scheduleEvents(loaded.schedules, course.tone, week);
  const weekend = events.some((event) => {
    const day = String(event.start).slice(0, 10);
    return day === week[5] || day === week[6];
  });
  const shown = weekend ? week : week.slice(0, 5);
  const firstHour = loaded.schedules.length
    ? Math.min(...loaded.schedules.map((s) => Number(s.start_time.slice(0, 2))))
    : 8;
  const now = new Date();
  const upcoming = loaded.sessions.filter((s) => new Date(s.ends_at) > now).slice(0, 6);
  const loose = loaded.sessions.filter((s) => s.kind !== "class" && new Date(s.ends_at) > now);

  return (
    <>
      <Section
        title="Horario"
        action={{ label: "Añadir clase", icon: "plus", onClick: onAdd }}
      >
        {loaded.schedules.length === 0 ? (
          <Empty title="Sin horario todavía">
            <p>
              Añade cada clase que se repite —«Estadística, martes y jueves de 18:00 a 20:00 hasta enero»— y Study crea todas
              las del periodo, cada una con su asistencia y sus apuntes.
            </p>
            <Button variant="tinted" icon="plus" onClick={onAdd}>
              Añadir la primera
            </Button>
          </Empty>
        ) : (
          <>
            <div className="surface study-timetable">
              <TimeGrid
                label={`Horario semanal de ${course.name}`}
                days={shown}
                events={events}
                showDates={false}
                scrollToHour={Math.max(0, firstHour - 1)}
                onEventClick={(eventId) => {
                  const block = loaded.schedules.find((s) => eventId.startsWith(s.id));
                  if (block) onBlock(block);
                }}
              />
            </div>
            <List>
              {loaded.schedules.map((block) => (
                <ListRow
                  key={block.id}
                  title={block.subject ?? course.name}
                  subtitle={`${capital(block.phrase)} · ${hhmm(block.start_time)}–${hhmm(block.end_time)}${block.place ? ` · ${block.place}` : ""}`}
                  detail={plural(block.sessions, "clase", "clases")}
                  accessory="chevron-right"
                  onClick={() => onBlock(block)}
                />
              ))}
            </List>
          </>
        )}
      </Section>

      <Section
        title="Próximas clases"
        action={{ label: "Sesión suelta", icon: "plus", onClick: onLoose }}
      >
        {upcoming.length === 0 && loose.length === 0 ? (
          <p className="study-muted">No queda ninguna. Una tutoría, una jornada o la defensa, con «Sesión suelta».</p>
        ) : (
          <SessionList sessions={upcoming} onOpen={onSession} />
        )}
      </Section>
    </>
  );
}

const capital = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export function SessionList({
  sessions,
  onOpen,
  inSubject = false,
}: {
  sessions: Session[];
  onOpen: (session: Session) => void;
  inSubject?: boolean;
}) {
  return (
    <List>
      {sessions.map((session) => {
        const start = new Date(session.starts_at);
        const status =
          session.status === "cancelled"
            ? "Cancelada"
            : session.attendance === "present"
              ? "Fui"
              : session.attendance === "absent"
                ? "No fui"
                : undefined;
        return (
          <ListRow
            key={session.id}
            title={
              inSubject && session.kind === "class"
                ? (session.topic ?? capital(start.toLocaleDateString("es-ES", { weekday: "long" })))
                : session.title
            }
            subtitle={[
              `${capital(dateLong(todayIsoOf(start)))} · ${hhmm(start.toTimeString())}`,
              session.place,
              !inSubject ? session.topic : null,
              session.has_notes ? "con apuntes" : null,
            ]
              .filter(Boolean)
              .join(" · ")}
            detail={status}
            tone={session.status === "cancelled" ? "negative" : session.attendance === "present" ? "positive" : undefined}
            accessory="chevron-right"
            onClick={() => onOpen(session)}
          />
        );
      })}
    </List>
  );
}

const todayIsoOf = (date: Date) => {
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${m}-${d}`;
};

export function AssessmentsSection({
  assessments,
  onOpen,
  onGrade,
  onAdd,
  title = "Evaluables",
}: {
  assessments: Assessment[];
  onOpen: (assessment: Assessment) => void;
  onGrade: (assessment: Assessment) => void;
  onAdd: () => void;
  title?: string;
}) {
  const pending = assessments.filter((a) => a.status !== "graded");
  const graded = assessments.filter((a) => a.status === "graded");
  const weights = assessments.reduce((sum, a) => sum + (a.weight ?? 0), 0);
  return (
    <Section
      title={title}
      count={assessments.length}
      action={{ label: "Añadir", icon: "plus", onClick: onAdd }}
    >
      {assessments.length === 0 ? (
        <Empty title="Sin evaluables">
          <p>Las entregas y los exámenes con su peso. Con ellos, Study te dice qué nota necesitas en lo que queda.</p>
        </Empty>
      ) : (
        <>
          {weights > 0 && Math.abs(weights - 100) > 0.01 && assessments.every((a) => a.subject_id === assessments[0]!.subject_id) && (
            <p className="study-muted">
              Los pesos suman {percent(weights)}.{" "}
              {weights < 100 ? "Lo que falta cuenta como pendiente." : "Revisa los pesos: pasan del 100 %."}
            </p>
          )}
          {pending.length > 0 && (
            <List>
              {pending.map((item) => (
                <AssessmentRow key={item.id} item={item} onOpen={onOpen} onGrade={onGrade} />
              ))}
            </List>
          )}
          {graded.length > 0 && (
            <>
              <GroupLabel>Calificados</GroupLabel>
              <List>
                {graded.map((item) => (
                  <AssessmentRow key={item.id} item={item} onOpen={onOpen} onGrade={onGrade} />
                ))}
              </List>
            </>
          )}
        </>
      )}
    </Section>
  );
}

function AssessmentRow({
  item,
  onOpen,
  onGrade,
}: {
  item: Assessment;
  onOpen: (assessment: Assessment) => void;
  onGrade: (assessment: Assessment) => void;
}) {
  const below = item.grade !== null && item.min_grade !== null && item.grade < item.min_grade;
  const pending = item.status !== "graded";
  return (
    <ListRow
      title={item.title}
      subtitle={[
        labelOf(ASSESSMENT_KINDS, item.kind),
        item.subject,
        item.due_on ? `${dateShort(item.due_on)}${item.due_time ? ` ${hhmm(item.due_time)}` : ""}` : "Sin fecha",
        item.weight !== null ? percent(item.weight) : "sin peso",
        item.min_grade !== null ? `mín. ${grade(item.min_grade, item.scale_max)}` : null,
      ]
        .filter(Boolean)
        .join(" · ")}
      detail={
        below
          ? "Bajo el mínimo"
          : item.status === "submitted"
            ? "Entregado"
            : pending && item.days_left !== null
              ? countdown(item.days_left)
              : undefined
      }
      value={item.grade === null ? undefined : grade(item.grade, item.scale_max)}
      tone={below ? "negative" : pending && item.days_left !== null ? dueTone(item.days_left) : undefined}
      onClick={() => onOpen(item)}
      action={{
        icon: "edit",
        label: item.grade === null ? `Poner nota a ${item.title}` : `Cambiar la nota de ${item.title}`,
        onClick: () => onGrade(item),
      }}
    />
  );
}

export function MaterialsSection({
  materials,
  onAdd,
  onDelete,
}: {
  materials: Material[];
  onAdd: () => void;
  onDelete: (material: Material) => void;
}) {
  return (
    <Section
      title="Materiales"
      count={materials.length}
      action={{ label: "Añadir", icon: "plus", onClick: onAdd }}
    >
      {materials.length === 0 ? (
        <Empty title="Sin materiales">
          <p>La guía docente, el campus de cada asignatura, las diapositivas, la bibliografía.</p>
        </Empty>
      ) : (
        <List>
          {materials.map((material) => (
            <ListRow
              key={material.id}
              title={material.title}
              subtitle={[material.subject, material.url ? host(material.url) : material.size ? fileSize(material.size) : extension(material.filename)]
                .filter(Boolean)
                .join(" · ")}
              icon={material.url ? "external" : "file"}
              onClick={() => window.open(material.url ?? fileUrl(material.attachment_id!), "_blank", "noreferrer")}
              action={{ icon: "trash", label: `Quitar ${material.title}`, onClick: () => onDelete(material) }}
            />
          ))}
        </List>
      )}
    </Section>
  );
}

const extension = (name: string | null) => (name?.split(".").pop() ?? "").slice(0, 4).toUpperCase() || "—";

function host(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function CourseNotes({ courseId }: { courseId: string }) {
  const navigate = useNavigate();
  const { data, found, problem, fail } = useLoad(`notes:course:${courseId}`, () => api.notes({ courseId }));
  return (
    <Section
      title="Apuntes"
      count={data?.length}
      action={{
        label: "Nuevos",
        icon: "plus",
        onClick: () =>
          void api
            .addNote({ course_id: courseId, title: "" })
            .then((note) => navigate({ tab: "note", id: note.id }))
            .catch(fail),
      }}
    >
      <Problem text={problem} />
      {data === null && <Pending found={found} />}
      {data && data.length === 0 && (
        <p className="study-muted">Los de cada clase salen aquí, y todo lo que haya en la carpeta del estudio en Notebook.</p>
      )}
      {data && data.length > 0 && <NoteGroups notes={data} />}
    </Section>
  );
}
