import {
  Button,
  CheckChips,
  ChoiceChips,
  Collapsible,
  DateField,
  Hint,
  IconButton,
  SegmentedControl,
  Sheet,
  TextField,
  TONES,
} from "@openarga/ui";
import { useState } from "react";

import { type Course, type CourseDetail, type CourseIn, type Tone, type Track, api } from "./api";
import { KINDS, MODALITIES, decimal, parseNumber } from "./words";
import { t } from "./lang";

export function ToneField({ value, onChange }: { value: Tone; onChange: (tone: Tone) => void }) {
  return (
    <fieldset className="study-tones">
      <legend className="text-field-label">{t("field.colour")}</legend>
      <div className="study-tones-row">
        {TONES.map(({ tone, name }) => (
          <button
            key={tone}
            type="button"
            className="study-tone"
            data-tone={tone}
            aria-label={name}
            aria-pressed={value === tone}
            onClick={() => onChange(tone as Tone)}
          />
        ))}
      </div>
    </fieldset>
  );
}

interface SubjectRow {
  key: number;
  name: string;
  credits: string;
}

const TRACKS: { value: Track; readonly label: string }[] = (["grades", "progress", "attendance"] as const).map((value) => ({
  value,
  get label() {
    return t(`track.${value}`);
  },
}));

export function defaultTracks(kind: CourseIn["kind"]): Track[] {
  return kind === "language" || kind === "other" ? [] : ["grades", "progress", "attendance"];
}

