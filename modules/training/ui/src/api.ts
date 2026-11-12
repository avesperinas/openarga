import type { BodyWeightHistory, WorkoutHeartData } from "@openarga/ui";

export type DayKind = "push" | "pull" | "leg" | "full" | "other";

export interface Option {
  variant_id: string;
  name: string;
  implement: string;
  min_increment: number;
  priority: number;
}

export interface Slot {
  id: string;
  position: number;
  exercise: string;
  target_sets: number;
  rep_min: number;
  rep_max: number;
  allow_both: boolean;
  options: Option[];
}

export interface Day {
  id: string;
  name: string;
  kind: DayKind;
  position: number;
  slots: Slot[];
}

export interface ActivePlan {
  plan_id: string;
  name: string;
  version_id: string;
  version: number;
  valid_from: string;
  days: Day[];
}

export interface NextSession {
  plan_day_id: string;
  name: string;
  kind: DayKind;
  rotation_number: number;
  remaining: number;
  days_in_rotation: number;
}

export interface Week {
  done: number;
  goal: number;
  monday: string;
}

export interface Settings {
  weekly_goal: number;
  unit: string;
  default_increments: Record<string, number>;
  bodyweight?: number | null;
}

export interface RotationDay {
  plan_day_id: string;
  name: string;
  kind: DayKind;
  done: boolean;
}

export interface Rotation {
  number: number;
  open: boolean;
  days: RotationDay[];
}

export interface Today {
  plan: ActivePlan | null;
  settings: Settings;
  next: NextSession | null;
  in_progress: string | null;
  week: Week;
  rotation?: Rotation | null;
}

export interface LoggedSet {
  number: number;
  reps: number | null;
  weight: number | null;
  added_load: number | null;
  completed: boolean;
  confirmed_at: string;
}

export interface SessionExercise {
  id: string;
  plan_slot_id: string | null;
  variant_id: string;
  variant: string;
  position: number;
  notes?: string | null;
  sets: LoggedSet[];
}

export interface LastTime {
  variant_id: string;
  day: string;
  gym_id?: string | null;
  gym?: string | null;
  sets: LoggedSet[];
}

export interface Session {
  id: string;
  rotation_number: number;
  plan_day_id: string;
  day_name: string;
  kind: DayKind;
  day: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  gym_id: string | null;
  source?: "app" | "import";
  slots: Slot[];
  exercises: SessionExercise[];
  history: LastTime[];
}

export const BASE = "/api/training";

type Here = Pick<Location, "pathname" | "search" | "assign">;

