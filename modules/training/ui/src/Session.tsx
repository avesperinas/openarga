import {
  AppBar,
  Badge,
  Button,
  Delta,
  DisclosureList,
  DisclosureRow,
  Inline,
  List,
  ListRow,
  ProgressRing,
  Sequence,
  SequenceHint,
  SequenceRow,
  SequenceSeparator,
  ChoiceChips,
  ConfirmButton,
  ConfirmDelete,
  Elapsed,
  EmptyState,
  Hint,
  Notice,
  Screen,
  Sheet,
  Skeleton,
  Stepper,
  SyncMark,
  TextField,
} from "@openarga/ui";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { OutcomeCard } from "./Outcome";
import { WorkoutPulseCard } from "./Pulse";
import {
  type LastTime,
  type LoggedSet,
  type Outcome,
  type Session,
  type SessionExercise,
  type Slot,
  changeTimes,
  deleteSession,
  readOutcome,
} from "./api";
import { keptSession, readSessionKept } from "./offline";
import { type Comparison, compare } from "./outcome";
import {
  type Draft,
  byPriority,
  describeSet,
  describeSets,
  isBodyweight,
  kg,
  preferredVariant,
  prefill,
  shortDay,
  unusualLoad,
} from "./prefill";
import type { SyncQueue, SyncState } from "./queue";
import { completedSets, madridTime, overlay, remap, restSince, sessionTimes, upsertSet } from "./session";
import { useLongPress, useWakeLock } from "./hooks";
import { formatDuration, longDate } from "./labels";

type Load = { status: "loading" } | { status: "error" } | { status: "ready"; session: Session };

export interface SessionScreenProps {
  id: string;
  queue: SyncQueue;
  onExit: () => void;
  initial?: Session;
  initialOutcome?: Outcome;
  newId?: () => string;
}

