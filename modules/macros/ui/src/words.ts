import { type Locale, type Translate, numbers, regional, zonedDates } from "@openarga/ui";

import type { Drinks, Item, Meal, MealKey } from "./api";

const GROUPED = { useGrouping: "always" } as unknown as Intl.NumberFormatOptions;

export type Row = { kind: "item"; item: Item } | { kind: "dish"; name: string; items: Item[] };

export function rows(items: Item[]): Row[] {
  const out: Row[] = [];
  for (const item of items) {
    const last = out.at(-1);
    if (item.dish && last?.kind === "dish" && last.name === item.dish) last.items.push(item);
    else if (item.dish) out.push({ kind: "dish", name: item.dish, items: [item] });
    else out.push({ kind: "item", item });
  }
  return out;
}

export function amount(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return numbers({ ...GROUPED, maximumFractionDigits: digits }).format(value);
}

export function plural(t: Translate, key: string, count: number, vars: Record<string, string | number> = {}): string {
  return t(`${key}.${count === 1 ? "one" : "other"}`, { count, ...vars });
}

type Quantity = Pick<Item, "quantity" | "unit" | "estimated"> & { portion?: string | null };

export function quantityLabel(item: Quantity, t: Translate, locale: Locale): string {
  const text =
    item.portion && item.unit === "unit"
      ? measureCount(item.quantity, item.portion, locale)
      : item.unit === "serving"
        ? plural(t, "unit.serving", item.quantity, { amount: amount(item.quantity) })
        : `${amount(item.quantity)} ${t(`unit.${item.unit}`)}`;
  return item.estimated ? `≈ ${text}` : text;
}

export function itemTag(item: Pick<Item, "kind">, t: Translate): string | undefined {
  if (item.kind === "recipe") return t("tag.recipe");
  if (item.kind === "quick") return t("tag.quick");
  return undefined;
}

export function timeOf(iso: string): string {
  return zonedDates({ hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

export function clockOf(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: regional().timeZone });
}

export function todayIso(now = new Date()): string {
  return now.toLocaleDateString("sv-SE", { timeZone: regional().timeZone });
}

export function shiftDay(day: string, by: number): string {
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  const moved = new Date(Date.UTC(y, m - 1, d + by));
  return moved.toISOString().slice(0, 10);
}

export function dayTitle(day: string, today: string, t: Translate, locale: Locale): string {
  if (day === today) return t("day.today");
  if (day === shiftDay(today, -1)) return t("day.yesterday");
  return longDate(day, locale);
}

export function remainingLabel(left: number, unit: string, t: Translate): string {
  const value = `${amount(Math.abs(left), 0)} ${unit}`;
  return left >= 0 ? t("remaining.left", { value }) : t("remaining.over", { value });
}

export function drinksLine(drinks: Drinks, t: Translate): string {
  const parts = [];
  if (drinks.caffeine_mg !== null) parts.push(t("drinks.caffeine", { mg: amount(drinks.caffeine_mg, 0) }));
  if (drinks.alcohol_g !== null) {
    parts.push(t("drinks.alcohol", { units: amount(drinks.alcohol_units), grams: amount(drinks.alcohol_g) }));
  }
  parts.push(t("drinks.water", { litres: amount(drinks.water_l) }));
  return parts.join(" · ");
}

export function longDate(day: string, locale: Locale): string {
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  const text = new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(locale, {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function mealLine(meal: Pick<Meal, "kcal" | "protein">, t: Translate): string {
  return t("meal.line", { kcal: amount(meal.kcal, 0), protein: amount(meal.protein, 0) });
}

const MEAL_STARTS: [string, MealKey][] = [
  ["00:00", "night"],
  ["04:00", "breakfast"],
  ["10:30", "morning"],
  ["13:00", "lunch"],
  ["17:00", "snack"],
  ["20:00", "dinner"],
];

export function mealOfTime(hhmm: string): MealKey {
  let found: MealKey = "night";
  for (const [start, meal] of MEAL_STARTS) if (hhmm >= start) found = meal;
  return found;
}

export function nowTime(now = new Date()): string {
  return now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: regional().timeZone });
}

export function withThis(
  kcal: number,
  protein: number,
  target: { kcal: number | null; protein: number | null },
  t: Translate,
): string {
  const energy = target.kcal
    ? t("with_this.kcal_of", { value: amount(kcal, 0), target: amount(target.kcal, 0) })
    : t("with_this.kcal", { value: amount(kcal, 0) });
  const body = target.protein
    ? t("with_this.protein_of", { value: amount(protein, 0), target: amount(target.protein, 0) })
    : t("with_this.protein", { value: amount(protein, 0) });
  return t("with_this.line", { energy, protein: body });
}

export function measureCount(quantity: number, name: string, locale: Locale): string {
  if (quantity === 1) return `1 ${name}`;
  const many =
    locale === "es"
      ? /[aeiou\u00e1\u00e9\u00f3]$/i.test(name)
        ? `${name}s`
        : /s$/i.test(name)
          ? name
          : `${name}es`
      : /s$/i.test(name)
        ? name
        : `${name}s`;
  return `${amount(quantity)} ${many}`;
}

export function doubtLine(doubt: "first" | "unsure" | null | undefined, t: Translate): string | undefined {
  if (doubt === "first") return t("doubt.first");
  if (doubt === "unsure") return t("doubt.unsure");
  return undefined;
}