export function signIn(here: Here = window.location): void {
  here.assign(`/login?next=${encodeURIComponent(here.pathname + here.search)}`);
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}, fetcher: typeof fetch = fetch): Promise<T> {
  const response = await fetcher(`${BASE}${path}`, {
    ...init,
    headers: { accept: "application/json", "content-type": "application/json" },
  });
  if (response.status === 401) signIn();
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof body?.detail === "string" ? body.detail : `${path} respondió ${response.status}`;
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const send = <T>(method: string, path: string, body?: unknown) =>
  call<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

export function readToday(fetcher: typeof fetch = fetch): Promise<Today> {
  return call<Today>("/today", {}, fetcher);
}

export async function startSession(planDayId?: string, fetcher: typeof fetch = fetch): Promise<string> {
  const body = planDayId ? { plan_day_id: planDayId } : {};
  const { id } = await call<{ id: string }>("/sessions", { method: "POST", body: JSON.stringify(body) }, fetcher);
  return id;
}

export const deleteSession = (id: string, withSets: boolean) =>
  send<void>("DELETE", `/sessions/${id}${withSets ? "?with_sets=true" : ""}`);

export const changeTimes = (id: string, times: { started_at: string; ended_at: string }) =>
  send<Session>("PUT", `/sessions/${id}/times`, times);

export interface SessionSummary {
  id: string;
  day: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  day_name: string;
  kind: DayKind;
  rotation_number: number;
  gym: string | null;
  exercises: number;
  sets: number;
}

export const listSessions = (since: string, until: string) =>
  call<SessionSummary[]>(`/sessions?since=${since}&until=${until}`);

export interface ActivityType {
  id: string;
  name: string;
  active: boolean;
  band_kinds?: string[];
}

export interface BandMeasured {
  kcal?: number;
  distance_km?: number;
  heart_rate_avg?: number;
  heart_rate_max?: number;
  active_zone_min?: number;
  hr_zone_min?: Partial<Record<"light" | "moderate" | "vigorous" | "peak", number>>;
}

export interface Activity {
  id: string;
  activity_type_id: string;
  name: string;
  day: string;
  start_time: string;
  duration_seconds: number | null;
  notes: string | null;
  source?: string;
  band?: BandMeasured | null;
  from_band?: boolean;
  ongoing?: boolean;
}

export const listActivityTypes = () => call<ActivityType[]>("/activity-types");
export const createActivityType = (name: string) => send<ActivityType>("POST", "/activity-types", { name });
export const listActivities = (since: string, until: string) =>
  call<Activity[]>(`/activities?since=${since}&until=${until}`);
export const logActivity = (body: {
  activity_type_id: string;
  day: string;
  start_time: string;
  duration_seconds: number | null;
  notes: string | null;
}) => send<Activity>("POST", "/activities", body);
export const removeActivity = (id: string) => send<void>("DELETE", `/activities/${id}`);
export const startActivity = (activity_type_id: string) =>
  send<Activity>("POST", "/activities/start", { activity_type_id });
export const finishActivity = (id: string) => send<Activity>("POST", `/activities/${id}/finish`);
export const listOngoingActivities = () => call<Activity[]>("/activities/ongoing");
export const setActivityTimes = (id: string, start: string, end: string) =>
  send<Activity>("PUT", `/activities/${id}/times`, { start, end });
export const updateActivityType = (type: ActivityType) =>
  send<ActivityType>("PUT", `/activity-types/${type.id}`, {
    name: type.name,
    active: type.active,
    band_kinds: type.band_kinds ?? [],
  });

export type Implement = "barbell" | "dumbbell" | "smith" | "machine" | "cable" | "bodyweight";
export type Pattern =
  | "horizontal_push"
  | "vertical_push"
  | "horizontal_pull"
  | "vertical_pull"
  | "knee_dominant"
  | "hip_dominant"
  | "isolation";

export interface Version {
  id: string;
  number: number;
  valid_from: string | null;
  published_at: string | null;
  days: Day[];
}

export interface Editor {
  plan: { id: string; name: string } | null;
  published: Version | null;
  draft: Version | null;
  rotation_version: number | null;
}

export interface CatalogueVariant {
  id: string;
  exercise_id: string;
  name: string;
  implement: Implement;
  gym_id: string | null;
  min_increment: number;
  index_weight: number;
}

export interface CatalogueExercise {
  id: string;
  name: string;
  pattern: Pattern;
  load_type: string;
  muscles: Record<string, number>;
  variants: CatalogueVariant[];
}

export interface Gym {
  id: string;
  name: string;
  active: boolean;
}

export interface Catalogue {
  exercises: CatalogueExercise[];
  gyms: Gym[];
  muscles: { id: string; name: string; region: string }[];
}

export interface SlotInput {
  target_sets: number;
  rep_min: number;
  rep_max: number;
  allow_both: boolean;
  variant_ids: string[];
}

export interface DayInput {
  name: string;
  kind: DayKind;
  slots: SlotInput[];
}

export const readPlan = () => call<Editor>("/plan");
export const createPlan = (name: string) => send<Editor>("POST", "/plan", { name });
export const renamePlan = (name: string) => send<Editor>("PATCH", "/plan", { name });
export const openDraft = () => send<Editor>("POST", "/plan/draft");
export const saveDraft = (days: DayInput[]) => send<Editor>("PUT", "/plan/draft", { days });
export const discardDraft = () => send<Editor>("DELETE", "/plan/draft");
export const publishDraft = () => send<Editor>("POST", "/plan/draft/publish");

export const readCatalogue = () => call<Catalogue>("/catalogue");
export type Muscles = Record<string, 1 | 0.5>;

export const createExercise = (body: {
  name: string;
  pattern: Pattern;
  muscles: Muscles;
  variant: { name: string; implement: Implement };
}) => send<CatalogueExercise>("POST", "/exercises", body);
export const updateMuscles = (exerciseId: string, muscles: Muscles) =>
  send<CatalogueExercise>("PUT", `/exercises/${exerciseId}/muscles`, { muscles });
export const createVariant = (exerciseId: string, body: { name: string; implement: Implement }) =>
  send<CatalogueVariant>("POST", `/exercises/${exerciseId}/variants`, body);
export const createGym = (name: string) => send<Gym>("POST", "/gyms", { name });
export const updateGym = (gym: Gym) => send<Gym>("PUT", `/gyms/${gym.id}`, { name: gym.name, active: gym.active });
export const updateSettings = (weeklyGoal: number) =>
  send<Settings>("PUT", "/settings", { weekly_goal: weeklyGoal });
export const updateBodyweight = (kg: number) => send<Settings>("PUT", "/bodyweight", { kg });
export const readWeight = () => call<BodyWeightHistory>("/weight");

export type WorkoutPulse = WorkoutHeartData & { found: boolean };
export const readHeart = (id: string) => call<WorkoutPulse>(`/heart?id=${encodeURIComponent(id)}`);
export const logWeight = (kg: number) => send<BodyWeightHistory>("POST", "/weight", { kg });

export function readSession(id: string, fetcher: typeof fetch = fetch): Promise<Session> {
  return call<Session>(`/sessions/${id}`, {}, fetcher);
}

export interface Worked {
  muscle: string;
  name: string;
  sets: number;
}

export interface SessionRecord {
  variant_id: string;
  range: string;
  reps: number;
  load: number;
  previous: number;
}

export interface Outcome {
  session_id: string;
  muscles: Worked[];
  records: SessionRecord[];
}

export const readOutcome = (id: string) => call<Outcome>(`/sessions/${id}/outcome`);

export const readVersion = (): Promise<string> =>
  fetch(`${BASE}/version`, { headers: { accept: "application/json" } })
    .then((response) => (response.ok ? response.json() : null))
    .then((body: { version?: string } | null) => body?.version ?? "")
    .catch(() => "");

export type Period = "4w" | "3m" | "1y" | "all";
export type Direction = "up" | "flat" | "down";

export interface Trend {
  day: string;
  value: number;
}

export interface Index {
  value: number | null;
  delta: number | null;
  direction: Direction | null;
  muscles: number;
  trend: Trend[];
}

export interface MuscleSummary {
  muscle: string;
  name: string;
  region: string;
  sets: number;
  band: "low" | "ok" | "high";
  value: number | null;
  delta: number | null;
  direction: Direction | null;
  trend: Trend[];
  last_day: string | null;
  current: string | null;
  excluded: number;
}

export interface Mover {
  variant_id: string;
  gym_id: string | null;
  gym: string | null;
  exercise: string;
  variant: string;
  e1rm: number;
  delta: number;
  sessions: number;
  without_pr: number;
}

export interface Stats {
  period: Period;
  since: string;
  until: string;
  sessions: number;
  index: Index;
  frequency: { done: number; goal: number; average: number; streak: number };
  muscles: MuscleSummary[];
  movers: Mover[];
  excluded: number;
  bodyweight: number | null;
}

export interface ExerciseHistory {
  variant_id: string;
  exercise: string;
  variant: string;
  gyms: string[];
  first_day: string;
  last_day: string;
  sessions: number;
  excluded: number;
  best: number | null;
  last: number | null;
  delta: number | null;
}

export interface MuscleStats {
  muscle: string;
  name: string;
  region: string;
  since: string;
  until: string;
  value: number | null;
  delta: number | null;
  direction: Direction | null;
  trend: Trend[];
  sets: number;
  band: "low" | "ok" | "high";
  last_day: string | null;
  changes: string[];
  exercises: ExerciseHistory[];
}

export type PointStatus = "counted" | "high" | "low" | "excluded";

export interface VariantPoint {
  id: string;
  session_id: string;
  day: string;
  reps: number;
  load: number;
  e1rm: number;
  reliable: boolean;
  status: PointStatus;
  reference: number | null;
  verdict: "counted" | "excluded" | null;
}

export interface Segment {
  since: string;
  until: string;
  start: "first" | "mark" | "detected";
  jump: number | null;
  mark_id: string | null;
}

export interface Machine {
  gym_id: string | null;
  gym: string | null;
  first_day: string;
  last_day: string;
  points: VariantPoint[];
  segments: Segment[];
  marks: { id: string; day: string; kind: "split" | "join" }[];
  best: VariantPoint | null;
  records: { range: string; load: number; reps: number; day: string; reliable: boolean }[];
  without_pr: number;
  excluded: number;
}

export interface VariantStats {
  variant_id: string;
  exercise: string;
  variant: string;
  implement: string;
  load_type: string;
  muscle: string | null;
  min_increment: number;
  since: string;
  until: string;
  bodyweight: number | null;
  machines: Machine[];
  notes: { title: string; href: string; line: string }[];
}

export const readStats = (period: Period) => call<Stats>(`/stats?period=${period}`);

export const readMuscleStats = (muscle: string, period: Period) =>
  call<MuscleStats>(`/stats/muscles/${muscle}?period=${period}`);

export const readVariantStats = (variantId: string, period: Period) =>
  call<VariantStats>(`/stats/variants/${variantId}?period=${period}`);

export const judgePoint = (pointId: string, verdict: "counted" | "excluded") =>
  send<void>("PUT", `/stats/points/${pointId}`, { verdict });
export const clearPoint = (pointId: string) => send<void>("DELETE", `/stats/points/${pointId}`);

export const addMark = (body: { variant_id: string; gym_id: string | null; day: string; kind: "split" | "join" }) =>
  send<{ id: string }>("POST", "/stats/marks", body);
export const removeMark = (markId: string) => send<void>("DELETE", `/stats/marks/${markId}`);