export function SessionScreen({
  id,
  queue,
  onExit,
  initial,
  initialOutcome,
  newId = () => crypto.randomUUID(),
}: SessionScreenProps) {
  const [start] = useState(() => initial ?? keptSession(id));
  const [load, setLoad] = useState<Load>(start ? { status: "ready", session: start } : { status: "loading" });
  const [exercises, setExercises] = useState<SessionExercise[]>(() =>
    start ? overlay(start, queue.pending(id)) : [],
  );
  const current = useRef(exercises);
  const [open, setOpen] = useState<string | null>(() => (start ? firstOpenSlot(start, current.current) : null));
  const [variants, setVariants] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [armed, setArmed] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editingTimes, setEditingTimes] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(initialOutcome ?? null);
  const [pair, setPairState] = useState<string[] | null>(() => readPair(id));
  const setPair = useCallback(
    (next: string[] | null) => {
      setPairState(next);
      writePair(id, next);
    },
    [id],
  );
  useSyncExternalStore(queue.subscribe, queue.snapshot, queue.snapshot);

  const commit = useCallback((next: SessionExercise[]) => {
    current.current = next;
    setExercises(next);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const session = await readSessionKept(id);
      const next = overlay(session, queue.pending(id));
      commit(next);
      setLoad({ status: "ready", session });
      setOpen((previous) => previous ?? firstOpenSlot(session, next));
    } catch {
      setLoad((previous) => (previous.status === "ready" ? previous : { status: "error" }));
    }
  }, [id, queue, commit]);

  useEffect(() => {
    if (!initial) void refresh();
    void queue.flush();
  }, [initial, refresh, queue]);

  useEffect(
    () =>
      queue.listen((event) => {
        if (event.type === "remapped") {
          commit(remap(current.current, event.from, event.to));
          return;
        }
        if (event.type === "signed-out") return;
        if (event.op.session !== id) return;
        setNotice(`No se ha guardado: ${event.detail || `el servidor respondió ${event.status}`}`);
        setFinishing(false);
        void refresh();
      }),
    [queue, id, commit, refresh],
  );

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!queue.hasPending()) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [queue]);

  const session = load.status === "ready" ? load.session : null;
  useWakeLock(session !== null && session.ended_at === null);

  const pending = queue.pending(id);
  useEffect(() => {
    if (!finishing || pending.length > 0) return;
    setFinishing(false);
    void refresh();
  }, [finishing, pending.length, refresh]);

  const ended = session?.ended_at ?? null;
  useEffect(() => {
    if (!ended || initialOutcome) return;
    let live = true;
    readOutcome(id)
      .then((found) => live && setOutcome(found))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [id, ended, initialOutcome]);

  useEffect(() => {
    if (!armed) return;
    const timer = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(timer);
  }, [armed]);

  if (!session) {
    return (
      <Screen>
        <AppBar title="Sesión" back={{ icon: "chevron-left", label: "Hoy", onClick: onExit }} />
        {load.status === "error" ? (
          <EmptyState title={"No se ha podido abrir la sesión"}>Comprueba la conexión y vuelve a intentarlo.</EmptyState>
        ) : (
          <Skeleton rows={3} label="Abriendo la sesión" />
        )}
      </Screen>
    );
  }

  const variantOf = (slot: Slot) => variants[slot.id] ?? preferredVariant(slot, session.history, exercises);

  function ensureExercise(slot: Slot, variantId: string): { next: SessionExercise[]; exercise: SessionExercise } {
    const option = slot.options.find((candidate) => candidate.variant_id === variantId);
    let next = current.current;
    let exercise = next.find((candidate) => candidate.plan_slot_id === slot.id && candidate.variant_id === variantId);
    if (!exercise) {
      exercise = {
        id: newId(),
        plan_slot_id: slot.id,
        variant_id: variantId,
        variant: option?.name ?? "",
        position: Math.max(0, ...next.map((candidate) => candidate.position)) + 1,
        sets: [],
      };
      next = [...next, exercise];
      queue.enqueue({
        key: `exercise:${exercise.id}`,
        session: id,
        method: "PUT",
        path: `/sessions/${id}/exercises/${exercise.id}`,
        body: { variant_id: variantId, plan_slot_id: slot.id },
      });
    }
    return { next, exercise };
  }

  function saveNote(slot: Slot, variantId: string, notes: string) {
    const { next, exercise } = ensureExercise(slot, variantId);
    const value = notes.trim() || null;
    commit(next.map((candidate) => (candidate.id === exercise.id ? { ...candidate, notes: value } : candidate)));
    queue.enqueue({
      key: `notes:${exercise.id}`,
      session: id,
      method: "PUT",
      path: `/sessions/${id}/exercises/${exercise.id}/notes`,
      body: { notes: value },
    });
  }

  function confirm(slot: Slot, variantId: string, number: number, draft: Draft, correction?: LoggedSet) {
    const option = slot.options.find((candidate) => candidate.variant_id === variantId);
    const ensured = ensureExercise(slot, variantId);
    let next = ensured.next;
    const exercise = ensured.exercise;

    const bodyweight = isBodyweight(option);
    const set: LoggedSet = {
      number,
      reps: draft.reps,
      weight: bodyweight ? null : draft.load,
      added_load: bodyweight ? draft.load || null : null,
      completed: true,
      confirmed_at: correction?.confirmed_at ?? new Date().toISOString(),
    };
    next = upsertSet(next, exercise.id, set);
    commit(next);
    queue.enqueue({
      key: `set:${exercise.id}:${number}`,
      session: id,
      method: "PUT",
      path: `/sessions/${id}/exercises/${exercise.id}/sets/${number}`,
      body: {
        reps: set.reps,
        weight: set.weight,
        added_load: set.added_load,
        completed: set.completed,
        confirmed_at: set.confirmed_at,
      },
    });

    if (correction) return;
    const after = slotAfter(session!, next, slot.id, pair);
    if (after) setOpen(after);
  }

  function finish() {
    if (!armed) {
      setArmed(true);
      return;
    }
    setArmed(false);
    setFinishing(true);
    queue.enqueue({
      key: `finish:${id}`,
      session: id,
      method: "POST",
      path: `/sessions/${id}/finish`,
      body: { ended_at: new Date().toISOString() },
    });
  }

  const unsent = pending.filter((op) => op.key.startsWith("set:")).length;
  const offline = pending.some((op) => op.attempts > 0);
  const subtitle = [
    session.ended_at ? longDate(session.day) : `Rotación ${session.rotation_number}`,
    unsent > 0 ? `${unsent} sin enviar` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="training-session" data-kind={session.kind}>
      <AppBar
        title={session.day_name}
        subtitle={subtitle}
        back={{ icon: "chevron-left", label: "Hoy", onClick: onExit }}
        action={
          session.ended_at
            ? undefined
            : { label: finishing ? "Terminando…" : armed ? "¿Terminar?" : "Terminar", onClick: finish, disabled: finishing }
        }
      />

      <main className="training-session-body">
        {notice && (
          <Notice tone="negative">{notice}</Notice>
        )}
        {finishing && offline && (
          <Notice>Sin conexión. La sesión se termina sola en cuanto vuelva.</Notice>
        )}

        {session.ended_at && <OutcomeCard session={session} exercises={exercises} outcome={outcome} />}

        <DisclosureList label="Ejercicios">
          {session.slots.map((slot) => {
            const variantId = variantOf(slot);
            const partnerId = pair?.includes(slot.id) ? pair.find((other) => other !== slot.id) : undefined;
            const done = exercises.filter((exercise) => exercise.plan_slot_id === slot.id && exercise.sets.length > 0);
            const used = done[0];
            const option = slot.options.find((candidate) => candidate.variant_id === used?.variant_id);
            return (
              <ExerciseRow
                key={slot.id}
                slot={slot}
                variantId={variantId}
                exercises={exercises.filter((exercise) => exercise.plan_slot_id === slot.id)}
                last={session.history.find((entry) => entry.variant_id === variantId)}
                comparison={
                  session.ended_at && used
                    ? compare(
                        used.sets,
                        session.history.find((entry) => entry.variant_id === used.variant_id),
                        isBodyweight(option),
                        session.day,
                      )
                    : null
                }
                record={outcome?.records.some((found) => done.some((exercise) => exercise.variant_id === found.variant_id))}
                gymId={session.gym_id}
                open={open === slot.id}
                queue={queue}
                running={session.ended_at === null}
                partner={session.slots.find((other) => other.id === partnerId) ?? null}
                others={session.slots.filter((other) => other.id !== slot.id)}
                onToggle={() => setOpen(open === slot.id ? null : slot.id)}
                onPair={(other) => setPair(other ? [slot.id, other] : null)}
                onVariant={(variant) => setVariants({ ...variants, [slot.id]: variant })}
                onNote={(notes) => variantId && saveNote(slot, variantId, notes)}
                onConfirm={(number, draft, correction) =>
                  variantId && confirm(slot, variantId, number, draft, correction)
                }
              />
            );
          })}
        </DisclosureList>

        {session.ended_at && <WorkoutPulseCard id={`training:session:${session.id}`} start={session.started_at} />}

        <Button variant="plain" icon="trash" block onClick={() => setDeleting(true)}>
          Borrar entreno
        </Button>
      </main>

      {deleting && (
        <DeleteSessionSheet
          title={`${session.day_name} · ${longDate(session.day)}`}
          sets={exercises.reduce((total, exercise) => total + exercise.sets.length, 0)}
          onCancel={() => setDeleting(false)}
          onDelete={async (withSets) => {
            await deleteSession(id, withSets);
            queue.forget(id);
            onExit();
          }}
        />
      )}

      {editingTimes && session.ended_at && (
        <TimesSheet
          day={session.day}
          startedAt={session.started_at}
          endedAt={session.ended_at}
          onCancel={() => setEditingTimes(false)}
          onSave={async (times) => {
            const saved = await changeTimes(id, times);
            setLoad({ status: "ready", session: saved });
            setEditingTimes(false);
          }}
        />
      )}

      {session.ended_at ? (
        <footer className="glass training-timers">
          <p className="elapsed">
            <span className="elapsed-label">Duración</span>
            <span className="elapsed-value">{formatDuration(session.duration_seconds)}</span>
          </p>
          <Button
            variant="secondary"
            size="small"
            icon="edit"
            aria-label={`Cambiar horas: de ${madridTime(session.started_at)} a ${madridTime(session.ended_at)}`}
            onClick={() => setEditingTimes(true)}
          >
            {`${madridTime(session.started_at)} – ${madridTime(session.ended_at)}`}
          </Button>
        </footer>
      ) : (
        <footer className="glass training-timers">
          <Elapsed since={restSince(exercises)} label="Descanso" size="large" />
          <Elapsed since={session.started_at} label="Sesión" />
        </footer>
      )}
    </div>
  );
}

