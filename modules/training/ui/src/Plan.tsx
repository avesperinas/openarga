import {
  Button,
  ChoiceChips,
  ConfirmDelete,
  EmptyState,
  Heading,
  Hint,
  Icon,
  IconButton,
  List,
  ListRow,
  Notice,
  Panes,
  Screen,
  Sheet,
  Skeleton,
  Stepper,
  TextField,
} from "@openarga/ui";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  type Catalogue,
  type CatalogueVariant,
  type DayInput,
  type DayKind,
  type Editor,
  type Implement,
  type Muscles,
  type Pattern,
  type Settings,
  type Version,
  createExercise,
  createPlan,
  createVariant,
  discardDraft,
  openDraft,
  publishDraft,
  readCatalogue,
  readPlan,
  readToday,
  saveDraft,
  updateMuscles,
} from "./api";
import {
  addDay,
  addOption,
  addSlot,
  moveDay,
  moveSlot,
  publishProblems,
  removeDay,
  removeOption,
  removeSlot,
  toInput,
  updateDay,
  updateSlot,
} from "./draft";
import { IMPLEMENTS, KINDS, PATTERNS, describeTarget, labelOf } from "./labels";
import { AppVersion } from "./AppVersion";
import { ScreenHeader } from "./Header";
import { MusclePicker, describeMuscles, hasPrimary } from "./Muscles";

type Loaded = { editor: Editor; catalogue: Catalogue; settings: Settings };

export interface PlanScreenProps {
  initial?: Loaded;
}

export function PlanScreen({ initial }: PlanScreenProps) {
  const [loaded, setLoaded] = useState<Loaded | null>(initial ?? null);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [editor, catalogue, today] = await Promise.all([readPlan(), readCatalogue(), readToday()]);
      setLoaded({ editor, catalogue, settings: today.settings });
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    if (!initial) void load();
  }, [initial, load]);

  const run = useCallback(
    async (action: () => Promise<Editor>) => {
      setNotice(null);
      try {
        const editor = await action();
        setLoaded((previous) => (previous ? { ...previous, editor } : previous));
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "No se ha podido guardar");
        void load();
      }
    },
    [load],
  );

  return (
    <Screen wide>
      <ScreenHeader title="Plan" />

      {notice && <Notice tone="negative">{notice}</Notice>}

      {!loaded ? (
        failed ? (
          <EmptyState title={"No se ha podido cargar el plan"}>Comprueba la conexión y vuelve a abrir la app.</EmptyState>
        ) : (
          <Skeleton rows={4} label="Cargando el plan" />
        )
      ) : !loaded.editor.plan ? (
        <CreatePlan onCreate={(name) => run(() => createPlan(name))} />
      ) : loaded.editor.draft ? (
        <DraftEditor
          key={loaded.editor.draft.id}
          editor={loaded.editor}
          draft={loaded.editor.draft}
          catalogue={loaded.catalogue}
          onCatalogue={(catalogue) => setLoaded({ ...loaded, catalogue })}
          onPublish={() => run(publishDraft)}
          onDiscard={() => run(discardDraft)}
          onError={(message) => setNotice(message)}
        />
      ) : (
        <PublishedPlan editor={loaded.editor} onEdit={() => run(openDraft)} />
      )}

      <AppVersion />
    </Screen>
  );
}

function CreatePlan({ onCreate }: { onCreate: (name: string) => Promise<void> }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!name.trim() || busy) return;
    setBusy(true);
    await onCreate(name.trim());
    setBusy(false);
  };
  return (
    <section className="surface training-card">
      <Heading>Crea tu plan</Heading>
      <Hint>
        Un plan son los días de tu ciclo —Push, Pull, Pierna…— con sus ejercicios. Training te propone
        cada día el siguiente de la secuencia.
      </Hint>
      <TextField label="Nombre del plan" value={name} onChange={setName} placeholder="Push Pull Leg" onSubmit={submit} />
      <Button variant="primary" block disabled={!name.trim() || busy} onClick={() => void submit()}>
        Crear plan
      </Button>
    </section>
  );
}

