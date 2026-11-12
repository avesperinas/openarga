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
import { KINDS, MODALITIES, parseNumber } from "./words";

export function ToneField({ value, onChange }: { value: Tone; onChange: (tone: Tone) => void }) {
  return (
    <fieldset className="study-tones">
      <legend className="text-field-label">Color</legend>
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

const TRACKS: { value: Track; label: string }[] = [
  { value: "grades", label: "Notas" },
  { value: "progress", label: "Progreso" },
  { value: "attendance", label: "Asistencia" },
];

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
  const [credits, setCredits] = useState(course?.credits?.toString().replace(".", ",") ?? "");
  const [hours, setHours] = useState(course?.hours?.toString().replace(".", ",") ?? "");
  const [scale, setScale] = useState<"10" | "100">(course?.scale_max === 100 ? "100" : "10");
  const [passMark, setPassMark] = useState(course ? String(course.pass_mark).replace(".", ",") : "");
  const [target, setTarget] = useState(course?.target_grade?.toString().replace(".", ",") ?? "");
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
      setProblem("Ponle un nombre.");
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
      setProblem(error instanceof Error ? error.message : "No se pudo guardar.");
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
      title={course ? "Editar estudio" : "Nuevo estudio"}
      onClose={onClose}
      action={{ label: course ? "Guardar" : "Crear estudio", onClick: () => void save(), disabled: saving }}
    >
      <div className="study-form">
        <TextField label="Nombre" value={name} onChange={setName} placeholder="Máster en Ciencia de Datos" autoFocus={!course} />
        <ChoiceChips label="Qué es" options={KINDS} value={kind} onChange={setKind} />
        <TextField label="Centro" value={institution} onChange={setInstitution} placeholder="Universidad, escuela, plataforma" />
        <div className="study-pair">
          <DateField label="Empieza" value={startsOn} onChange={setStartsOn} />
          <DateField label="Termina" value={endsOn} onChange={setEndsOn} />
        </div>
        <ToneField value={tone} onChange={setTone} />
        <CheckChips label="Qué se sigue" options={TRACKS} values={followed} onChange={setTracks} />
        <p className="study-muted">
          {followed.length === 0
            ? "Nada: solo su horario, sus clases y sus apuntes. Para lo que se estudia sin un final fijo."
            : "Lo que no marques no se enseña en el estudio ni en el escritorio."}
        </p>
        <div className="study-pair">
          <TextField label="Créditos" value={credits} onChange={setCredits} inputMode="decimal" placeholder="60" hint="ECTS del total" />
          <TextField label="Horas" value={hours} onChange={setHours} inputMode="decimal" placeholder="—" hint="Si se mide en horas" />
        </div>

        {!course && (
          <fieldset className="study-subject-rows">
            <legend className="text-field-label">Asignaturas</legend>
            <p className="study-muted">Las que tenga. Un curso corto puede no tener ninguna.</p>
            {subjects.map((row, index) => (
              <div key={row.key} className="study-subject-row">
                <TextField
                  label={`Asignatura ${index + 1}`}
                  value={row.name}
                  onChange={(value) => setRow(row.key, { name: value })}
                  placeholder="Estadística"
                  onSubmit={addRow}
                />
                <TextField
                  label="Créditos"
                  value={row.credits}
                  onChange={(value) => setRow(row.key, { credits: value })}
                  inputMode="decimal"
                  placeholder="6"
                />
                <IconButton
                  icon="minus"
                  label={`Quitar asignatura ${index + 1}`}
                  variant="plain"
                  size="small"
                  onClick={() => setSubjects((rows) => rows.filter((one) => one.key !== row.key))}
                />
              </div>
            ))}
            <Button variant="plain" size="small" icon="plus" onClick={addRow}>
              Otra asignatura
            </Button>
          </fieldset>
        )}

        <Collapsible title="Nota, modalidad y campus" subtitle={`Escala de 0 a ${scaleMax}`}>
          <div className="study-form">
            <SegmentedControl
              label="Escala"
              options={[
                { value: "10", label: "De 0 a 10" },
                { value: "100", label: "De 0 a 100" },
              ]}
              value={scale}
              onChange={setScale}
            />
            <div className="study-pair">
              <TextField
                label="Aprobado"
                value={passMark}
                onChange={setPassMark}
                inputMode="decimal"
                placeholder={scale === "100" ? "50" : "5"}
              />
              <TextField
                label="Tu objetivo"
                value={target}
                onChange={setTarget}
                inputMode="decimal"
                placeholder="—"
                hint="Te dice qué necesitas para llegar"
              />
            </div>
            <SegmentedControl label="Modalidad" options={MODALITIES} value={modality} onChange={setModality} />
            <TextField label="Enlace al campus" value={campus} onChange={setCampus} placeholder="campus.universidad.es" />
            {(!course || course.status === "planned" || course.status === "active") && (
              <SegmentedControl
                label="Estado"
                options={[
                  { value: "active", label: "En curso" },
                  { value: "planned", label: "Planeado" },
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
