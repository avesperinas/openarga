import type { Translate } from "@openarga/ui";

export const ACTIONS = [
  "wash",
  "peel",
  "chop",
  "mix",
  "knead",
  "season",
  "coat",
  "fry",
  "saute",
  "boil",
  "simmer",
  "steam",
  "bake",
  "roast",
  "grill",
  "toast",
  "rest",
  "marinate",
  "chill",
  "freeze",
  "prove",
  "blend",
  "strain",
  "assemble",
  "serve",
] as const;

export const EQUIPMENT = ["hob", "oven", "air_fryer", "board", "bowl", "fridge", "none"] as const;

export const USUALLY_UNATTENDED = new Set([
  "bake",
  "roast",
  "rest",
  "marinate",
  "chill",
  "freeze",
  "prove",
  "simmer",
]);

export function actionName(t: Translate, action: string): string {
  return (ACTIONS as readonly string[]).includes(action) ? t(`action.${action}`) : action;
}

export function equipmentName(t: Translate, equipment: string): string {
  return (EQUIPMENT as readonly string[]).includes(equipment) ? t(`equipment.${equipment}`) : equipment;
}

export function whenLabel(start: number, end: number, t: Translate): string {
  return start === end ? t("when.at", { start }) : t("when.between", { start, end });
}
