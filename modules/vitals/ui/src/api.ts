const BASE = "/api/vitals";

export type Source = "manual" | "claude" | "history";

export interface Entry {
  id: string;
  day: string;
  at: string | null;
  kg: number;
  source: Source;
  note: string | null;
}

export interface Day {
  day: string;
  kg: number;
  avg7: number;
}

export interface Goal {
  steps_per_day: number | null;
  weight_min_kg: number | null;
  weight_max_kg: number | null;
  weight_direction: "up" | "down" | null;
}

export type Against = "below" | "inside" | "above";

export interface WeightSummary {
  days: Day[];
  entries: Entry[];
  latest: Day | null;
  change_30: number | null;
  change_90: number | null;
  goal: Goal;
  against_goal: Against | null;
}

export interface WeightIn {
  kg: number;
  day?: string | null;
  at?: string | null;
  note?: string | null;
}

export class Unauthorised extends Error {}

async function answer<T>(path: string, response: Response): Promise<T> {
  if (response.status === 401) throw new Unauthorised("no session");
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(typeof detail?.detail === "string" ? detail.detail : `${path}: ${response.status}`);
  }
  return (await response.json()) as T;
}

async function get<T>(path: string): Promise<T> {
  return answer<T>(path, await fetch(`${BASE}${path}`, { headers: { accept: "application/json" } }));
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: { "content-type": "application/json", accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return answer<T>(path, response);
}

export const readWeight = () => get<WeightSummary>("/weight");
export const logWeight = (weighing: WeightIn) =>
  send<{ entry: Entry; already: boolean }>("/weight", "POST", weighing);
export const correctWeight = (id: string, weighing: WeightIn) => send<Entry>(`/weight/${id}`, "PUT", weighing);
export interface StepsDay {
  day: string;
  steps: number;
}

export interface StepsSummary {
  days: StepsDay[];
  today: StepsDay | null;
  mean_7: number | null;
  mean_30: number | null;
  goal: number | null;
  best: StepsDay | null;
  streak: number;
  by_weekday: (number | null)[];
  last_received: string | null;
}

export const readSteps = () => get<StepsSummary>("/steps");
export interface Analyte {
  id: string;
  name: string;
  panel: "blood_count" | "biochemistry" | "lipids" | "urine" | "other";
  unit: string | null;
  about: string;
}

export interface Checkup {
  id: string;
  day: string;
  center: string | null;
  notes: string | null;
  values: number;
  out: number;
  document: string | null;
}

export interface Cell {
  value: number | null;
  value_text: string | null;
  unit: string | null;
  ref_low: number | null;
  ref_high: number | null;
  out: boolean;
}

export interface LabTable {
  checkups: Checkup[];
  rows: { analyte: Analyte; cells: Record<string, Cell> }[];
}

export interface Point {
  day: string;
  checkup_id: string;
  value: number;
  ref_low: number | null;
  ref_high: number | null;
  out: boolean;
}

export interface Evolution {
  analyte: Analyte;
  points: Point[];
  skipped: number;
}

export interface ResultIn {
  analyte: string;
  value?: number | null;
  value_text?: string | null;
  unit?: string | null;
  ref_low?: number | null;
  ref_high?: number | null;
}

export interface Latest {
  analyte: string;
  day: string;
  value: number;
  unit: string | null;
  ref_low: number | null;
  ref_high: number | null;
  out: boolean;
  previous: number | null;
  previous_day: string | null;
}

export interface Kpis {
  steps: {
    today: number | null;
    mean_7: number | null;
    mean_7_past: number | null;
    mean_30: number | null;
    goal: number | null;
  };
  weight: {
    average_7: number | null;
    change_30: number | null;
    change_90: number | null;
    goal: Goal;
    against_goal: Against | null;
  };
  ldl: Latest | null;
}

export const readKpis = () => get<Kpis>("/kpis");
export const readAnalytes = () => get<Analyte[]>("/analytes");
export const readLabs = () => get<LabTable>("/labs");
export const readEvolution = (analyte: string) => get<Evolution>(`/labs/${encodeURIComponent(analyte)}`);
export const recordCheckup = (day: string, center: string | null) =>
  send<{ id: string; existed: boolean }>("/checkups", "POST", { day, center });
export const addResult = (checkup: string, result: ResultIn) =>
  send<unknown>(`/checkups/${checkup}/results`, "POST", result);
export const documentUrl = (checkup: string) => `${BASE}/checkups/${checkup}/document`;

export async function uploadDocument(checkup: string, file: File): Promise<void> {
  const response = await fetch(`${BASE}/checkups/${checkup}/document?filename=${encodeURIComponent(file.name)}`, {
    method: "PUT",
    headers: { "content-type": "application/pdf" },
    body: file,
  });
  if (response.status === 401) throw new Unauthorised("no session");
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(typeof detail?.detail === "string" ? detail.detail : "Could not upload the PDF.");
  }
}

