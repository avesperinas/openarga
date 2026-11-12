import type { Drinks, Item, Meal, MealKey, Unit } from "./api";

const GROUPED = { useGrouping: "always" } as unknown as Intl.NumberFormatOptions;
const ONE = new Intl.NumberFormat("es-ES", { ...GROUPED, maximumFractionDigits: 1 });
const NONE = new Intl.NumberFormat("es-ES", { ...GROUPED, maximumFractionDigits: 0 });

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
  return (digits === 0 ? NONE : ONE).format(value);
}

const SHORT: Record<Unit, string> = { g: "g", ml: "ml", unit: "ud", serving: "rac.", kcal: "kcal" };

export function quantityLabel(item: Pick<Item, "quantity" | "unit" | "estimated"> & { portion?: string | null }): string {
  if (item.portion && item.unit === "unit") {
    const text = measureCount(item.quantity, item.portion);
    return item.estimated ? `≈ ${text}` : text;
  }
  const unit = item.unit === "serving" && item.quantity === 1 ? "ración" : SHORT[item.unit];
  const text = `${amount(item.quantity)} ${item.unit === "serving" && item.quantity !== 1 ? "raciones" : unit}`;
  return item.estimated ? `≈ ${text}` : text;
}

export function itemTag(item: Pick<Item, "kind">): string | undefined {
  if (item.kind === "recipe") return "receta";
  if (item.kind === "quick") return "a ojo";
  return undefined;
}

export function timeOf(iso: string): string {
  return new Date(iso).toLocaleTimeString("es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Madrid",
  });
}

export function todayIso(now = new Date()): string {
  return now.toLocaleDateString("sv-SE", { timeZone: "Europe/Madrid" });
}

export function shiftDay(day: string, by: number): string {
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  const moved = new Date(Date.UTC(y, m - 1, d + by));
  return moved.toISOString().slice(0, 10);
}

export function dayTitle(day: string, today: string): string {
  if (day === today) return "Hoy";
  if (day === shiftDay(today, -1)) return "Ayer";
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  const text = new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("es-ES", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function remainingLabel(left: number, unit: string): string {
  return left >= 0 ? `quedan ${amount(left, 0)} ${unit}` : `te pasas ${amount(-left, 0)} ${unit}`;
}

export function drinksLine(drinks: Drinks): string {
  const parts = [];
  if (drinks.caffeine_mg !== null) parts.push(`${amount(drinks.caffeine_mg, 0)} mg de cafeína`);
  if (drinks.alcohol_g !== null) {
    parts.push(`${amount(drinks.alcohol_units)} ud de alcohol (${amount(drinks.alcohol_g)} g)`);
  }
  parts.push(`${amount(drinks.water_l)} l de agua`);
  return parts.join(" · ");
}

export function longDate(day: string): string {
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  const text = new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("es-ES", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function mealLine(meal: Pick<Meal, "kcal" | "protein">): string {
  return `${amount(meal.kcal, 0)} kcal · ${amount(meal.protein, 0)} g de proteína`;
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
  return now.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Europe/Madrid" });
}

export function withThis(kcal: number, protein: number, target: { kcal: number | null; protein: number | null }): string {
  const energy = target.kcal ? `${amount(kcal, 0)} de ${amount(target.kcal, 0)} kcal` : `${amount(kcal, 0)} kcal`;
  const body = target.protein
    ? `${amount(protein, 0)} de ${amount(target.protein, 0)} g de proteína`
    : `${amount(protein, 0)} g de proteína`;
  return `Con esto: ${energy} · ${body}`;
}

export function measureCount(quantity: number, name: string): string {
  if (quantity === 1) return `1 ${name}`;
  const plural = /[aeiouáéó]$/i.test(name) ? `${name}s` : /s$/i.test(name) ? name : `${name}es`;
  return `${amount(quantity)} ${plural}`;
}

export function doubtLine(doubt: "first" | "unsure" | null | undefined): string | undefined {
  if (doubt === "first") return "¿Es este? Primera vez que lo apuntas";
  if (doubt === "unsure") return "¿Es este? Claude no lo tenía claro";
  return undefined;
}