export function slotAfter(
  session: Session,
  exercises: SessionExercise[],
  slot: string,
  pair: string[] | null,
): string | null {
  const partner = pair?.includes(slot) ? pair.find((other) => other !== slot) : undefined;
  const partnerSlot = session.slots.find((candidate) => candidate.id === partner);
  if (partnerSlot && completedSets(exercises, partnerSlot.id) < partnerSlot.target_sets) return partnerSlot.id;
  const own = session.slots.find((candidate) => candidate.id === slot);
  if (own && completedSets(exercises, slot) >= own.target_sets) return firstOpenSlot(session, exercises, slot) ?? slot;
  return null;
}

function firstOpenSlot(session: Session, exercises: SessionExercise[], after?: string): string | null {
  const start = after ? session.slots.findIndex((slot) => slot.id === after) + 1 : 0;
  const ordered = [...session.slots.slice(start), ...session.slots.slice(0, start)];
  return ordered.find((slot) => completedSets(exercises, slot.id) < slot.target_sets)?.id ?? null;
}

function worst(states: SyncState[]): SyncState {
  if (states.includes("pending")) return "pending";
  if (states.includes("sending")) return "sending";
  return "saved";
}

const SYNC_WORD: Record<SyncState, string> = { saved: "guardada", sending: "enviando", pending: "pendiente" };