export const readGoals = () => get<Goal>("/goals");
export const saveGoals = (goal: Goal) => send<Goal>("/goals", "PUT", goal);

export function signIn(): void {
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.assign(`/login?next=${next}`);
}

export async function readVersion(): Promise<string> {
  try {
    const { version } = await get<{ version: string }>("/version");
    return version;
  } catch {
    return "";
  }
}

export type BodyGroup = "heart" | "activity" | "breath" | "gait" | "more" | "history";

export interface BodyPoint {
  day: string;
  value: number;
  total?: number | null;
}

export interface Figure {
  id: string;
  group: BodyGroup;
  name: string;
  unit: string;
  digits: number;
  kind: "mean" | "sum" | "last";
  about: string;
  latest: BodyPoint | null;
  mean_30: number | null;
  mean_365: number | null;
  days: number;
  changed_on?: string | null;
  historic?: boolean;
  weeks?: (number | null)[];
}

export interface BodySection {
  id: BodyGroup;
  name: string;
  figures: Figure[];
}

export interface Profile {
  blood_type: string | null;
  sex: "female" | "male" | "other" | null;
  birth_date: string | null;
  age: number | null;
  height_cm: number | null;
  cardio_medications: string | null;
  walking_stride_cm?: number | null;
  running_stride_cm?: number | null;
  irn_enrolled?: boolean | null;
}

export interface BodyOverview {
  profile: Profile | null;
  sections: BodySection[];
}

export interface FigureSeries {
  figure: Figure;
  points: BodyPoint[];
}

export const readBody = () => get<BodyOverview>("/body");
export const readFigure = (id: string) => get<FigureSeries>(`/body/${id}`);
export const readProfile = () => get<Profile | null>("/profile");

export type SleepStage = "deep" | "rem" | "light" | "awake";

export type Quality = "excellent" | "good" | "fair" | "poor";

export interface Score {
  value: number;
  quality: Quality;
  duration: number;
  depth: number | null;
  calm: number | null;
}

export interface Night {
  day: string;
  start: string;
  end: string;
  minutes_asleep: number;
  minutes_awake: number | null;
  minutes_in_bed: number | null;
  minutes_to_fall_asleep: number | null;
  stages: Partial<Record<SleepStage, number>> | null;
  nap_minutes: number;
  awakenings?: number | null;
  minutes_after_wake_up?: number | null;
  minutes_out_of_bed?: number | null;
  score?: Score | null;
}

export interface SleepSegment {
  start: string;
  end: string;
  stage: SleepStage | "asleep" | "restless";
}

export interface NightDetail extends Night {
  segments: SleepSegment[];
}

export interface SleepMeans {
  nights: number;
  asleep: number | null;
  stages: Partial<Record<SleepStage, number>>;
  fell_asleep_at: number | null;
  woke_at: number | null;
}

export interface SleepSummary {
  last: NightDetail | null;
  nights: Night[];
  mean_7: SleepMeans;
  mean_30: SleepMeans;
}

export interface HeartBucket {
  minute: number;
  min: number;
  avg: number;
  max: number;
}

export interface HeartDay {
  day: string;
  step: number;
  buckets: HeartBucket[];
  min: HeartBucket | null;
  max: HeartBucket | null;
}

export const readSleep = (since?: string) => get<SleepSummary>(since ? `/sleep?since=${since}` : "/sleep");

export interface NightPage {
  night: NightDetail;
  heart: { at: string; bpm: number }[];
  figures: Baseline[];
  mean_30: SleepMeans;
  previous: string | null;
  next: string | null;
}

