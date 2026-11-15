import {
  ChoiceChips,
  Collapsible,
  DateField,
  Hint,
  RecurrencePicker,
  type RecurrenceRule,
  SelectField,
  Sheet,
  Switch,
  TextField,
} from "@openarga/ui";
import { useState } from "react";

import { type AssessmentKind, type Course, api } from "./api";
import { ASSESSMENT_KINDS, atTime, localIso, ruleToServer, todayIso } from "./words";
import { t } from "./lang";

export type AddKind = "class" | "task" | "exam" | "note";

const KINDS: { value: AddKind; readonly label: string }[] = (["class", "task", "exam", "note"] as const).map((value) => ({
  value,
  get label() {
    return t(`add.kind.${value}`);
  },
}));

export function plan(
  kind: AddKind,
  form: { title: string; day: string; from: string; to: string; time: string; repeats: boolean; type: AssessmentKind; place: string; url: string },
):
  | { call: "session"; body: { kind: "class"; title: string | null; subject_id: null; starts_at: string; ends_at: string; place: string | null; url: string | null } }
  | { call: "schedule" }
  | { call: "assessment"; body: { title: string; kind: AssessmentKind; due_on: string; due_time: string | null } }
  | { call: "note"; title: string } {
  if (kind === "note") return { call: "note", title: form.title.trim() };
  if (kind === "class") {
    if (form.repeats) return { call: "schedule" };
    return {
      call: "session",
      body: {
        kind: "class",
        title: form.title.trim() || null,
        subject_id: null,
        starts_at: localIso(atTime(form.day, form.from)),
        ends_at: localIso(atTime(form.day, form.to)),
        place: form.place.trim() || null,
        url: form.url.trim() || null,
      },
    };
  }
  return {
    call: "assessment",
    body: {
      title: form.title.trim(),
      kind: kind === "exam" ? "exam" : form.type,
      due_on: form.day,
      due_time: form.time || null,
    },
  };
}

export function AddSheet({
  courses,
  course: initial,
  onClose,
  onSaved,
}: {
  courses: Course[];
  course?: string;
  onClose: () => void;
  onSaved: (message: string, open?: { tab: "note"; id: string }) => void;
}) {
  const [kind, setKind] = useState<AddKind>("task");
  const [course, setCourse] = useState(initial ?? courses[0]?.id ?? "");
  const [title, setTitle] = useState("");
  const [day, setDay] = useState(todayIso());
  const [from, setFrom] = useState("18:00");
  const [to, setTo] = useState("19:00");
  const [time, setTime] = useState("");
  const [repeats, setRepeats] = useState(false);
  const [rule, setRule] = useState<RecurrenceRule | null>(null);
  const [until, setUntil] = useState(courses.find((one) => one.id === initial)?.ends_on ?? "");
  const [type, setType] = useState<AssessmentKind>("assignment");
  const [place, setPlace] = useState("");
  const [url, setUrl] = useState("");
  const [weight, setWeight] = useState("");
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState("");

  const needsTitle = kind !== "class";
  const ready = Boolean(course) && Boolean(day || kind === "note") && (!needsTitle || title.trim().length > 0) && (!(kind === "class" && repeats) || rule);

  const save = async () => {
    setSaving(true);
    setProblem("");
    try {
      const what = plan(kind, { title, day, from, to, time, repeats, type, place, url });
      if (what.call === "note") {
        const note = await api.addNote({ course_id: course, title: what.title || undefined });
        onSaved(t("add.note_created"), { tab: "note", id: note.id });
        return;
      }
      if (what.call === "schedule" && rule) {
        await api.addSchedule(course, {
          subject_id: null,
          rule: ruleToServer(until ? { ...rule, until } : rule),
          starts_on: day,
          start_time: from,
          end_time: to,
          place: place.trim() || null,
          url: url.trim() || null,
        });
        onSaved(t("add.schedule_added"));
        return;
      }
      if (what.call === "session") {
        await api.addSession(course, what.body);
        onSaved(t("add.session_added"));
        return;
      }
      if (what.call === "assessment") {
        await api.addAssessment(course, {
          ...what.body,
          subject_id: null,
          weight: weight ? Number(weight.replace(",", ".")) : null,
          min_grade: null,
          status: "pending",
          grade: null,
          note: null,
        });
        onSaved(t(kind === "exam" ? "add.exam_added" : "add.task_added"));
      }
    } catch (error) {
      setProblem(error instanceof Error ? error.message : t("error.save"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet
      title={t("home.add")}
      onClose={onClose}
      action={{ label: saving ? t("action.saving") : t("action.save"), onClick: () => void save(), disabled: saving || !ready }}
    >
      <ChoiceChips label={t("add.what")} options={KINDS} value={kind} onChange={setKind} />
      {problem && <Hint tone="warning">{problem}</Hint>}
      <TextField
        label={kind === "class" ? t("field.title_optional") : t("field.title")}
        value={title}
        onChange={setTitle}
        placeholder={t(kind === "class" ? "add.ph.class" : kind === "exam" ? "add.ph.exam" : kind === "note" ? "add.ph.note" : "add.ph.task")}
        autoFocus
      />
      {courses.length > 1 && (
        <SelectField label={t("field.course")} options={courses.map((one) => ({ value: one.id, label: one.name }))} value={course} onChange={setCourse} />
      )}
      {kind !== "note" && <DateField label={kind === "task" ? t("field.due") : t("field.day")} value={day} onChange={setDay} />}
      {kind === "class" && (
        <>
          <TextField label={t("field.from")} type="time" value={from} onChange={setFrom} />
          <TextField label={t("field.to")} type="time" value={to} onChange={setTo} />
          <div className="study-switch">
            <span>{t("add.repeats")}</span>
            <Switch label={t("add.repeats")} checked={repeats} onChange={setRepeats} />
          </div>
          {repeats && (
            <>
              <RecurrencePicker date={day || todayIso()} value={rule} onChange={setRule} label={t("field.every")} />
              <DateField label={t("field.until")} value={until} onChange={setUntil} />
            </>
          )}
        </>
      )}
      {(kind === "task" || kind === "exam") && <TextField label={t("field.time")} type="time" value={time} onChange={setTime} hint={t("add.no_time_hint")} />}
      {kind !== "note" && (
        <Collapsible title={t("add.more")} subtitle={kind === "class" ? t("add.place_link") : t("add.type_weight")}>
          {kind === "task" && <ChoiceChips label={t("field.type")} options={ASSESSMENT_KINDS.filter((one) => one.value !== "exam")} value={type} onChange={setType} />}
          {(kind === "task" || kind === "exam") && (
            <TextField label={t("field.weight")} value={weight} onChange={setWeight} inputMode="decimal" placeholder="%" hint={t("add.weight_hint")} />
          )}
          {kind === "class" && (
            <>
              <TextField label={t("field.place")} value={place} onChange={setPlace} placeholder="Room 2.3" />
              <TextField label={t("field.link")} value={url} onChange={setUrl} placeholder={t("add.link_placeholder")} />
            </>
          )}
        </Collapsible>
      )}
      {kind !== "note" && <Hint>{t("add.in_calendar")}</Hint>}
    </Sheet>
  );
}