const PAIR_KEY = (session: string) => `training:superserie:${session}`;

function readPair(session: string): string[] | null {
  try {
    const stored = window.sessionStorage.getItem(PAIR_KEY(session));
    const value: unknown = stored ? JSON.parse(stored) : null;
    return Array.isArray(value) && value.length === 2 ? value.map(String) : null;
  } catch {
    return null;
  }
}

function writePair(session: string, pair: string[] | null): void {
  try {
    if (pair) window.sessionStorage.setItem(PAIR_KEY(session), JSON.stringify(pair));
    else window.sessionStorage.removeItem(PAIR_KEY(session));
  } catch {
  }
}

interface ExerciseRowProps {
  slot: Slot;
  variantId: string | undefined;
  exercises: SessionExercise[];
  last: LastTime | undefined;
  gymId: string | null;
  open: boolean;
  queue: SyncQueue;
  running: boolean;
  partner: Slot | null;
  others: Slot[];
  onToggle: () => void;
  onPair: (other: string | null) => void;
  onVariant: (variantId: string) => void;
  onConfirm: (number: number, draft: Draft, correction?: LoggedSet) => void;
  onNote: (notes: string) => void;
  comparison?: Comparison | null;
  record?: boolean;
}

function ExerciseRow({
  slot,
  variantId,
  exercises,
  last,
  gymId,
  open,
  queue,
  running,
  partner,
  others,
  onToggle,
  onPair,
  onVariant,
  onConfirm,
  onNote,
  comparison = null,
  record = false,
}: ExerciseRowProps) {
  const [pairing, setPairing] = useState(false);
  const options = byPriority(slot);
  const option = options.find((candidate) => candidate.variant_id === variantId);
  const bodyweight = isBodyweight(option);
  const exercise = exercises.find((candidate) => candidate.variant_id === variantId);
  const done = completedSets(exercises, slot.id);
  const keys = exercises.flatMap((candidate) => [
    `exercise:${candidate.id}`,
    ...candidate.sets.map((set) => `set:${candidate.id}:${set.number}`),
  ]);
  const state = worst(keys.map((key) => queue.stateOf(key)));
  const locked = !slot.allow_both
    ? exercises.find((candidate) => candidate.sets.length > 0)?.variant_id
    : undefined;

  const doneText = exercises
    .filter((candidate) => candidate.sets.length > 0)
    .map((candidate) => {
      const own = slot.options.find((o) => o.variant_id === candidate.variant_id);
      const text = describeSets(candidate.sets, isBodyweight(own));
      return exercises.length > 1 ? `${candidate.variant}: ${text}` : text;
    })
    .join(" · ");
  const lastText = last
    ? `${describeSets(last.sets, bodyweight)}${
        last.gym && (last.gym_id ?? null) !== gymId ? ` en ${last.gym}` : ""
      }`
    : "primera vez";

  return (
    <>
      <DisclosureRow
        title={slot.exercise}
        tag={partner ? "superserie" : undefined}
        subtitle={done > 0 ? doneText : `${slot.target_sets} × ${slot.rep_min}–${slot.rep_max} · ${lastText}`}
        leading={<ProgressRing done={done} target={slot.target_sets} />}
        trailing={
          <>
            {done > 0 && state !== "saved" && <SyncMark state={state} />}
            {comparison && record && <Badge tone="positive">Récord</Badge>}
            {comparison && (
              <Delta
                text={comparison.text}
                direction={comparison.direction}
                label={
                  comparison.direction === "first"
                    ? "Primera vez"
                    : `Mejor serie contra la última vez: ${comparison.text}${record ? ", récord" : ""}`
                }
              />
            )}
          </>
        }
        open={open}
        onToggle={onToggle}
      >
        {variantId && (
          <>
          {options.length > 1 && (
            <ChoiceChips
              label="Variante"
              value={variantId}
              onChange={onVariant}
              options={options.map((candidate) => ({
                value: candidate.variant_id,
                label: candidate.name,
                disabled: locked !== undefined && locked !== candidate.variant_id,
              }))}
            />
          )}
          <Hint>
            {last
              ? `La última vez, ${shortDay(last.day)}${
                  last.gym && (last.gym_id ?? null) !== gymId ? ` en ${last.gym}` : ""
                }: ${describeSets(last.sets, bodyweight)}`
              : "Primera vez con esta variante"}
          </Hint>
          <SetRows
            key={variantId}
            slot={slot}
            option={option}
            exerciseId={exercise?.id}
            sets={exercise?.sets ?? []}
            last={last}
            gymId={gymId}
            queue={queue}
            running={running}
            onConfirm={onConfirm}
          />
          <Inline>
            {running &&
              (partner ? (
                <Button variant="plain" size="small" icon="close" onClick={() => onPair(null)}>
                  {`Superserie con ${partner.exercise}`}
                </Button>
              ) : (
                others.length > 0 && (
                  <Button variant="plain" size="small" icon="repeat" onClick={() => setPairing(true)}>
                    Superserie
                  </Button>
                )
              ))}
            <ExerciseNote key={`nota-${variantId}`} value={exercise?.notes ?? ""} onSave={onNote} folded />
          </Inline>
          </>
        )}
      </DisclosureRow>

      {pairing && (
        <Sheet title={`Superserie con ${slot.exercise}`} onClose={() => setPairing(false)}>
          <Hint>Después de cada serie se abre el otro ejercicio, mientras le queden series.</Hint>
          <List>
            {others.map((other) => (
              <ListRow
                key={other.id}
                title={other.exercise}
                subtitle={`${other.target_sets} × ${other.rep_min}–${other.rep_max}`}
                onClick={() => {
                  onPair(other.id);
                  setPairing(false);
                }}
              />
            ))}
          </List>
        </Sheet>
      )}
    </>
  );
}

