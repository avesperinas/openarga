import { Button, ConfirmDelete, GroupLabel, List, ListRow, Notice, OfflineNotice, Screen } from "@openarga/ui";
import { useState } from "react";

import { type Assessment, type Material, type Schedule, api } from "./api";
import { useNavigate } from "./App";
import { GradeMeter, Pending, Problem, Section, changed, useLoad } from "./Bits";
import { AssessmentsSection, MaterialsSection, SessionList } from "./CourseScreen";
import { ScreenHeader } from "./Header";
import { NoteList } from "./Notes";
import { AssessmentSheet, GradeSheet, MaterialSheet, RecordSheet, ScheduleSheet, SessionSheet, SubjectSheet } from "./Sheets";
import { grade, hhmm, plural } from "./words";
import { intl, t } from "./lang";

type Open =
  | { sheet: "edit" }
  | { sheet: "record" }
  | { sheet: "delete" }
  | { sheet: "assessment"; assessment: Assessment | null }
  | { sheet: "grade"; assessment: Assessment }
  | { sheet: "delete-assessment"; assessment: Assessment }
  | { sheet: "schedule"; schedule: Schedule | null }
  | { sheet: "session" }
  | { sheet: "material" }
  | { sheet: "delete-material"; material: Material };

export function SubjectScreen({ id }: { id: string }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState<Open | null>(null);
  const [allClasses, setAllClasses] = useState(false);
  const { data, found, problem, fail, refresh } = useLoad(`subject:${id}`, () => api.subject(id));

  const done = () => {
    setOpen(null);
    void refresh();
  };

  if (!data) {
    return (
      <Screen>
        <ScreenHeader back={{ label: t("app.name"), onClick: () => navigate({ tab: "home" }) }} />
        <OfflineNotice />
        <Problem text={problem} />
        <Pending found={found} />
      </Screen>
    );
  }

  const { subject, course } = data;
  const subjects = [{ id: subject.id, name: subject.name }];
  const now = new Date();
  const past = data.sessions.filter((s) => new Date(s.ends_at) <= now).reverse();
  const future = data.sessions.filter((s) => new Date(s.ends_at) > now);
  const next = future.find((s) => s.status === "scheduled");
  const marked = past.filter((s) => s.status === "scheduled");
  const present = marked.filter((s) => s.attendance === "present").length;

  return (
    <Screen>
      <ScreenHeader
        back={{ label: course.name, onClick: () => navigate({ tab: "course", id: course.id }) }}
        eyebrow={[
          subject.credits ? t("subject.credits", { credits: grade(subject.credits, 100) }) : null,
          subject.period,
          subject.teacher,
        ]
          .filter(Boolean)
          .join(" · ") || course.name}
        title={subject.name}
      />
      <OfflineNotice />
      <Problem text={problem} />

      <section className="surface study-grade-card">
        <GradeMeter grade={subject.grade} scale={course.scale_max} passMark={course.pass_mark} tone={course.tone} />
        <div className="study-row-actions">
          <Button variant="tinted" size="small" icon="plus" onClick={() => setOpen({ sheet: "assessment", assessment: null })}>
            {t("assessment.one")}
          </Button>
          <Button variant="secondary" size="small" onClick={() => setOpen({ sheet: "record" })}>
            {subject.final_grade === null ? t("meter.record") : t("subject.record_is", { grade: grade(subject.final_grade, course.scale_max) })}
          </Button>
        </div>
      </section>

      {next && (
        <List>
          <ListRow
            title={t("subject.next_session")}
            subtitle={[
              new Date(next.starts_at).toLocaleDateString(intl(), { weekday: "long", day: "numeric", month: "long" }),
              hhmm(new Date(next.starts_at).toTimeString()),
              next.place,
            ]
              .filter(Boolean)
              .join(" · ")}
            icon="calendar"
            hue={8}
            accessory="chevron-right"
            onClick={() => navigate({ tab: "session", id: next.id })}
          />
        </List>
      )}

      <AssessmentsSection
        assessments={data.assessments}
        onOpen={(assessment) => setOpen({ sheet: "assessment", assessment })}
        onGrade={(assessment) => setOpen({ sheet: "grade", assessment })}
        onAdd={() => setOpen({ sheet: "assessment", assessment: null })}
      />

      <Section
        title={t("sessions.title")}
        count={data.sessions.length}
        action={{ label: data.schedules.length ? t("sessions.one_off") : t("schedule.title"), icon: "plus", onClick: () => setOpen(data.schedules.length ? { sheet: "session" } : { sheet: "schedule", schedule: null }) }}
      >
        {data.schedules.length > 0 && (
          <List>
            {data.schedules.map((block) => (
              <ListRow
                key={block.id}
                title={block.phrase.charAt(0).toUpperCase() + block.phrase.slice(1)}
                subtitle={[t("schedule.from_to", { from: hhmm(block.start_time), to: hhmm(block.end_time) }), block.place].filter(Boolean).join(" · ")}
                icon="repeat"
                accessory="edit"
                onClick={() => setOpen({ sheet: "schedule", schedule: block })}
              />
            ))}
          </List>
        )}
        {marked.length > 0 && (
          <p className="study-muted">
            {t("subject.attendance", { present, of: plural(marked.length, "subject.past_sessions") })}
            {marked.filter((s) => s.attendance === null).length > 0 &&
              ` · ${t("subject.unmarked", { count: marked.filter((s) => s.attendance === null).length })}`}
          </p>
        )}
        {data.sessions.length === 0 ? (
          <p className="study-muted">{t("sessions.empty")}</p>
        ) : (
          <>
            <SessionList inSubject sessions={future.slice(0, allClasses ? undefined : 4)} onOpen={(s) => navigate({ tab: "session", id: s.id })} />
            {past.length > 0 && (
              <>
                <GroupLabel>{t("sessions.past")}</GroupLabel>
                <SessionList inSubject sessions={past.slice(0, allClasses ? undefined : 4)} onOpen={(s) => navigate({ tab: "session", id: s.id })} />
              </>
            )}
            {(future.length > 4 || past.length > 4) && (
              <Button variant="plain" size="small" onClick={() => setAllClasses(!allClasses)}>
                {allClasses ? t("action.see_less") : t("sessions.see_all", { count: data.sessions.length })}
              </Button>
            )}
          </>
        )}
      </Section>

      <Section
        title={t("notes.title")}
        count={data.notes.length}
        action={{ label: t("action.new"), icon: "plus", onClick: () =>
              void api
                .addNote({ course_id: course.id, subject_id: subject.id, title: "" })
                .then((note) => navigate({ tab: "note", id: note.id }))
                .catch(fail) }}
      >
        {data.notes_unavailable ? (
          <Notice tone="warning" title={t("notes.unavailable")}>
            {data.notes_unavailable}
          </Notice>
        ) : data.notes.length === 0 ? (
          <p className="study-muted">{t("notes.subject_empty")}</p>
        ) : (
          <NoteList notes={data.notes} showCourse={false} />
        )}
      </Section>

      <MaterialsSection
        materials={data.materials}
        onAdd={() => setOpen({ sheet: "material" })}
        onDelete={(material) => setOpen({ sheet: "delete-material", material })}
      />

      <footer className="study-footer-actions">
        <Button variant="secondary" icon="edit" onClick={() => setOpen({ sheet: "edit" })}>
          {t("subject.edit")}
        </Button>
        <Button variant="plain" onClick={() => setOpen({ sheet: "delete" })}>
          {t("subject.delete")}
        </Button>
      </footer>

      {open?.sheet === "edit" && (
        <SubjectSheet courseId={course.id} subject={subject} onClose={() => setOpen(null)} onSaved={done} onError={fail} />
      )}
      {open?.sheet === "record" && (
        <RecordSheet subject={subject} scale={course.scale_max} onClose={() => setOpen(null)} onSaved={done} onError={fail} />
      )}
      {open?.sheet === "delete" && (
        <ConfirmDelete
          title={t("subject.delete_title")}
          subject={subject.name}
          consequence={t("subject.delete_consequence")}
          action={t("subject.delete")}
          onCancel={() => setOpen(null)}
          onConfirm={async () => {
            await api.deleteSubject(subject.id);
            changed();
            navigate({ tab: "course", id: course.id });
          }}
        />
      )}
      {open?.sheet === "assessment" && (
        <AssessmentSheet
          course={course}
          subjects={subjects}
          subjectId={subject.id}
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
          title={t("assessment.delete_title")}
          subject={open.assessment.title}
          consequence={open.assessment.grade !== null ? t("assessment.delete_consequence") : undefined}
          action={t("assessment.delete")}
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
          subjectId={subject.id}
          schedule={open.schedule}
          onClose={() => setOpen(null)}
          onSaved={done}
          onError={fail}
        />
      )}
      {open?.sheet === "session" && (
        <SessionSheet
          course={course}
          subjects={subjects}
          subjectId={subject.id}
          onClose={() => setOpen(null)}
          onSaved={(sessionId) => {
            changed();
            navigate({ tab: "session", id: sessionId });
          }}
          onError={fail}
        />
      )}
      {open?.sheet === "material" && (
        <MaterialSheet
          courseId={course.id}
          subjects={subjects}
          subjectId={subject.id}
          onClose={() => setOpen(null)}
          onSaved={done}
          onError={fail}
        />
      )}
      {open?.sheet === "delete-material" && (
        <ConfirmDelete
          title={t("material.delete_title")}
          subject={open.material.title}
          action={t("material.delete")}
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
