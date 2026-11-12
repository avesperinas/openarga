import { createApi } from "@openarga/app";
import type { BodyWeightHistory } from "@openarga/ui";

export type Nutrients = Record<string, number>;
export type Kind = "food" | "recipe" | "quick" | "water";
export type Unit = "g" | "ml" | "unit" | "serving" | "kcal";

export interface Item {
  id: string;
  position: number;
  kind: Kind;
  name: string;
  quantity: number;
  unit: Unit;
  grams: number | null;
  estimated: boolean;
  food_id: string | null;
  recipe_id: string | null;
  nutrients: Nutrients;
  portion?: string | null;
  doubt?: "first" | "unsure" | null;
  dish?: string | null;
}

export interface Entry {
  id: string;
  eaten_at: string;
  day: string;
  said: string | null;
  origin: "claude" | "app";
  items: Item[];
  nutrients: Nutrients;
  status?: "confirmed" | "planned";
  meal: MealKey;
}

export type MealKey = "night" | "breakfast" | "morning" | "lunch" | "snack" | "dinner";

export interface Meal {
  meal: MealKey;
  label: string;
  usual_at: string;
  started: boolean;
  current: boolean;
  kcal: number;
  protein: number;
  entry_ids: string[];
  planned_ids: string[];
}

export interface Target {
  valid_from: string;
  kcal: number | null;
  protein: number | null;
  carbs: number | null;
  fat: number | null;
}

export interface Drinks {
  caffeine_mg: number | null;
  alcohol_g: number | null;
  alcohol_units: number | null;
  water_l: number;
}

export interface Day {
  day: string;
  nutrients: Nutrients;
  coverage: Record<string, number>;
  target: Target | null;
  remaining: Nutrients;
  drinks: Drinks;
  entries: Entry[];
  goals?: GoalState[];
  day_kind?: { kind: "training" | "rest"; source: "manual" | "workout" | "none"; workouts: string[] } | null;
  groups?: NutrientGroup[];
  caffeine?: CaffeineDay | null;
  planned?: Entry[];
  meals: Meal[];
  complete?: boolean;
}

export interface Template {
  id: string;
  name: string;
  items: ItemIn[];
  said: string | null;
  daily_at: string | null;
}

export interface Outdated {
  recipe_id: string;
  name: string;
  items: number;
  days: string[];
}

export type GoalStatus = "low" | "ok" | "high" | "none";

export interface GoalState {
  nutrient: string;
  name: string;
  unit: string;
  basis: "amount" | "kcal_pct";
  min: number | null;
  max: number | null;
  source: "own" | "legacy" | "efsa";
  profile: "any" | "training" | "rest";
  value: number | null;
  share: number | null;
  low: number | null;
  high: number | null;
  status: GoalStatus;
  coverage: number | null;
}

export interface NutrientGroup {
  key: string;
  name: string;
  items: {
    key: string;
    name: string;
    unit: string;
    value: number | null;
    coverage: number;
    partial: boolean;
    status: GoalStatus;
    min: number | null;
    max: number | null;
    goal_unit: "amount" | "kcal_pct" | null;
  }[];
}

export interface CaffeineDay {
  total_mg: number;
  last_at: string | null;
  now_mg: number;
  half_life_h: number;
  curve: { at: string; mg: number }[];
}

export interface Contributors {
  nutrient: string;
  name: string;
  unit: string;
  total: number | null;
  coverage: number;
  items: { name: string; value: number; share: number; times: number }[];
  without: string[];
}

export interface Reference {
  nutrient: string;
  kind: "min" | "max" | "energy_share";
  value: number;
  own: boolean;
}

export interface Micro {
  key: string;
  name: string;
  unit: string;
  value: number | null;
  coverage: number;
  reference: Reference | null;
  status: "low" | "high" | "ok" | "none";
  partial: boolean;
  missing: string[];
}

export interface DayMark {
  day: string;
  kcal: number | null;
  against_target: "over" | "under" | "on" | "none";
}

export interface Profile {
  sex: string | null;
  age: number | null;
  from_health: boolean;
}

export interface Week {
  first: string;
  last: string;
  days_logged: number;
  averages: Nutrients;
  days: DayMark[];
  micros: Micro[];
  profile: Profile;
  drinks: Drinks;
  goals?: GoalState[];
  compliance?: { nutrient: string; name: string; states: GoalStatus[] }[];
  expenditure?: Expenditure | null;
  counted?: { days: number; complete: boolean } | null;
}

export interface Trend {
  days: { day: string; kcal: number | null; complete: boolean }[];
  weeks: { first: string; last: string; counted: number }[];
  nutrients: Record<string, (number | null)[]>;
}

export interface SuggestedFood {
  food_id: string | null;
  recipe_id: string | null;
  name: string;
  portion: string;
  quantity: number;
  unit: string;
  amount: number;
  share_of_reference: number;
  times: number;
  last_eaten: string;
}