export const readNight = (day: string) => get<NightPage>(`/night/${day}`);
export const readHeartDays = () => get<string[]>("/heart");
export const readHeartDay = (day: string) => get<HeartDay>(`/heart/${day}`);

export interface Ecg {
  id: string;
  start: string;
  end: string;
  result: string | null;
  result_text: string | null;
  heart_rate_avg: number | null;
  seconds: number | null;
  device: string | null;
}

export interface EcgTrace extends Ecg {
  step_seconds: number | null;
  millivolts: number[];
}

export interface Irn {
  id: string;
  start: string;
  end: string;
  windows: number;
  positive_windows: number;
  device: string | null;
}

export interface Device {
  id: string;
  name: string;
  kind: string;
  battery_pct: number | null;
  battery: "high" | "medium" | "low" | "empty" | null;
  last_sync: string | null;
}

export const readEcgs = () => get<Ecg[]>("/ecg");
export const readEcg = (id: string) => get<EcgTrace>(`/ecg/trace?id=${encodeURIComponent(id)}`);
export const readIrns = () => get<Irn[]>("/irn");
export const readDevices = () => get<Device[]>("/devices");

export type Status = "below" | "inside" | "above";

export interface Baseline {
  id: string;
  name: string;
  unit: string;
  digits: number;
  day: string | null;
  value: number | null;
  mean: number | null;
  low: number | null;
  high: number | null;
  status: Status | null;
  days: number;
}

export interface WorkoutHeart {
  avg: number | null;
  max: number | null;
  zones: number[];
  load: number;
  recovery_2min: number | null;
  source: "band" | "day" | null;
}

export interface Workout {
  id: string;
  kind: "strength" | "activity";
  name: string;
  start: string;
  end: string;
  minutes: number;
  href: string | null;
  from_band: boolean;
  kcal: number | null;
  heart: WorkoutHeart;
}

export interface WorkoutDetail extends Workout {
  beats: { s: number; bpm: number }[];
  marks: { at: string; label: string }[];
  max_heart_rate: number;
}

export interface LoadWeek {
  start: string;
  workouts: number;
  minutes: number;
  load: number;
  zones?: number[];
}

export interface Load {
  this_week: number;
  mean_4: number | null;
  weeks: LoadWeek[];
}

export interface Today {
  day: string;
  steps: Kpis["steps"];
  pulse: { minute: number; bpm: number } | null;
  baselines: Baseline[];
  load: Load;
  workouts: Workout[];
  battery: Device | null;
}

export interface DayLine {
  day: string;
  night: NightDetail | null;
  heart: HeartDay | null;
  workouts: Workout[];
}

export interface SleepGroup {
  nights: number;
  asleep: number | null;
  deep: number | null;
  hrv: number | null;
}

export interface SleepPatterns {
  nights: number;
  fell_asleep_spread: number | null;
  woke_spread: number | null;
  comparisons: { id: string; label: string; after: SleepGroup; rest: SleepGroup }[];
}

export interface CheckupChange {
  analyte: Analyte;
  value: number;
  previous: number;
  unit: string | null;
  change: number;
  out: boolean;
  was_out: boolean;
}

export interface CheckupChanges {
  checkup: Checkup | null;
  previous: Checkup | null;
  changes: CheckupChange[];
}

export const readToday = () => get<Today>("/today");
export const readDayLine = (day: string) => get<DayLine>(`/day/${day}`);
export const readWorkouts = () => get<Workout[]>("/workouts");
export const readWorkout = (id: string) => get<WorkoutDetail>(`/workouts/detail?id=${encodeURIComponent(id)}`);
export const readLoad = () => get<Load>("/load");
export const readSleepPatterns = () => get<SleepPatterns>("/sleep-patterns");
export const readCheckupChanges = () => get<CheckupChanges>("/labs/changes");

export interface Stress {
  tension: {
    day: string;
    minutes: number;
    still_minutes: number;
    by_hour: number[];
    threshold: number;
    resting: number;
  } | null;
  morning: { score: number | null; hrv_z: number | null; resting_z: number | null; days_left: number };
  missing: string | null;
}

export const readStress = () => get<Stress>("/stress");