interface SetListProps {
  slot: Slot;
  option: Slot["options"][number] | undefined;
  exerciseId: string | undefined;
  sets: LoggedSet[];
  last: LastTime | undefined;
  gymId: string | null;
  queue: SyncQueue;
  running: boolean;
  onConfirm: (number: number, draft: Draft, correction?: LoggedSet) => void;
}

function SetRows({ slot, option, exerciseId, sets, last, gymId, queue, running, onConfirm }: SetListProps) {
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [editing, setEditing] = useState<number | null>(null);
  const [extra, setExtra] = useState(0);
  const bodyweight = isBodyweight(option);

  const logged = new Map(sets.map((set) => [set.number, set]));
  const highest = Math.max(0, ...sets.map((set) => set.number));
  const count = Math.max(slot.target_sets, highest) + extra;
  const numbers = Array.from({ length: count }, (_, index) => index + 1);
  const active = running ? numbers.find((number) => !logged.has(number)) : undefined;

  const draftFor = (number: number): Draft => {
    if (drafts[number]) return drafts[number];
    const set = logged.get(number);
    if (set) return { load: bodyweight ? (set.added_load ?? 0) : set.weight, reps: set.reps };
    return prefill(number, slot, option, last, sets);
  };

  return (
    <Sequence>
      {numbers.map((number) => {
        const set = logged.get(number);
        const draft = draftFor(number);

        if (number === editing || (set === undefined && number === active)) {
          const previous = logged.get(number - 1);
          return (
            <SetEditor
              key={number}
              number={number}
              draft={draft}
              bodyweight={bodyweight}
              perDumbbell={option?.implement === "dumbbell"}
              unusual={unusualLoad(draft, last, option, gymId)}
              step={option?.min_increment ?? 1}
              state={set && exerciseId ? queue.stateOf(`set:${exerciseId}:${number}`) : undefined}
              onDraft={(next) => setDrafts({ ...drafts, [number]: next })}
              onConfirm={() => {
                onConfirm(number, draft, set);
                setEditing(null);
                setDrafts(Object.fromEntries(Object.entries(drafts).filter(([key]) => Number(key) !== number)));
              }}
              onDuplicate={
                previous && !set
                  ? () => {
                      onConfirm(number, {
                        load: bodyweight ? (previous.added_load ?? 0) : previous.weight,
                        reps: previous.reps,
                      });
                      setEditing(null);
                    }
                  : undefined
              }
            />
          );
        }

        if (set) {
          const state = exerciseId ? queue.stateOf(`set:${exerciseId}:${number}`) : "saved";
          return (
            <li key={number}>
              <SequenceRow
                number={number}
                state="done"
                value={describeSet(set, bodyweight)}
                trailing={<SyncMark state={state} />}
                label={`Serie ${number}: ${describeSet(set, bodyweight)}, ${SYNC_WORD[state]}. Tocar para corregir`}
                onClick={() => setEditing(number)}
              />
            </li>
          );
        }

        return (
          <li key={number}>
            <SequenceRow
              number={number}
              state="todo"
              value={describeSet({ reps: draft.reps, weight: draft.load, added_load: draft.load }, bodyweight)}
            />
          </li>
        );
      })}
      {running && active === undefined && editing === null && (
        <li>
          <Button variant="plain" size="small" icon="plus" onClick={() => setExtra(extra + 1)}>
            Añadir serie
          </Button>
        </li>
      )}
    </Sequence>
  );
}