export interface Suggestions {
  window: { first: string; last: string; days: number };
  nutrients: { key: string; name: string; unit: string; average: number; reference: number; share: number; foods: SuggestedFood[] }[];
}

export interface Proposal {
  rate_kg_week: number;
  kcal: number;
  floored: boolean;
}

export interface Expenditure {
  kcal: number | null;
  days: number;
  first: string;
  last: string;
  intake: number | null;
  weight_change_kg_week: number | null;
  bmr: number | null;
  proposals: Proposal[];
  missing: string | null;
}

export interface PantryFood {
  id: string;
  name: string;
  label: string;
  source: string;
  nutrients: Nutrients;
  grams_per_unit: number | null;
  density_g_ml: number | null;
  nutrients_per?: "100g" | "unit";
  unit_name?: string | null;
  portions?: Record<string, number>;
}

export interface Candidate {
  source: "usda" | "off";
  source_ref: string;
  name: string;
  brand: string | null;
  nutrients: Nutrients;
}

export interface RecipeRef {
  id: string;
  name: string;
  servings: number;
}

export interface Found {
  foods: PantryFood[];
  candidates: Candidate[];
  failed: { source: string; reason: string }[];
  recipes: RecipeRef[];
}

export interface NutrientInfo {
  key: string;
  name: string;
  unit: string;
  group: string;
  front: boolean;
  digits: number;
}

export interface ItemIn {
  kind: Kind;
  food_id?: string;
  source?: string;
  source_ref?: string;
  recipe_id?: string;
  name?: string;
  quantity: number;
  unit: Unit;
  quick?: { protein?: number; carbs?: number; fat?: number };
  portion?: string;
  dish?: string;
}

export { Unauthorised, problemOf, signIn } from "@openarga/app";

export const api = createApi("macros");
const { get, send } = api;
export const readVersion = api.readVersion;

export const readDay = (day: string) => get<Day>(`/day?day=${day}`);
export const confirmEntry = (id: string) => send<Entry>(`/entries/${id}/confirm`, "POST", {});
export const unconfirmEntry = (id: string) => send<Entry>(`/entries/${id}/unconfirm`, "POST");
export const renameDish = (entry: string, from: string, to: string | null) =>
  send<Entry>(`/entries/${entry}/dish`, "PUT", { from, to });
export const dishToRecipe = (entry: string, dish: string) =>
  send<{ recipe_id: string; version_id: string; skipped: number }>(`/entries/${entry}/dish/recipe`, "POST", { dish });
export const readTemplates = () => get<Template[]>("/templates");
export const saveTemplate = (body: Pick<Template, "name" | "items" | "said" | "daily_at">) =>
  send<Template>("/templates", "POST", body);
export const removeTemplate = (id: string) => send<void>(`/templates/${id}`, "DELETE");
export const logTemplate = (id: string, meal?: MealKey, eatenAt?: string) =>
  send<Entry>(`/templates/${id}/log`, "POST", { meal, eaten_at: eatenAt });
export const templateFromEntry = (entryId: string, name: string, dailyAt: string | null) =>
  send<Template>(`/templates/from-entry/${entryId}`, "POST", { name, daily_at: dailyAt });
export const readOutdated = () => get<Outdated[]>("/recipes/outdated");
export const recalculateRecipe = (id: string) =>
  send<{ items: number; days: string[] }>(`/recipes/${id}/recalculate`, "POST", {});
export const readContributors = (day: string, nutrient: string) =>
  get<Contributors>(`/day/${day}/contributors/${nutrient}`);
export const readWeek = (last: string, all = false) => get<Week>(`/week?last=${last}&all=${all}`);
export const readTrend = (last: string, weeks = 8) => get<Trend>(`/week/trend?last=${last}&weeks=${weeks}`);
export const readSuggestions = (last: string) => get<Suggestions>(`/week/suggestions?last=${last}`);
export const readWeekContributors = (last: string, nutrient: string) =>
  get<Contributors>(`/week/contributors/${nutrient}?last=${last}`);
export const readNutrients = () => get<NutrientInfo[]>("/nutrients");
export const search = (q: string, outside = true) =>
  get<Found>(`/search?q=${encodeURIComponent(q)}&outside=${outside}`);

export const logEntry = (items: ItemIn[], eatenAt?: string, meal?: MealKey) =>
  send<Entry>("/entries", "POST", { items, eaten_at: eatenAt, meal });
export const changeItem = (entry: string, item: string, quantity: number) =>
  send<Entry>(`/entries/${entry}`, "PATCH", { change: [{ item_id: item, quantity, estimated: false }] });
