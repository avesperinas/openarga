import { createApi, invalidate } from "@openarga/app";

export { Unauthorised, problemOf, signIn } from "@openarga/app";

export const api = createApi("recipes");
const { get, send } = api;

export function changed(): void {
  for (const key of ["recipes", "recipe:", "foods"]) invalidate(key);
}

export interface Category {
  id: string;
  name: string;
  emoji: string;
  position: number;
}

export interface RecipeSummary {
  id: string;
  name: string;
  servings: number;
  version: number;
  tags: string[];
  total_minutes: number | null;
  active_minutes: number | null;
  space_id: string | null;
  mine: boolean;
  archived?: boolean;
}

export interface Macros {
  kcal: number;
  protein: number;
  fat: number;
  carbs: number;
  fiber: number | null;
  salt: number | null;
}

export interface Food {
  id: string;
  name: string;
  alias: string | null;
  source: "usda" | "off" | "manual";
  source_ref: string | null;
  category_id: string;
  macros: Macros;
  density_g_ml: number | null;
  grams_per_unit: number | null;
  corrected: boolean;
  provenance?: string | null;
  micros_from?: string | null;
  micros_from_label?: string | null;
  borrowed?: string[];
  edible_fraction?: number | null;
  portions?: { name: string; grams: number }[];
  nutrients_per?: "100g" | "unit";
  unit_name?: string | null;
}

export interface Candidate {
  source: "usda" | "off";
  source_ref: string;
  name: string;
  brand: string | null;
  macros: Macros;
  category_hint: string;
  known_id: string | null;
}

export interface SearchOut {
  candidates: Candidate[];
  failed: { source: string; reason: string }[];
  discarded?: { source: string; name: string; reason: string }[];
}

export interface Tag {
  id: string;
  name: string;
  emoji: string | null;
}

export interface Ingredient {
  position: number;
  name: string;
  food_id: string | null;
  category_id: string;
  quantity: number;
  unit: Unit;
  note: string | null;
  optional: boolean;
  grams: number | null;
  portion?: string | null;
  as_purchased?: boolean;
}

export interface Group {
  category_id: string;
  name: string;
  emoji: string;
  ingredients: Ingredient[];
}

export interface Nutrition {
  total: Macros;
  per_serving: Macros;
  counted: number;
  ingredients: number;
  uncertainty: string | null;
  nutrients?: Record<string, number>;
  coverage?: Record<string, number>;
}

export interface NutrientInfo {
  key: string;
  name: string;
  unit: string;
  group: string;
  front: boolean;
  digits: number;
}

export function readNutrients(): Promise<NutrientInfo[]> {
  return get<NutrientInfo[]>("/nutrients");
}

export interface ScheduledStep {
  position: number;
  action: string;
  text: string;
  minutes: number;
  attended: boolean;
  equipment: string;
  ingredients: string[];
  uses: number[];
  after: number[];
  start: number;
  end: number;
}

export interface GridRow {
  position: number;
  name: string;
  orphan: boolean;
}

export interface GridCell {
  position: number;
  action: string;
  text: string;
  minutes: number;
  attended: boolean;
  equipment: string;
  column: number;
  row: number;
  span: number;
}

export interface GridBand {
  position: number;
  action: string;
  text: string;
  minutes: number;
  attended: boolean;
  equipment: string;
}

export interface RecipeGridData {
  rows: GridRow[];
  cells: GridCell[];
  bands: GridBand[];
  columns: number;
  notes: string[];
}

export interface Kitchen {
  steps: ScheduledStep[];
  grid: RecipeGridData;
  total_minutes: number;
  active_minutes: number;
  lanes: string[];
  overlaps: { equipment: string; positions: number[] }[];
}

export interface StepIn {
  action: string;
  text: string;
  minutes: number;
  attended: boolean;
  equipment: string;
  after: number[];
  ingredients: number[];
}

export interface Recipe {
  id: string;
  name: string;
  servings: number;
  requested_servings: number;
  version: number;
  versions: number;
  source: "app" | "tool";
  note: string | null;
  tags: Tag[];
  groups: Group[];
  nutrition: Nutrition;
  kitchen: Kitchen;
  space_id: string | null;
  mine: boolean;
  archived?: boolean;
}

export type Unit = "g" | "ml" | "unit" | "tbsp" | "tsp" | "pinch";

export interface IngredientIn {
  food_id?: string | null;
  name?: string | null;
  quantity: number;
  unit: Unit;
  note?: string | null;
  optional?: boolean;
  portion?: string | null;
  as_purchased?: boolean;
}

export interface RecipeIn {
  name: string;
  servings: number;
  ingredients: IngredientIn[];
  steps: StepIn[];
  tags: string[];
  note?: string | null;
}

export interface Space {
  id: string;
  name: string;
  me: string;
  members: { user_id: string; name: string | null }[];
}

export const readSpaces = () => api.raw<Space[]>("/api/kernel/spaces");

export const shareRecipe = (id: string, spaceId: string | null) =>
  send<Recipe>(`/recipes/${id}/space`, "PUT", { space_id: spaceId });

export const readCategories = () => get<Category[]>("/categories");
export const readRecipes = () => get<RecipeSummary[]>("/recipes");
export const readFoods = () => get<Food[]>("/foods");
export const searchFoods = (query: string) =>
  get<SearchOut>(`/foods/search?q=${encodeURIComponent(query)}`);
export const importFood = (body: {
  source: string;
  source_ref: string;
  name: string;
  category_id: string;
  macros: Macros;
  alias?: string | null;
}) => send<Food>("/foods", "POST", body);
export const setFoodAlias = (id: string, alias: string | null) =>
  send<Food>(`/foods/${id}/alias`, "PUT", { alias });

export interface Replaced {
  recipes: { recipe_id: string; name: string; version: number }[];
  skipped: { recipe_id: string; name: string; reason: string }[];
  macros: { done: boolean; items?: number; days?: string[]; note?: string };
}

export const replaceFood = (id: string, newId: string) =>
  send<Replaced>(`/foods/${id}/replace`, "POST", { new_id: newId });

export const labelOf = (food: Pick<Food, "name" | "alias">): string => food.alias ?? food.name;
export const readRecipe = (id: string, servings?: number) =>
  get<Recipe>(`/recipes/${id}${servings ? `?servings=${servings}` : ""}`);
export const createRecipe = (body: RecipeIn) => send<Recipe>("/recipes", "POST", body);
export const updateRecipe = (id: string, body: RecipeIn) =>
  send<Recipe>(`/recipes/${id}`, "PUT", body);
export const readTags = () => get<Tag[]>("/tags");

export const deleteRecipe = (id: string) => send<void>(`/recipes/${id}`, "DELETE");
export const archiveRecipe = (id: string) => send<void>(`/recipes/${id}/archive`, "POST");
export const unarchiveRecipe = (id: string) => send<void>(`/recipes/${id}/unarchive`, "POST");
export const readArchived = () => get<RecipeSummary[]>("/recipes?archived=true");

export const createManualFood = (body: {
  name: string;
  category_id: string;
  macros: Macros;
  grams_per_unit?: number | null;
  density_g_ml?: number | null;
}) => send<Food>("/foods/manual", "POST", body);

export const readVersion = api.readVersion;

export interface ShoppingAdded {
  added: { name: string; already_on_list: boolean }[];
  pending: number;
}

export const addToShoppingList = (id: string, body: { servings: number; positions: number[] }) =>
  send<ShoppingAdded>(`/recipes/${id}/shopping`, "POST", body);