interface SetEditorProps {
  number: number;
  draft: Draft;
  bodyweight: boolean;
  perDumbbell?: boolean;
  unusual?: number | null;
  step: number;
  state: SyncState | undefined;
  onDraft: (draft: Draft) => void;
  onConfirm: () => void;
  onDuplicate: (() => void) | undefined;
}

function SetEditor({
  number,
  draft,
  bodyweight,
  perDumbbell = false,
  unusual = null,
  step,
  state,
  onDraft,
  onConfirm,
  onDuplicate,
}: SetEditorProps) {
  const press = useLongPress(() => onDuplicate?.());
  const [asking, setAsking] = useState(false);
  useEffect(() => setAsking(false), [draft.load]);
  return (
    <li>
      <SequenceRow
        number={number}
        state="now"
        trailing={
          <ConfirmButton
            label={asking ? `Guardar serie ${number} así` : `Confirmar serie ${number}`}
            disabled={draft.reps === null}
            title={onDuplicate ? "Mantén pulsado para repetir la serie anterior" : undefined}
            {...press.handlers}
            onClick={() => {
              if (press.consumed()) return;
              if (unusual !== null && !asking) {
                setAsking(true);
                return;
              }
              onConfirm();
            }}
          />
        }
      >
        <Stepper
          size="small"
          label={bodyweight ? "Lastre" : perDumbbell ? "Peso por mancuerna" : "Peso"}
          value={draft.load}
          step={step}
          unit="kg"
          onChange={(load) => onDraft({ ...draft, load })}
        />
        <SequenceSeparator />
        <Stepper
          size="small"
          label="Reps"
          value={draft.reps}
          step={1}
          max={200}
          inputMode="numeric"
          onChange={(reps) => onDraft({ ...draft, reps })}
        />
      </SequenceRow>
      {perDumbbell && <SequenceHint>kg por mancuerna</SequenceHint>}
      {state && <SequenceHint>Corrigiendo la serie {number}</SequenceHint>}
      {asking && unusual !== null && draft.load !== null && (
        <Hint tone="warning">
          ¿{kg(draft.load)}? La última vez aquí, {kg(unusual)}. Toca otra vez para guardarlo así.
        </Hint>
      )}
    </li>
  );
}

