import type { LoggedSet, Session, SessionExercise } from "./api";
import type { Op } from "./queue";

export function upsertSet(exercises: SessionExercise[], exerciseId: string, set: LoggedSet): SessionExercise[] {
  return exercises.map((exercise) =>
    exercise.id === exerciseId
      ? {
          ...exercise,
          sets: [...exercise.sets.filter((other) => other.number !== set.number), set].sort(
            (a, b) => a.number - b.number,
          ),
        }
      : exercise,
  );
}

export function overlay(session: Session, ops: Op[]): SessionExercise[] {
  let exercises = session.exercises;
  for (const op of ops) {
    if (op.session !== session.id) continue;
    const [kind, id, number] = op.key.split(":");
    if (!id) continue;
    if (kind === "exercise" && !exercises.some((exercise) => exercise.id === id)) {
      const slotId = op.body.plan_slot_id as string | null;
      const variantId = op.body.variant_id as string;
      const option = session.slots
        .find((slot) => slot.id === slotId)
        ?.options.find((candidate) => candidate.variant_id === variantId);
      exercises = [
        ...exercises,
        {
          id,
          plan_slot_id: slotId,
          variant_id: variantId,
          variant: option?.name ?? "",
          position: Math.max(0, ...exercises.map((exercise) => exercise.position)) + 1,
          sets: [],
        },
      ];
    }
    if (kind === "notes") {
      exercises = exercises.map((exercise) =>
        exercise.id === id ? { ...exercise, notes: (op.body.notes as string | null) ?? null } : exercise,
      );
    }
    if (kind === "set") {
      const body = op.body as Omit<LoggedSet, "number">;
      exercises = upsertSet(exercises, id, { ...body, number: Number(number) });
    }
  }
  return exercises;
}

export function remap(exercises: SessionExercise[], from: string, to: string): SessionExercise[] {
  const moved = exercises.find((exercise) => exercise.id === from);
  if (!moved) return exercises;
  const target = exercises.find((exercise) => exercise.id === to);
  const rest = exercises.filter((exercise) => exercise.id !== from && exercise.id !== to);
  const merged = target
    ? { ...target, sets: moved.sets.reduce((all, set) => upsertSet(all, to, set), [target])[0]?.sets ?? target.sets }
    : { ...moved, id: to };
  return [...rest, merged].sort((a, b) => a.position - b.position);
}

export function restSince(exercises: SessionExercise[]): string | null {
  let latest: string | null = null;
  for (const exercise of exercises) {
    for (const set of exercise.sets) {
      if (latest === null || Date.parse(set.confirmed_at) > Date.parse(latest)) latest = set.confirmed_at;
    }
  }
  return latest;
}

export function completedSets(exercises: SessionExercise[], slotId: string): number {
  return exercises
    .filter((exercise) => exercise.plan_slot_id === slotId)
    .reduce((total, exercise) => total + exercise.sets.filter((set) => set.completed).length, 0);
}

export function madridTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("es-ES", {
    timeZone: "Europe/Madrid",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
}

export interface Times {
  started_at: string;
  ended_at: string;
  seconds: number;
}

export function sessionTimes(day: string, start: string, end: string): Times | null {
  const valid = /^\d{2}:\d{2}$/;
  if (!valid.test(start) || !valid.test(end)) return null;
  const minutes = (time: string) => {
    const [hours, rest] = time.split(":").map(Number) as [number, number];
    return hours * 60 + rest;
  };
  const crosses = minutes(end) < minutes(start);
  const [year, month, date] = day.split("-").map(Number) as [number, number, number];
  const next = new Date(Date.UTC(year, month - 1, date + 1)).toISOString().slice(0, 10);
  return {
    started_at: `${day}T${start}:00`,
    ended_at: `${crosses ? next : day}T${end}:00`,
    seconds: (minutes(end) - minutes(start) + (crosses ? 24 * 60 : 0)) * 60,
  };
}
