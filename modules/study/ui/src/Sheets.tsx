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
import { t } from "./lang";

function useSaving(onError: (error: unknown) => void) {
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState("");
  const run = async (action: () => Promise<void>) => {
    setSaving(true);
    setProblem("");
    try {
      await action();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : t("error.save"));
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

function subjectOptions(subjects: Pick<Subject, "id" | "name">[], none = t("field.whole_course")) {
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
      if (!name.trim()) return setProblem(t("course.needs_name"));
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
      title={subject ? t("subject.edit") : t("subject.new")}
      onClose={onClose}
      action={{ label: subject ? t("action.save") : t("subject.add"), onClick: () => void save(), disabled: saving }}
    >
      <div className="study-form">
        <TextField label={t("field.name")} value={name} onChange={setName} autoFocus={!subject} onSubmit={() => void save()} />
        <div className="study-pair">
          <TextField label={t("field.credits")} value={credits} onChange={setCredits} inputMode="decimal" placeholder="6" />
          <TextField label={t("field.period")} value={period} onChange={setPeriod} placeholder={t("subject.period_placeholder")} />
        </div>
        <TextField label={t("field.teacher")} value={teacher} onChange={setTeacher} />
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
      if (!title.trim()) return setProblem(t("error.needs_title"));
      const given = parseNumber(mark);
      if (status === "graded" && given === null) return setProblem(t("assessment.graded_needs_grade"));
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
      title={assessment ? assessment.title : t("assessment.new")}
      onClose={onClose}
      action={{ label: assessment ? t("action.save") : t("action.add"), onClick: () => void save(), disabled: saving }}
    >
      <div className="study-form">
        <TextField label={t("field.title")} value={title} onChange={setTitle} autoFocus={!assessment} placeholder={t("add.ph.task")} />
        <ChoiceChips label={t("field.type")} options={ASSESSMENT_KINDS} value={kind} onChange={setKind} />
        {subjects.length > 0 && (
          <SelectField label={t("field.subject")} options={subjectOptions(subjects)} value={subject} onChange={setSubject} />
        )}
        <div className="study-pair">
          <DateField label={t("field.date")} value={dueOn} onChange={setDueOn} />
          <TextField label={t("field.time")} type="time" value={dueTime} onChange={setDueTime} hint={t("add.no_time_hint")} />
        </div>
        <div className="study-pair">
          <TextField label={t("field.weight")} value={weight} onChange={setWeight} inputMode="decimal" placeholder="%" hint={t("add.weight_hint")} />
          <TextField label={t("field.min_grade")} value={minimum} onChange={setMinimum} inputMode="decimal" placeholder="—" hint={t("assessment.min_hint")} />
        </div>
        <SegmentedControl
          label={t("field.status")}
          options={[
            { value: "pending", label: t("status.pending") },
            { value: "submitted", label: t("assessment.submitted") },
            { value: "graded", label: t("status.graded") },
          ]}
          value={status}
          onChange={setStatus}
        />
        {status === "graded" && (
          <TextField
            label={t("assessment.grade_0_to", { max: grade(course.scale_max, 100) })}
            value={mark}
            onChange={setMark}
            inputMode="decimal"
            autoFocus
          />
        )}
        <TextField label={t("assessment.remark")} value={note} onChange={setNote} placeholder={t("assessment.remark_placeholder")} />
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
    <Sheet title={t("assessment.grade_of", { title: assessment.title })} onClose={onClose} action={{ label: t("assessment.save_grade"), onClick: () => void save(), disabled: saving }}>
      <div className="study-form">
        <TextField
          label={t("assessment.from_0_to", { max: grade(assessment.scale_max, 100) })}
          value={mark}
          onChange={setMark}
          inputMode="decimal"
          autoFocus
          onSubmit={() => void save()}
          hint={assessment.min_grade !== null ? t("assessment.min_is", { grade: grade(assessment.min_grade, assessment.scale_max) }) : t("assessment.empty_removes")}
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
    <Sheet title={t("meter.record")} onClose={onClose} action={{ label: t("action.save"), onClick: () => void save(), disabled: saving }}>
      <div className="study-form">
        <p className="study-muted">
          {t("record.hint")}
        </p>
        <TextField label={t("assessment.from_0_to", { max: grade(scale, 100) })} value={mark} onChange={setMark} inputMode="decimal" autoFocus onSubmit={() => void save()} />
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
      if (!rule) return setProblem(t("schedule.needs_rule"));
      if (!startsOn) return setProblem(t("schedule.needs_start"));
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
      title={schedule ? t("schedule.edit") : t("schedule.add")}
      onClose={onClose}
      action={{ label: schedule ? t("schedule.save_move") : t("schedule.add_create"), onClick: () => void save(), disabled: saving }}
    >
      <div className="study-form">
        {subjects.length > 0 && (
          <SelectField label={t("field.subject")} options={subjectOptions(subjects, t("field.whole_course"))} value={subject} onChange={setSubject} />
        )}
        <div className="study-pair">
          <TextField label={t("field.from")} type="time" value={start} onChange={setStart} />
          <TextField label={t("field.to")} type="time" value={end} onChange={setEnd} />
        </div>
        <DateField label={t("schedule.from_day")} value={startsOn} onChange={setStartsOn} />
        <RecurrencePicker date={startsOn || todayIso()} value={rule} onChange={setRule} label={t("add.repeats")} />
        <div className="study-pair">
          <TextField label={t("field.place")} value={place} onChange={setPlace} placeholder="Room 2.3" />
          <TextField label={t("field.link")} value={url} onChange={setUrl} placeholder={t("add.link_placeholder")} />
        </div>
        {schedule && (
          <p className="study-muted">
            {t("schedule.touched_stay")}
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
      if (kind !== "class" && !title.trim()) return setProblem(t("error.needs_title"));
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
    <Sheet title={t("sessions.new")} onClose={onClose} action={{ label: t("action.add"), onClick: () => void save(), disabled: saving }}>
      <div className="study-form">
        <SegmentedControl
          label={t("add.what")}
          options={[
            { value: "tutorial", label: t("session.kind.tutorial") },
            { value: "event", label: t("sessions.event") },
            { value: "class", label: t("sessions.extra_class") },
          ]}
          value={kind}
          onChange={setKind}
        />
        <TextField label={t("field.title")} value={title} onChange={setTitle} placeholder={t(kind === "class" ? "sessions.class_placeholder" : "sessions.event_placeholder")} />
        {subjects.length > 0 && (
          <SelectField label={t("field.subject")} options={subjectOptions(subjects)} value={subject} onChange={setSubject} />
        )}
        <DateField label={t("field.day")} value={date} onChange={setDate} />
        <div className="study-pair">
          <TextField label={t("field.from")} type="time" value={start} onChange={setStart} />
          <TextField label={t("field.to")} type="time" value={end} onChange={setEnd} />
        </div>
        <div className="study-pair">
          <TextField label={t("field.place")} value={place} onChange={setPlace} />
          <TextField label={t("field.link")} value={url} onChange={setUrl} />
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
    <Sheet title={session.kind === "class" ? t("move.session") : t("move.change")} onClose={onClose} action={{ label: t("action.save"), onClick: () => void save("scheduled"), disabled: saving }}>
      <div className="study-form">
        {session.kind !== "class" && <TextField label={t("field.title")} value={title} onChange={setTitle} />}
        <DateField label={t("field.day")} value={date} onChange={setDate} />
        <div className="study-pair">
          <TextField label={t("field.from")} type="time" value={start} onChange={setStart} />
          <TextField label={t("field.to")} type="time" value={end} onChange={setEnd} />
        </div>
        <div className="study-pair">
          <TextField label={t("field.place")} value={place} onChange={setPlace} />
          <TextField label={t("field.link")} value={url} onChange={setUrl} />
        </div>
        <p className="study-muted">{t("move.only_this")}</p>
        <SheetProblem text={problem} />
        <div className="study-row-actions">
          {cancelled ? (
            <Button variant="secondary" size="small" onClick={() => void save("scheduled")}>
              Recuperar la clase
            </Button>
          ) : (
            <Button variant="secondary" size="small" onClick={() => void save("cancelled")}>
              {t("move.cancel_this")}
            </Button>
          )}
          {onDelete && (
            <Button variant="destructive" size="small" icon="trash" onClick={onDelete}>
              {t("session.delete")}
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
        if (!url.trim()) return setProblem(t("material.paste_link"));
        await api.addLink(courseId, { title: title.trim() || url.trim(), url: url.trim(), subject_id: owner });
      } else {
        if (!file) return setProblem(t("material.choose_file"));
        await api.addFile(courseId, file, owner);
      }
      onSaved();
    });

  return (
    <Sheet title={t("material.new")} onClose={onClose} action={{ label: t("action.add"), onClick: () => void save(), disabled: saving }}>
      <div className="study-form">
        <SegmentedControl
          label={t("add.what")}
          options={[
            { value: "link", label: t("field.link") },
            { value: "file", label: t("material.file") },
          ]}
          value={kind}
          onChange={setKind}
        />
        {kind === "link" ? (
          <>
            <TextField label={t("field.link")} value={url} onChange={setUrl} placeholder="https://" autoFocus />
            <TextField label={t("field.name")} value={title} onChange={setTitle} placeholder={t("material.name_placeholder")} />
          </>
        ) : (
          <label className="study-file-pick">
            <span className="text-field-label">{t("material.file")}</span>
            <input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            <span className="study-muted">{t("material.file_hint")}</span>
          </label>
        )}
        {subjects.length > 0 && (
          <SelectField label={t("material.of")} options={subjectOptions(subjects)} value={subject} onChange={setSubject} />
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
      title={t("close.title")}
      onClose={onClose}
      action={{ label: status === "finished" ? t("close.finish") : t("close.abandon"), onClick: () => void save(), disabled: saving }}
    >
      <div className="study-form">
        <SegmentedControl
          label={t("close.how")}
          options={[
            { value: "finished", label: t("archive.finished") },
            { value: "abandoned", label: t("archive.abandoned") },
          ]}
          value={status}
          onChange={setStatus}
        />
        <DateField label={t("field.date")} value={closedOn} onChange={setClosedOn} />
        {status === "finished" && (
          <>
            <TextField
              label={t("close.final_grade")}
              value={mark}
              onChange={setMark}
              inputMode="decimal"
              hint={suggested !== null ? t("close.average_is", { grade: grade(suggested, course.scale_max) }) : t("close.certificate_grade")}
            />
            <Collapsible title={t("close.certificate")} subtitle={t("close.certificate_hint")}>
              <label className="study-file-pick">
                <input type="file" accept="application/pdf,image/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
              </label>
            </Collapsible>
          </>
        )}
        <p className="study-muted">{t("close.detail")}</p>
        <SheetProblem text={problem} />
      </div>
    </Sheet>
  );
}
