import { type Translate, numbers } from "@openarga/ui";

import type { Unit } from "./api";

export const UNITS: Unit[] = ["g", "ml", "unit", "tbsp", "tsp", "pinch"];

export const unitName = (t: Translate, unit: Unit): string => t(`unit.${unit}`);

export const unitShort = (t: Translate, unit: Unit): string => t(`unit_short.${unit}`);

export function quantityLabel(quantity: number, unit: Unit, t: Translate): string {
  return `${numbers({ maximumFractionDigits: 2 }).format(quantity)} ${UNITS.includes(unit) ? unitShort(t, unit) : unit}`;
}
