import { peek, remember } from "@openarga/app";

import {
  ApiError,
  type LastTime,
  type Session,
  type Today,
  readSession,
  readToday,
  startSession,
} from "./api";
import { SyncQueue } from "./queue";

const TODAY = "today";
const HISTORY = "history";
const sessionKey = (id: string) => `session:${id}`;

export const offline = (error: unknown) => !(error instanceof ApiError);

let shared: SyncQueue | null = null;
export function sharedQueue(): SyncQueue {
  shared ??= new SyncQueue();
  return shared;
}

export function mergeHistory(known: Record<string, LastTime>, entries: LastTime[]): Record<string, LastTime> {
  const next = { ...known };
  for (const entry of entries) {
    const before = next[entry.variant_id];
    if (!before || before.day <= entry.day) next[entry.variant_id] = entry;
  }
  return next;
}

export function learnFrom(session: Session): LastTime[] {
  const own = session.ended_at
    ? session.exercises
        .filter((exercise) => exercise.sets.some((set) => set.completed))
        .map((exercise) => ({
          variant_id: exercise.variant_id,
          day: session.day,
          gym_id: session.gym_id,
          sets: exercise.sets,
        }))
    : [];
  return [...session.history, ...own];
}

function learn(session: Session): void {
  remember(HISTORY, mergeHistory(peek<Record<string, LastTime>>(HISTORY) ?? {}, learnFrom(session)));
}

export async function readTodayKept(): Promise<Today> {
  try {
    const today = await readToday();
    remember(TODAY, today);
    return today;
  } catch (error) {
    const kept = peek<Today>(TODAY);
    if (offline(error) && kept) return kept;
    throw error;
  }
}

export const keptSession = (id: string) => peek<Session>(sessionKey(id));

export async function readSessionKept(id: string): Promise<Session> {
  try {
    const session = await readSession(id);
    remember(sessionKey(id), session);
    learn(session);
    return session;
  } catch (error) {
    const kept = keptSession(id);
    if (offline(error) && kept) return kept;
    throw error;
  }
}

export function offlineSession(
  today: Today,
  id: string,
  planDayId: string | undefined,
  startedAt: Date,
  history: Record<string, LastTime>,
): Session | null {
  const dayId = planDayId ?? today.next?.plan_day_id;
  const day = today.plan?.days.find((candidate) => candidate.id === dayId);
  if (!day) return null;
  const variants = new Set(day.slots.flatMap((slot) => slot.options.map((option) => option.variant_id)));
  const local = new Date(startedAt.getTime() - startedAt.getTimezoneOffset() * 60_000);
  return {
    id,
    rotation_number: today.next?.rotation_number ?? today.rotation?.number ?? 1,
    plan_day_id: day.id,
    day_name: day.name,
    kind: day.kind,
    day: local.toISOString().slice(0, 10),
    started_at: startedAt.toISOString(),
    ended_at: null,
    duration_seconds: null,
    gym_id: null,
    slots: day.slots,
    exercises: [],
    history: Object.values(history).filter((entry) => variants.has(entry.variant_id)),
  };
}

export async function startAnywhere(
  planDayId?: string,
  queue: SyncQueue = sharedQueue(),
  now: () => Date = () => new Date(),
  newId: () => string = () => crypto.randomUUID(),
): Promise<string> {
  try {
    return await startSession(planDayId);
  } catch (error) {
    const today = peek<Today>(TODAY);
    if (!offline(error) || !today) throw error;
    const id = newId();
    const startedAt = now();
    const session = offlineSession(today, id, planDayId, startedAt, peek<Record<string, LastTime>>(HISTORY) ?? {});
    if (!session) throw error;
    remember(sessionKey(id), session);
    remember(TODAY, { ...today, in_progress: id });
    queue.enqueue({
      key: `start:${id}`,
      session: id,
      method: "PUT",
      path: `/sessions/${id}`,
      body: { started_at: session.started_at, plan_day_id: session.plan_day_id },
    });
    return id;
  }
}
