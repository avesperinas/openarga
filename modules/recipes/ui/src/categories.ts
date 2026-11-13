import type { Translate } from "@openarga/ui";

const BUILT_IN = new Set([
  "vegetable",
  "fruit",
  "protein",
  "fish",
  "dairy",
  "grain",
  "legume",
  "fat",
  "spice",
  "sweet",
  "liquid",
  "other",
  "supplement",
]);

export function categoryName(t: Translate, id: string, name: string): string {
  return BUILT_IN.has(id) ? t(`category.${id}`) : name;
}
