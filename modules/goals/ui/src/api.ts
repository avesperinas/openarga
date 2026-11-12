import { createApi, invalidate } from "@openarga/app";

export { Unauthorised, problemOf, signIn } from "@openarga/app";

export const api = createApi("goals");
const { get, send } = api;

export function changed(): void {
  for (const key of ["tasks", "goals", "goal:", "categories"]) invalidate(key);
}

export type Status = "overdue" | "today" | "upcoming" | "someday" | "done";

export interface Category {
  id: string;
  name: string;
  hue: number;
  position: number;
  space_id: string | null;
  pending: number;
  overdue: number;
  goals: number;
}

export interface Task {
  id: string;
  category_id: string;
  category: string;
  hue: number;
  title: string;
  notes: string | null;
  due_on: string | null;
  due_time: string | null;
  rule: string | null;
  repeats: string | null;
  status: Status;
  done_at: string | null;
  done_by_me: boolean | null;
  space_id: string | null;
}

export interface TaskIn {
  category_id: string;
  title: string;
  notes: string | null;
  due_on: string | null;
  due_time: string | null;
  rule: string | null;
}

export interface Completed {
  task: Task;
  next: Task | null;
}

export type GoalKind = "periodic" | "dated";
export type Direction = "at_least" | "at_most";
export type Period = "day" | "week";
export type GoalStatus = "active" | "achieved" | "missed" | "abandoned";
export type Pace = "ahead" | "on_track" | "behind";
export type DayState = "met" | "missed" | "today" | "future" | "before";

export interface MetricRef {
  key: string;
  label: string;
  unit: string;
  kind: "level" | "amount" | "peak";
}

export interface Metric extends MetricRef {
  last_day: string;
  last_value: number;
}

export interface Goal {
  id: string;
  title: string;
  category_id: string | null;
  category: string | null;
  hue: number | null;
  kind: GoalKind;
  metric: MetricRef | null;
  direction: Direction;
  target: number | null;
  period: Period | null;
  days_per_week: number | null;
  start_value: number | null;
  start_on: string;
  due_on: string | null;
  status: GoalStatus;
  closed_on: string | null;
  closed_value: number | null;
  note: string | null;
  featured: boolean;
  position: number;
  today_met: boolean | null;
  today_value: number | null;
  today_manual: boolean;
  week: { day: string; state: DayState }[];
  week_count: number | null;
  week_target: number | null;
  week_met: boolean | null;
  streak: number | null;
  streak_unit: "days" | "weeks" | null;
  constancy: number | null;
  current: number | null;
  start: number | null;
  expected: number | null;
  pace: Pace | null;
  progress: number | null;
  projection: number | null;
  projection_reached: boolean | null;
  reached: boolean | null;
  last_day: string | null;
  days_left: number | null;
}

export interface DayPoint {
  day: string;
  value: number | null;
  met: boolean | null;
  manual: boolean;
  done: boolean | null;
  note: string | null;
}

export interface GoalDetail {
  goal: Goal;
  history: DayPoint[];
}

export interface GoalIn {
  title: string;
  category_id: string | null;
  kind: GoalKind;
  metric_key: string | null;
  direction: Direction;
  target: number | null;
  period: Period | null;
  days_per_week: number | null;
  start_value: number | null;
  start_on: string | null;
  due_on: string | null;
  note: string | null;
  featured: boolean;
}

export interface CheckIn {
  day?: string;
  done?: boolean | null;
  value?: number | null;
  note?: string | null;
}

export interface Space {
  id: string;
  name: string;
  role: string;
  members: number;
}

export const readCategories = () => get<Category[]>("/categories");
export const createCategory = (name: string, hue: number) => send<Category>("/categories", "POST", { name, hue });
export const updateCategory = (id: string, body: { name?: string; hue?: number }) =>
  send<Category>(`/categories/${id}`, "PUT", body);
export const orderCategories = (ids: string[]) => send<Category[]>("/categories/order", "POST", { ids });
export const removeCategory = (id: string) => send<void>(`/categories/${id}`, "DELETE");
export const shareCategory = (id: string, space: string | null) =>
  send<Category>(`/categories/${id}/space`, "PUT", { space_id: space });

export const readPending = () => get<Task[]>("/tasks");
export const readDone = () => get<Task[]>("/tasks?state=done");
export const readTask = (id: string) => get<Task>(`/tasks/${id}`);
export const createTask = (body: TaskIn) => send<Task>("/tasks", "POST", body);
export const updateTask = (id: string, body: Partial<TaskIn>) => send<Task>(`/tasks/${id}`, "PUT", body);
export const removeTask = (id: string) => send<void>(`/tasks/${id}`, "DELETE");
export const completeTask = (id: string) => send<Completed>(`/tasks/${id}/done`, "POST");
export const undoTask = (id: string) => send<Task>(`/tasks/${id}/undo`, "POST");

export const readGoals = () => get<Goal[]>("/goals");
export const readClosedGoals = () => get<Goal[]>("/goals?state=closed");
export const readGoal = (id: string) => get<GoalDetail>(`/goals/${id}`);
export const createGoal = (body: GoalIn) => send<Goal>("/goals", "POST", body);
export const updateGoal = (id: string, body: Partial<GoalIn>) => send<Goal>(`/goals/${id}`, "PUT", body);
export const removeGoal = (id: string) => send<void>(`/goals/${id}`, "DELETE");
export const orderGoals = (ids: string[]) => send<Goal[]>("/goals/order", "POST", { ids });
export const checkGoal = (id: string, body: CheckIn) => send<Goal>(`/goals/${id}/checks`, "POST", body);
export const uncheckGoal = (id: string, day: string) => send<Goal>(`/goals/${id}/checks/${day}`, "DELETE");
export const closeGoal = (id: string, outcome: "achieved" | "abandoned") =>
  send<Goal>(`/goals/${id}/close`, "POST", { outcome });
export const reopenGoal = (id: string) => send<Goal>(`/goals/${id}/reopen`, "POST");
export const readMetrics = () => get<Metric[]>("/metrics");

export const readSpaces = () => get<Space[]>("/spaces");
export const createSpace = (name: string) => send<Space>("/spaces", "POST", { name });
export const inviteToSpace = (space: string) =>
  send<{ code: string; expires_at: string }>(`/spaces/${space}/invites`, "POST");
export const joinSpace = (code: string) => send<Space>("/spaces/join", "POST", { code });

export const readVersion = api.readVersion;
