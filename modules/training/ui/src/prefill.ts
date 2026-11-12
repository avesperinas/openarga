import { formatDecimal } from "@openarga/ui";

import type { LastTime, LoggedSet, Option, SessionExercise, Slot } from "./api";

export interface Draft {
  load: number | null;
  reps: number | null;
}

export function isBodyweight(option: Pick<Option, "implement"> | undefined): boolean {
  return option?.implement === "bodyweight";
}

export function byPriority(slot: Slot): Option[] {
  return [...slot.options].sort((a, b) => a.priority - b.priority);
}

export function preferredVariant(
  slot: Slot,
  history: LastTime[],
  exercises: SessionExercise[],
): string | undefined {
  const inSession = exercises
    .filter((exercise) => exercise.plan_slot_id === slot.id)
    .sort((a, b) => b.position - a.position)[0];
  if (inSession) return inSession.variant_id;

  const options = byPriority(slot);
  const used = options
    .map((option) => ({ option, last: history.find((h) => h.variant_id === option.variant_id) }))
    .filter((entry) => entry.last !== undefined)
    .sort((a, b) => (a.last!.day < b.last!.day ? 1 : a.last!.day > b.last!.day ? -1 : 0))[0];
  return used?.option.variant_id ?? options[0]?.variant_id;
}

function loadOf(set: LoggedSet, bodyweight: boolean): number | null {
  return bodyweight ? (set.added_load ?? 0) : set.weight;
}

export function prefill(
  number: number,
  slot: Slot,
  option: Option | undefined,
  last: LastTime | undefined,
  today: LoggedSet[],
): Draft {
  const bodyweight = isBodyweight(option);
  const completed = last?.sets.filter((set) => set.completed) ?? [];
  const reference = completed.find((set) => set.number === number) ?? completed[completed.length - 1];
  if (reference) return { load: loadOf(reference, bodyweight), reps: reference.reps };

  const previous = today.filter((set) => set.number < number).sort((a, b) => b.number - a.number)[0];
  if (previous) return { load: loadOf(previous, bodyweight), reps: previous.reps };
  return { load: bodyweight ? 0 : null, reps: slot.rep_min };
}

const UNUSUAL = 0.3;

export function unusualLoad(
  draft: Draft,
  last: LastTime | undefined,
  option: Pick<Option, "implement"> | undefined,
  gymId: string | null,
): number | null {
  if (isBodyweight(option) || !last || draft.load === null || draft.load <= 0) return null;
  if ((last.gym_id ?? null) !== gymId) return null;
  const loads = last.sets
    .filter((set) => set.completed && set.weight !== null && set.weight > 0)
    .map((set) => set.weight as number);
  if (loads.length === 0) return null;
  const reference = Math.max(...loads);
  const ratio = draft.load / reference;
  return ratio > 1 + UNUSUAL || ratio < 1 / (1 + UNUSUAL) ? reference : null;
}

export function kg(value: number): string {
  return `${formatDecimal(value)} kg`;
}

export function describeSet(set: Pick<LoggedSet, "reps" | "weight" | "added_load">, bodyweight: boolean): string {
  const reps = set.reps === null ? "—" : String(set.reps);
  if (bodyweight) return set.added_load ? `${reps} + ${kg(set.added_load)}` : reps;
  return set.weight === null ? reps : `${reps} × ${kg(set.weight)}`;
}

export function describeSets(sets: LoggedSet[], bodyweight: boolean): string {
  const runs: LoggedSet[][] = [];
  for (const set of sets.filter((candidate) => candidate.completed)) {
    const run = runs[runs.length - 1];
    if (run?.[0] && loadOf(run[0], bodyweight) === loadOf(set, bodyweight)) run.push(set);
    else runs.push([set]);
  }
  return runs
    .map((run) => {
      const reps = run.map((set) => (set.reps === null ? "—" : String(set.reps))).join(", ");
      const [first] = run as [LoggedSet, ...LoggedSet[]];
      return describeSet({ ...first, reps: null }, bodyweight).replace("—", reps);
    })
    .join(" · ");
}

const SHORT_DATE = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short" });

export function shortDay(day: string): string {
  const [year = 1970, month = 1, date = 1] = day.split("-").map(Number);
  return SHORT_DATE.format(new Date(year, month - 1, date)).replace(".", "");
}