export function CourseSheet({
  course,
  onClose,
  onSaved,
  onError,
}: {
  course: Course | null;
  onClose: () => void;
  onSaved: (detail: CourseDetail) => void;
  onError: (error: unknown) => void;
}) {
  const [name, setName] = useState(course?.name ?? "");
  const [kind, setKind] = useState<CourseIn["kind"]>(course?.kind ?? "master");
  const [institution, setInstitution] = useState(course?.institution ?? "");
  const [modality, setModality] = useState<CourseIn["modality"]>(course?.modality ?? "in_person");
  const [startsOn, setStartsOn] = useState(course?.starts_on ?? "");
  const [endsOn, setEndsOn] = useState(course?.ends_on ?? "");
  const [tone, setTone] = useState<Tone>(course?.tone ?? 1);
  const [credits, setCredits] = useState(course ? decimal(course.credits?.toString() ?? "") : "");
  const [hours, setHours] = useState(course ? decimal(course.hours?.toString() ?? "") : "");
  const [scale, setScale] = useState<"10" | "100">(course?.scale_max === 100 ? "100" : "10");
  const [passMark, setPassMark] = useState(course ? decimal(String(course.pass_mark)) : "");
  const [target, setTarget] = useState(course ? decimal(course.target_grade?.toString() ?? "") : "");
  const [campus, setCampus] = useState(course?.campus_url ?? "");
  const [planned, setPlanned] = useState<"active" | "planned">(course?.status === "planned" ? "planned" : "active");
  const [subjects, setSubjects] = useState<SubjectRow[]>(course ? [] : [{ key: 1, name: "", credits: "" }]);
  const [tracks, setTracks] = useState<Track[] | null>(course?.tracks ?? null);
  const [problem, setProblem] = useState("");
  const [saving, setSaving] = useState(false);
  const followed = tracks ?? defaultTracks(kind);

  const scaleMax = scale === "100" ? 100 : 10;

  const save = async () => {
    if (!name.trim()) {
      setProblem(t("course.needs_name"));
      return;
    }
    const body: CourseIn = {
      name: name.trim(),
      kind,
      institution: institution.trim() || null,
      modality,
      starts_on: startsOn || null,
      ends_on: endsOn || null,
      status: planned,
      credits: parseNumber(credits),
      hours: parseNumber(hours),
      scale_max: scaleMax,
      pass_mark: parseNumber(passMark),
      target_grade: parseNumber(target),
      tone,
      campus_url: campus.trim() || null,
      note: course?.note ?? null,
      tracks: followed,
    };
    setSaving(true);
    setProblem("");
    try {
      const saved = course
        ? await api.updateCourse(course.id, { ...body, final_grade: course.final_grade })
        : await api.createCourse({
            ...body,
            subjects: subjects
              .filter((row) => row.name.trim())
              .map((row) => ({ name: row.name.trim(), credits: parseNumber(row.credits) })),
          });
      onSaved(saved);
    } catch (error) {
      setProblem(error instanceof Error ? error.message : t("error.save"));
      onError(error);
    } finally {
      setSaving(false);
    }
  };

  const setRow = (key: number, change: Partial<SubjectRow>) =>
    setSubjects((rows) => rows.map((row) => (row.key === key ? { ...row, ...change } : row)));
  const addRow = () => setSubjects((rows) => [...rows, { key: Date.now(), name: "", credits: "" }]);

  return (
    <Sheet
      title={course ? t("course.edit") : t("home.new_course")}
      onClose={onClose}
      action={{ label: course ? t("action.save") : t("course.create"), onClick: () => void save(), disabled: saving }}
    >
      <div className="study-form">
        <TextField label={t("field.name")} value={name} onChange={setName} placeholder={t("course.name_placeholder")} autoFocus={!course} />
        <ChoiceChips label={t("add.what")} options={KINDS} value={kind} onChange={setKind} />
        <TextField label={t("field.institution")} value={institution} onChange={setInstitution} placeholder={t("course.institution_placeholder")} />
        <div className="study-pair">
          <DateField label={t("field.starts")} value={startsOn} onChange={setStartsOn} />
          <DateField label={t("field.ends")} value={endsOn} onChange={setEndsOn} />
        </div>
        <ToneField value={tone} onChange={setTone} />
        <CheckChips label={t("course.tracked")} options={TRACKS} values={followed} onChange={setTracks} />
        <p className="study-muted">
          {followed.length === 0
            ? t("course.tracked_none")
            : t("course.tracked_hint")}
        </p>
        <div className="study-pair">
          <TextField label={t("field.credits")} value={credits} onChange={setCredits} inputMode="decimal" placeholder="60" hint={t("course.credits_hint")} />
          <TextField label={t("field.hours")} value={hours} onChange={setHours} inputMode="decimal" placeholder="—" hint={t("course.hours_hint")} />
        </div>

        {!course && (
          <fieldset className="study-subject-rows">
            <legend className="text-field-label">{t("subjects.title")}</legend>
            <p className="study-muted">{t("course.subjects_hint")}</p>
            {subjects.map((row, index) => (
              <div key={row.key} className="study-subject-row">
                <TextField
                  label={t("course.subject_n", { n: index + 1 })}
                  value={row.name}
                  onChange={(value) => setRow(row.key, { name: value })}
                  placeholder={t("course.subject_placeholder")}
                  onSubmit={addRow}
                />
                <TextField
                  label={t("field.credits")}
                  value={row.credits}
                  onChange={(value) => setRow(row.key, { credits: value })}
                  inputMode="decimal"
                  placeholder="6"
                />
                <IconButton
                  icon="minus"
                  label={t("course.remove_subject", { n: index + 1 })}
                  variant="plain"
                  size="small"
                  onClick={() => setSubjects((rows) => rows.filter((one) => one.key !== row.key))}
                />
              </div>
            ))}
            <Button variant="plain" size="small" icon="plus" onClick={addRow}>
              {t("course.another_subject")}
            </Button>
          </fieldset>
        )}

        <Collapsible title={t("course.grade_section")} subtitle={t("course.scale_0_to", { max: scaleMax })}>
          <div className="study-form">
            <SegmentedControl
              label={t("field.scale")}
              options={[
                { value: "10", label: t("course.scale_10") },
                { value: "100", label: t("course.scale_100") },
              ]}
              value={scale}
              onChange={setScale}
            />
            <div className="study-pair">
              <TextField
                label={t("field.pass_mark")}
                value={passMark}
                onChange={setPassMark}
                inputMode="decimal"
                placeholder={scale === "100" ? "50" : "5"}
              />
              <TextField
                label={t("field.target")}
                value={target}
                onChange={setTarget}
                inputMode="decimal"
                placeholder="—"
                hint={t("course.target_hint")}
              />
            </div>
            <SegmentedControl label={t("field.modality")} options={MODALITIES} value={modality} onChange={setModality} />
            <TextField label={t("field.campus")} value={campus} onChange={setCampus} placeholder="campus.university.edu" />
            {(!course || course.status === "planned" || course.status === "active") && (
              <SegmentedControl
                label={t("field.status")}
                options={[
                  { value: "active", label: t("status.active") },
                  { value: "planned", label: t("status.planned") },
                ]}
                value={planned}
                onChange={setPlanned}
              />
            )}
          </div>
        </Collapsible>

        {problem && (
          <Hint tone="warning">
            {problem}
          </Hint>
        )}
      </div>
    </Sheet>
  );
}