function ExerciseNote({
  value,
  onSave,
  folded = false,
}: {
  value: string;
  onSave: (notes: string) => void;
  folded?: boolean;
}) {
  const [draft, setDraft] = useState(value);
  const [open, setOpen] = useState(!folded || value.trim() !== "");
  const save = () => {
    if (draft.trim() !== value.trim()) onSave(draft);
  };
  if (!open) {
    return (
      <Button variant="plain" size="small" icon="edit" onClick={() => setOpen(true)}>
        Añadir nota
      </Button>
    );
  }
  return (
    <TextField
      label="Nota"
      value={draft}
      onChange={setDraft}
      onBlur={save}
      onSubmit={save}
      placeholder="Polea rara, después de aperturas…"
    />
  );
}

export interface TimesSheetProps {
  day: string;
  startedAt: string;
  endedAt: string;
  onCancel: () => void;
  onSave: (times: { started_at: string; ended_at: string }) => Promise<void>;
}

export function TimesSheet({ day, startedAt, endedAt, onCancel, onSave }: TimesSheetProps) {
  const [start, setStart] = useState(() => madridTime(startedAt));
  const [end, setEnd] = useState(() => madridTime(endedAt));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const times = sessionTimes(day, start, end);

  const save = () => {
    if (!times) return;
    setBusy(true);
    setError(null);
    onSave({ started_at: times.started_at, ended_at: times.ended_at }).catch((reason: unknown) => {
      setError(reason instanceof Error && reason.message ? reason.message : "No se ha podido guardar");
      setBusy(false);
    });
  };

  return (
    <Sheet
      title="Horas del entreno"
      onClose={busy ? () => undefined : onCancel}
      action={{ label: busy ? "Guardando…" : "Guardar", onClick: save, disabled: busy || !times }}
    >
      <Hint>{longDate(day)}</Hint>
      <TextField label="Empezó" type="time" value={start} onChange={setStart} />
      <TextField
        label="Terminó"
        type="time"
        value={end}
        onChange={setEnd}
        hint={
          times
            ? `Duración: ${formatDuration(times.seconds)}${times.ended_at.startsWith(day) ? "" : ", terminó al día siguiente"}`
            : undefined
        }
      />
      {error && (
        <p className="training-field-error" role="alert">
          {error}
        </p>
      )}
    </Sheet>
  );
}

export interface DeleteSessionSheetProps {
  title: string;
  sets: number;
  onCancel: () => void;
  onDelete: (withSets: boolean) => Promise<void>;
}

export function DeleteSessionSheet({ title, sets, onCancel, onDelete }: DeleteSessionSheetProps) {
  return (
    <ConfirmDelete
      title="¿Borrar este entreno?"
      subject={title}
      consequence={
        sets > 0
          ? `Se borran sus ${sets} ${sets === 1 ? "serie" : "series"} y sus notas. No se puede deshacer.`
          : "No tiene series. No se puede deshacer."
      }
      action="Borrar entreno"
      onCancel={onCancel}
      onConfirm={() => onDelete(sets > 0)}
    />
  );
}