function PublishedPlan({ editor, onEdit }: { editor: Editor; onEdit: () => void }) {
  const version = editor.published;
  const since = version?.valid_from ? new Date(`${version.valid_from}T12:00:00`) : null;
  return (
    <Panes
      asideFirst
      asideLabel="El plan"
      main={version ? <DaysView version={version} /> : null}
      aside={
        <section className="surface training-card">
          <p className="training-eyebrow">
            {editor.plan?.name}
            {version ? ` · versión ${version.number}` : ""}
            {since ? ` · desde el ${since.toLocaleDateString("es-ES", { day: "numeric", month: "long" })}` : ""}
          </p>
          {!version && <Hint>El plan no tiene ninguna versión publicada.</Hint>}
          {version && editor.rotation_version !== null && editor.rotation_version !== version.number && (
            <Hint>
              La rotación en curso sigue con la versión {editor.rotation_version}. Esta entra en la siguiente.
            </Hint>
          )}
          <Button variant="primary" block icon="edit" onClick={onEdit}>
            Editar plan
          </Button>
        </section>
      }
    />
  );
}

function DaysView({ version }: { version: Version }) {
  return (
    <ol className="training-plan-days">
      {version.days.map((day, index) => (
        <li key={day.id} className="surface training-plan-day" data-kind={day.kind}>
          <div className="training-plan-day-head">
            <span className="training-plan-day-name">
              <span className="training-kind-dot" aria-hidden="true" />
              {day.name}
            </span>
            <span className="training-plan-day-detail">Día {index + 1}</span>
          </div>
          <ul className="training-plan-slots">
            {day.slots.map((slot) => (
              <li key={slot.id} className="training-plan-slot">
                <span className="training-plan-slot-name">
                  {[...slot.options]
                    .sort((a, b) => a.priority - b.priority)
                    .map((option) => option.name)
                    .join(" o ")}
                </span>
                <span className="training-plan-slot-detail">{describeTarget(slot)}</span>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}

type Editing =
  | { sheet: "day"; index: number | null }
  | { sheet: "slot"; day: number; slot: number }
  | { sheet: "pick"; day: number; slot: number | null }
  | { sheet: "muscles"; exercise: string; day: number; slot: number };

interface DraftEditorProps {
  editor: Editor;
  draft: Version;
  catalogue: Catalogue;
  onCatalogue: (catalogue: Catalogue) => void;
  onPublish: () => Promise<void>;
  onDiscard: () => Promise<void>;
  onError: (message: string) => void;
}

function DraftEditor({ editor, draft, catalogue, onCatalogue, onPublish, onDiscard, onError }: DraftEditorProps) {
  const [days, setDays] = useState<DayInput[]>(() => toInput(draft.days));
  const [editing, setEditing] = useState<Editing | null>(null);
  const [saving, setSaving] = useState<"idle" | "saving" | "saved">("idle");
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const latest = useRef(days);
  const queue = useRef<Promise<void>>(Promise.resolve());

  const names = useMemo(() => {
    const map = new Map<string, CatalogueVariant | { name: string }>();
    for (const day of draft.days) for (const slot of day.slots) for (const o of slot.options) map.set(o.variant_id, o);
    for (const exercise of catalogue.exercises) for (const variant of exercise.variants) map.set(variant.id, variant);
    return map;
  }, [catalogue, draft]);
  const nameOf = (id: string) => names.get(id)?.name ?? "Ejercicio";
  const exerciseOf = (variantId: string) =>
    catalogue.exercises.find((exercise) => exercise.variants.some((variant) => variant.id === variantId));
  const missingMuscles = (slot: DayInput["slots"][number]) =>
    slot.variant_ids.some((id) => {
      const exercise = exerciseOf(id);
      return exercise !== undefined && !hasPrimary(exercise.muscles);
    });
  const withoutMuscles = days.flatMap((day) => day.slots).filter(missingMuscles).length;

  function commit(next: DayInput[]) {
    latest.current = next;
    setDays(next);
    setSaving("saving");
    queue.current = queue.current.then(async () => {
      if (latest.current !== next) return;
      try {
        await saveDraft(next);
        if (latest.current === next) setSaving("saved");
      } catch (error) {
        onError(error instanceof Error ? error.message : "No se ha podido guardar el borrador");
        setSaving("idle");
      }
    });
  }

  const problems = publishProblems(days);
  const current = editing?.sheet === "slot" ? days[editing.day]?.slots[editing.slot] : undefined;

  return (
    <>
      <Panes
        asideFirst
        asideLabel="El borrador"
        main={
          <>
            <ol className="training-plan-days">
              {days.map((day, dayIndex) => (
                <li key={dayIndex} className="surface training-plan-day" data-kind={day.kind}>
                  <button
                    type="button"
                    className="training-plan-day-head training-pressable"
                    onClick={() => setEditing({ sheet: "day", index: dayIndex })}
                  >
                    <span className="training-plan-day-name">
                      <span className="training-kind-dot" aria-hidden="true" />
                      {day.name}
                    </span>
                    <span className="training-plan-day-detail">
                      Día {dayIndex + 1} · {labelOf(KINDS, day.kind)}
                    </span>
                  </button>
                  {day.slots.length === 0 ? (
                    <p className="training-plan-empty">Sin ejercicios todavía.</p>
                  ) : (
                    <ol className="training-plan-slots">
                      {day.slots.map((slot, slotIndex) => (
                        <li key={slotIndex}>
                          <button
                            type="button"
                            className="training-plan-slot training-pressable"
                            onClick={() => setEditing({ sheet: "slot", day: dayIndex, slot: slotIndex })}
                          >
                            <span className="training-plan-slot-name">{slot.variant_ids.map(nameOf).join(" o ")}</span>
                            <span className="training-plan-slot-detail">
                              {describeTarget(slot)}
                              {slot.allow_both ? " · las dos" : ""}
                              {missingMuscles(slot) && <span className="training-warning"> · faltan músculos</span>}
                            </span>
                            <Icon name="chevron-right" />
                          </button>
                        </li>
                      ))}
                    </ol>
                  )}
                  <div className="training-plan-day-actions">
                    <Button
                      variant="tinted"
                      size="small"
                      icon="plus"
                      onClick={() => setEditing({ sheet: "pick", day: dayIndex, slot: null })}
                    >
                      Añadir ejercicio
                    </Button>
                  </div>
                </li>
              ))}
            </ol>

            <Button variant="secondary" block icon="plus" onClick={() => setEditing({ sheet: "day", index: null })}>
              Añadir día
            </Button>
          </>
        }
        aside={
          <section className="surface training-card">
            <p className="training-eyebrow">
              {editor.plan?.name} · borrador de la versión {draft.number}
            </p>
            <Hint>
              Los cambios se guardan solos. Al publicar, lo ya entrenado sigue con su versión.
            </Hint>
            <p className="training-saving" role="status">
              {saving === "saving" ? "Guardando…" : saving === "saved" ? "Guardado" : ""}
            </p>
            {withoutMuscles > 0 && (
              <Hint tone="warning">
                {withoutMuscles === 1 ? "Un ejercicio no tiene" : `${withoutMuscles} ejercicios no tienen`} los
                músculos que trabaja. Tócalo para completarlos: sin ellos no hay estadísticas por grupo.
              </Hint>
            )}
            {problems.length > 0 && (
              <ul className="training-problems">
                {problems.map((problem) => (
                  <li key={problem}>{problem}</li>
                ))}
              </ul>
            )}
            <Button
              variant="primary"
              block
              disabled={problems.length > 0 || saving === "saving"}
              onClick={() => void queue.current.then(onPublish)}
            >
              Publicar versión {draft.number}
            </Button>
            <Button variant="plain" block onClick={() => setConfirmDiscard(true)}>
              Descartar cambios
            </Button>
          </section>
        }
      />
      {confirmDiscard && (
        <ConfirmDelete
          title="¿Descartar los cambios?"
          subject={`Borrador de la versión ${draft.number}`}
          consequence="Se pierde todo lo cambiado en el borrador. La versión publicada sigue como está."
          action="Descartar cambios"
          onCancel={() => setConfirmDiscard(false)}
          onConfirm={onDiscard}
        />
      )}

      {editing?.sheet === "day" && (
        <DaySheet
          day={editing.index === null ? null : (days[editing.index] ?? null)}
          position={editing.index}
          count={days.length}
          onClose={() => setEditing(null)}
          onSave={(name, kind) => {
            commit(
              editing.index === null ? addDay(days, name, kind) : updateDay(days, editing.index, { name, kind }),
            );
            setEditing(null);
          }}
          onMove={(direction) => {
            if (editing.index === null) return;
            commit(moveDay(days, editing.index, direction));
            setEditing({ sheet: "day", index: editing.index + direction });
          }}
          onRemove={() => {
            if (editing.index !== null) commit(removeDay(days, editing.index));
            setEditing(null);
          }}
        />
      )}

      {editing?.sheet === "slot" && current && (
        <SlotSheet
          slot={current}
          position={editing.slot}
          count={days[editing.day]?.slots.length ?? 0}
          nameOf={nameOf}
          musclesOf={(id) => {
            const exercise = exerciseOf(id);
            if (!exercise) return null;
            return {
              summary: hasPrimary(exercise.muscles) ? describeMuscles(exercise.muscles, catalogue) : null,
              edit: () => setEditing({ sheet: "muscles", exercise: exercise.id, day: editing.day, slot: editing.slot }),
            };
          }}
          onClose={() => setEditing(null)}
          onChange={(patch) => commit(updateSlot(days, editing.day, editing.slot, patch))}
          onAddOption={() => setEditing({ sheet: "pick", day: editing.day, slot: editing.slot })}
          onRemoveOption={(id) => commit(removeOption(days, editing.day, editing.slot, id))}
          onMove={(direction) => {
            commit(moveSlot(days, editing.day, editing.slot, direction));
            setEditing({ ...editing, slot: editing.slot + direction });
          }}
          onRemove={() => {
            commit(removeSlot(days, editing.day, editing.slot));
            setEditing(null);
          }}
        />
      )}

      {editing?.sheet === "muscles" && (
        <MusclesSheet
          catalogue={catalogue}
          exerciseId={editing.exercise}
          onClose={() => setEditing({ sheet: "slot", day: editing.day, slot: editing.slot })}
          onSaved={(exercise) => {
            onCatalogue({
              ...catalogue,
              exercises: catalogue.exercises.map((other) => (other.id === exercise.id ? exercise : other)),
            });
            setEditing({ sheet: "slot", day: editing.day, slot: editing.slot });
          }}
        />
      )}

      {editing?.sheet === "pick" && (
        <PickerSheet
          catalogue={catalogue}
          title={editing.slot === null ? `Añadir a ${days[editing.day]?.name ?? "el día"}` : "Añadir alternativa"}
          exclude={editing.slot === null ? [] : (days[editing.day]?.slots[editing.slot]?.variant_ids ?? [])}
          onCatalogue={onCatalogue}
          onClose={() => setEditing(editing.slot === null ? null : { sheet: "slot", day: editing.day, slot: editing.slot })}
          onPick={(variantId) => {
            if (editing.slot === null) {
              commit(addSlot(days, editing.day, variantId));
              setEditing(null);
            } else {
              commit(addOption(days, editing.day, editing.slot, variantId));
              setEditing({ sheet: "slot", day: editing.day, slot: editing.slot });
            }
          }}
        />
      )}
    </>
  );
}

interface DaySheetProps {
  day: DayInput | null;
  position: number | null;
  count: number;
  onClose: () => void;
  onSave: (name: string, kind: DayKind) => void;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
}

function DaySheet({ day, position, count, onClose, onSave, onMove, onRemove }: DaySheetProps) {
  const [name, setName] = useState(day?.name ?? "");
  const [kind, setKind] = useState<DayKind>(day?.kind ?? "push");
  const [confirm, setConfirm] = useState(false);
  const valid = name.trim().length > 0;
  if (confirm && day) {
    const exercises = day.slots.length;
    return (
      <ConfirmDelete
        title="¿Quitar este día?"
        subject={day.name}
        consequence={
          exercises > 0
            ? `Se quitan del borrador sus ${exercises} ${exercises === 1 ? "ejercicio" : "ejercicios"}. Lo ya entrenado no cambia.`
            : "Se quita del borrador. Lo ya entrenado no cambia."
        }
        action="Quitar día"
        onCancel={() => setConfirm(false)}
        onConfirm={onRemove}
      />
    );
  }
  return (
    <Sheet
      title={day ? "Editar día" : "Nuevo día"}
      onClose={onClose}
      action={{ label: day ? "Guardar" : "Añadir día", onClick: () => valid && onSave(name, kind), disabled: !valid }}
    >
      <TextField label="Nombre" value={name} onChange={setName} placeholder="Push" autoFocus={!day} onSubmit={() => valid && onSave(name, kind)} />
      <div className="training-field">
        <span className="training-field-label">Tipo</span>
        <ChoiceChips label="Tipo" value={kind} onChange={setKind} options={KINDS} />
      </div>
      {day && position !== null && (
        <div className="training-sheet-row">
          <Button size="small" icon="chevron-up" disabled={position === 0} onClick={() => onMove(-1)}>
            Antes
          </Button>
          <Button size="small" icon="chevron-down" disabled={position >= count - 1} onClick={() => onMove(1)}>
            Después
          </Button>
          <Button size="small" variant="destructive" icon="trash" onClick={() => setConfirm(true)}>
            Quitar
          </Button>
        </div>
      )}
    </Sheet>
  );
}

interface SlotSheetProps {
  slot: DayInput["slots"][number];
  position: number;
  count: number;
  nameOf: (id: string) => string;
  musclesOf: (variantId: string) => { summary: string | null; edit: () => void } | null;
  onClose: () => void;
  onChange: (patch: Partial<DayInput["slots"][number]>) => void;
  onAddOption: () => void;
  onRemoveOption: (variantId: string) => void;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
}

function SlotSheet({
  slot,
  position,
  count,
  nameOf,
  musclesOf,
  onClose,
  onChange,
  onAddOption,
  onRemoveOption,
  onMove,
  onRemove,
}: SlotSheetProps) {
  const [asking, setAsking] = useState<{ option: string | null } | null>(null);
  if (asking) {
    const option = asking.option;
    return (
      <ConfirmDelete
        title={option === null ? "¿Quitar este ejercicio del día?" : "¿Quitar esta alternativa?"}
        subject={nameOf(option ?? slot.variant_ids[0] ?? "")}
        consequence={
          option === null
            ? "Se quita del borrador con sus alternativas. Lo ya entrenado no cambia."
            : "Se quita del borrador. Lo ya entrenado no cambia."
        }
        action={option === null ? "Quitar ejercicio" : "Quitar alternativa"}
        onCancel={() => setAsking(null)}
        onConfirm={() => {
          setAsking(null);
          if (option === null) onRemove();
          else onRemoveOption(option);
        }}
      />
    );
  }
  return (
    <Sheet title={nameOf(slot.variant_ids[0] ?? "")} onClose={onClose} action={{ label: "Hecho", onClick: onClose }}>
      <div className="training-field-grid">
        <div className="training-field">
          <span className="training-field-label">Series</span>
          <Stepper label="Series" value={slot.target_sets} step={1} min={1} max={20} inputMode="numeric" onChange={(v) => v && onChange({ target_sets: v })} />
        </div>
        <div className="training-field">
          <span className="training-field-label">Reps mínimas</span>
          <Stepper label="Reps mínimas" value={slot.rep_min} step={1} min={1} max={100} inputMode="numeric" onChange={(v) => v && onChange({ rep_min: v })} />
        </div>
        <div className="training-field">
          <span className="training-field-label">Reps máximas</span>
          <Stepper label="Reps máximas" value={slot.rep_max} step={1} min={1} max={100} inputMode="numeric" onChange={(v) => v && onChange({ rep_max: v })} />
        </div>
      </div>

      <div className="training-field">
        <span className="training-field-label">Variantes</span>
        <p className="training-field-hint">La primera es la que se propone si nunca has hecho ninguna.</p>
        <ul className="training-options">
          {slot.variant_ids.map((id) => {
            const muscles = musclesOf(id);
            return (
              <li key={id} className="training-option training-option-stacked">
                <span className="training-option-text">
                  <span>{nameOf(id)}</span>
                  {muscles && (
                    <button type="button" className="training-option-muscles training-pressable" onClick={muscles.edit}>
                      {muscles.summary ?? <span className="training-warning">Faltan los músculos · completar</span>}
                    </button>
                  )}
                </span>
                {slot.variant_ids.length > 1 && (
                  <IconButton icon="close" label={`Quitar ${nameOf(id)}`} size="small" variant="plain" onClick={() => setAsking({ option: id })} />
                )}
              </li>
            );
          })}
        </ul>
        <Button variant="tinted" size="small" icon="plus" onClick={onAddOption}>
          Añadir alternativa
        </Button>
      </div>

      {slot.variant_ids.length > 1 && (
        <div className="training-field">
          <span className="training-field-label">En una sesión</span>
          <ChoiceChips
            label="En una sesión"
            value={slot.allow_both ? "both" : "one"}
            onChange={(value) => onChange({ allow_both: value === "both" })}
            options={[
              { value: "one", label: "Solo una" },
              { value: "both", label: "Pueden ir las dos" },
            ]}
          />
        </div>
      )}

      <div className="training-sheet-row">
        <Button size="small" icon="chevron-up" disabled={position === 0} onClick={() => onMove(-1)}>
          Antes
        </Button>
        <Button size="small" icon="chevron-down" disabled={position >= count - 1} onClick={() => onMove(1)}>
          Después
        </Button>
        <Button size="small" variant="destructive" icon="trash" onClick={() => setAsking({ option: null })}>
          Quitar
        </Button>
      </div>
    </Sheet>
  );
}

export const normalize = (text: string) =>
  text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();

interface PickerSheetProps {
  catalogue: Catalogue;
  title: string;
  exclude: string[];
  onCatalogue: (catalogue: Catalogue) => void;
  onClose: () => void;
  onPick: (variantId: string) => void;
}

function PickerSheet({ catalogue, title, exclude, onCatalogue, onClose, onPick }: PickerSheetProps) {
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(catalogue.exercises.length === 0);

  if (creating) {
    return (
      <CreateExerciseSheet
        catalogue={catalogue}
        initialName={query}
        onClose={onClose}
        onBack={catalogue.exercises.length > 0 ? () => setCreating(false) : undefined}
        onCreated={async (variantId) => {
          onCatalogue(await readCatalogue());
          onPick(variantId);
        }}
      />
    );
  }

  const needle = normalize(query);
  const matches = catalogue.exercises
    .map((exercise) => ({
      exercise,
      variants: exercise.variants.filter(
        (variant) =>
          !exclude.includes(variant.id) &&
          (!needle || normalize(exercise.name).includes(needle) || normalize(variant.name).includes(needle)),
      ),
    }))
    .filter((entry) => entry.variants.length > 0);

  return (
    <Sheet title={title} onClose={onClose}>
      <TextField label="Buscar" type="search" value={query} onChange={setQuery} placeholder="Press, remo, sentadilla…" />
      <Button variant="tinted" icon="plus" block onClick={() => setCreating(true)}>
        {query.trim() ? `Crear «${query.trim()}»` : "Crear ejercicio nuevo"}
      </Button>
      {matches.length === 0 ? (
        <Hint>Nada con ese nombre. Créalo con el botón de arriba.</Hint>
      ) : (
        matches.map(({ exercise, variants }) => (
          <div key={exercise.id} className="training-field">
            <span className="training-field-label">{exercise.name}</span>
            <List>
              {variants.map((variant) => (
                <ListRow
                  key={variant.id}
                  title={variant.name}
                  detail={labelOf(IMPLEMENTS, variant.implement)}
                  accessory="plus"
                  onClick={() => onPick(variant.id)}
                />
              ))}
            </List>
          </div>
        ))
      )}
    </Sheet>
  );
}

interface CreateExerciseSheetProps {
  catalogue: Catalogue;
  initialName: string;
  onClose: () => void;
  onBack?: () => void;
  onCreated: (variantId: string) => Promise<void>;
}

export const defaultVariantName = (exercise: string, implement: Implement) =>
  `${exercise.trim()} (${labelOf(IMPLEMENTS, implement).toLowerCase()})`;

function CreateExerciseSheet({ catalogue, initialName, onClose, onBack, onCreated }: CreateExerciseSheetProps) {
  const [name, setName] = useState(initialName);
  const [variant, setVariant] = useState("");
  const [implement, setImplement] = useState<Implement>("barbell");
  const [pattern, setPattern] = useState<Pattern>("horizontal_push");
  const [muscles, setMuscles] = useState<Muscles>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const existing = catalogue.exercises.find((exercise) => normalize(exercise.name) === normalize(name));
  const valid = name.trim().length > 0 && !busy && (existing !== undefined || hasPrimary(muscles));

  async function submit() {
    if (!valid) return;
    setBusy(true);
    setError(null);
    const body = { name: variant.trim() || defaultVariantName(name, implement), implement };
    try {
      const variantId = existing
        ? (await createVariant(existing.id, body)).id
        : (await createExercise({ name: name.trim(), pattern, muscles, variant: body })).variants[0]!.id;
      await onCreated(variantId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se ha podido crear");
      setBusy(false);
    }
  }

  return (
    <Sheet
      title="Nuevo ejercicio"
      onClose={onClose}
      action={{ label: existing ? "Añadir variante" : "Crear y añadir", onClick: () => void submit(), disabled: !valid }}
    >
      {onBack && (
        <Button variant="plain" size="small" icon="chevron-left" onClick={onBack}>
          Volver a la lista
        </Button>
      )}
      <TextField
        label="Ejercicio"
        value={name}
        onChange={setName}
        placeholder="Press banca"
        autoFocus
        hint={existing ? `Ya existe: se añade como otra variante de «${existing.name}».` : undefined}
      />
      <div className="training-field">
        <span className="training-field-label">Implemento</span>
        <ChoiceChips label="Implemento" value={implement} onChange={setImplement} options={IMPLEMENTS} />
      </div>
      <TextField
        label="Nombre de la variante"
        value={variant}
        onChange={setVariant}
        placeholder={name.trim() ? defaultVariantName(name, implement) : "Press banca (barra)"}
        hint="La carga solo se compara dentro de la misma variante, y en el mismo centro."
      />
      {!existing && (
        <div className="training-field">
          <span className="training-field-label">Patrón</span>
          <ChoiceChips label="Patrón" value={pattern} onChange={setPattern} options={PATTERNS} />
        </div>
      )}
      {!existing && <MusclePicker catalogue={catalogue} value={muscles} onChange={setMuscles} />}
      {!existing && name.trim() && !hasPrimary(muscles) && (
        <p className="training-field-hint">Marca al menos un músculo principal para crearlo.</p>
      )}
      {error && (
        <p className="training-field-error" role="alert">
          {error}
        </p>
      )}
    </Sheet>
  );
}

interface MusclesSheetProps {
  catalogue: Catalogue;
  exerciseId: string;
  onClose: () => void;
  onSaved: (exercise: Catalogue["exercises"][number]) => void;
}

function MusclesSheet({ catalogue, exerciseId, onClose, onSaved }: MusclesSheetProps) {
  const exercise = catalogue.exercises.find((candidate) => candidate.id === exerciseId);
  const [muscles, setMuscles] = useState<Record<string, number>>(exercise?.muscles ?? {});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = hasPrimary(muscles) && !busy;

  async function save() {
    if (!valid) return;
    setBusy(true);
    try {
      onSaved(await updateMuscles(exerciseId, muscles as Muscles));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se ha podido guardar");
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={exercise ? `Músculos · ${exercise.name}` : "Músculos"}
      onClose={onClose}
      action={{ label: "Guardar", onClick: () => void save(), disabled: !valid }}
    >
      <p className="training-field-hint">Vale para todas las variantes de este ejercicio.</p>
      <MusclePicker catalogue={catalogue} value={muscles} onChange={setMuscles} />
      {error && (
        <p className="training-field-error" role="alert">
          {error}
        </p>
      )}
    </Sheet>
  );
}