export const swapItem = (
  entry: string,
  item: string,
  to: { food_id: string } | { source: string; source_ref: string } | { recipe_id: string },
) => send<Entry>(`/entries/${entry}`, "PATCH", { swap: [{ item_id: item, ...to }] });
export interface Measure {
  name: string;
  grams: number;
}
export const readMeasures = (item: string) => get<{ item_id: string; measures: Measure[] }>(`/items/${item}/measures`);
export const moveEntry = (entry: string, eatenAt: string) =>
  send<Entry>(`/entries/${entry}`, "PATCH", { eaten_at: eatenAt });
export const removeEntry = (entry: string) => send<void>(`/entries/${entry}`, "DELETE");
export const repeatEntry = (entry: string) => send<Entry>(`/entries/${entry}/repeat`, "POST");
export const repeatMeal = (fromDay: string, meal: MealKey, day?: string) =>
  send<Entry>("/meals/repeat", "POST", { from_day: fromDay, meal, day });
export const moveMeal = (day: string, meal: MealKey, at: string) =>
  send<Entry[]>(`/meals/${day}/${meal}/time`, "PUT", { at });
export const removeMeal = (day: string, meal: MealKey) => send<void>(`/meals/${day}/${meal}`, "DELETE");
export const moveItem = (item: string, meal: MealKey) => send<Entry>(`/items/${item}/move`, "POST", { meal });
export const menuFromMeal = (day: string, meal: MealKey, name: string, dailyAt: string | null) =>
  send<Template>("/templates/from-meal", "POST", { day, meal, name, daily_at: dailyAt });
export interface UsualItem {
  name: string;
  kind: Kind;
  food_id: string | null;
  recipe_id: string | null;
  quantity: number;
  unit: Unit;
  grams: number | null;
  kcal: number | null;
  times: number;
  item_id: string;
  last_day: string;
  portion?: string | null;
}

export interface UsualOfMeal {
  meal: MealKey;
  label: string;
  day: string;
  yesterday: UsualItem[];
  usual: { label: string; times: number; kcal: number; item_ids: string[] } | null;
  items: UsualItem[];
  recent: UsualItem[];
  menus: Template[];
}

export const readUsualOf = (meal: MealKey, day: string) => get<UsualOfMeal>(`/usual/${meal}?day=${day}`);
export const repeatItems = (itemIds: string[], meal: MealKey, day: string) =>
  send<Entry>("/items/repeat", "POST", { item_ids: itemIds, meal, day });
export const itemIsSure = (item: string) => send<Entry>(`/items/${item}/sure`, "POST");
export const removeItem = (item: string) => send<{ entry: Entry | null }>(`/items/${item}`, "DELETE");
export const duplicateItem = (item: string) => send<Entry>(`/items/${item}/duplicate`, "POST");

export interface GoalInfo {
  nutrient: string;
  name: string;
  min: number | null;
  max: number | null;
  unit: "amount" | "kcal_pct" | "per_kg";
  nutrient_unit: string;
  kg?: number;
  amount?: { min: number | null; max: number | null };
  source: "own" | "legacy" | "efsa";
  profile: "any" | "training" | "rest";
  valid_from: string | null;
}

export interface DayKindInfo {
  day: string;
  kind: "training" | "rest";
  source: "manual" | "workout" | "none";
  workouts: string[];
}

export const readGoals = (day?: string) =>
  get<{ day_kind: DayKindInfo; goals: GoalInfo[] }>(`/goals${day ? `?day=${day}` : ""}`);
export const saveGoal = (
  nutrient: string,
  body: { min: number | null; max: number | null; unit: GoalInfo["unit"]; profile: GoalInfo["profile"] },
) => send<unknown>(`/goals/${nutrient}`, "PUT", body);
export const resetGoal = (nutrient: string, profile: GoalInfo["profile"]) =>
  send<unknown>(`/goals/${nutrient}?profile=${profile}`, "DELETE");
export const setDayComplete = (day: string, complete: boolean) =>
  send<{ day: string; complete: boolean }>(`/day-complete/${day}`, "PUT", { complete });
export const setDayKind = (day: string, kind: DayKindInfo["kind"] | null) =>
  send<DayKindInfo>(`/day-kind/${day}`, "PUT", { kind });
export const readTarget = () => get<Target | null>("/target");
export const saveTarget = (body: Partial<Target>) => send<Target>("/target", "PUT", body);
export const readReferences = () => get<{ profile: Profile; references: Reference[] }>("/references");
export const saveReference = (nutrient: string, kind: Reference["kind"], value: number) =>
  send<void>(`/references/${nutrient}`, "PUT", { kind, value });
export const resetReference = (nutrient: string) => send<void>(`/references/${nutrient}`, "DELETE");

export const readWeight = () => get<BodyWeightHistory>("/weight");
export const logWeight = (kg: number) => send<BodyWeightHistory>("/weight", "POST", { kg });

export interface Settings {
  protein_at: string;
}

export const readSettings = () => get<Settings>("/settings");
export const saveSettings = (protein_at: string) => send<Settings>("/settings", "PUT", { protein_at });
