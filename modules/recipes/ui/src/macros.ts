import type { Macros } from "./api";

export const MACRO_LABELS: { key: keyof Macros; label: string; unit: string }[] = [
  { key: "kcal", label: "kcal", unit: "" },
  { key: "protein", label: "Proteína", unit: "g" },
  { key: "fat", label: "Grasa", unit: "g" },
  { key: "carbs", label: "Hidratos", unit: "g" },
];

const GROUPED = { useGrouping: "always" } as unknown as Intl.NumberFormatOptions;
const NUMBER = new Intl.NumberFormat("es-ES", { ...GROUPED, maximumFractionDigits: 1 });
const WHOLE = new Intl.NumberFormat("es-ES", { ...GROUPED, maximumFractionDigits: 0 });

export function kcal(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : WHOLE.format(value);
}

export function grams(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return Math.abs(value) < 10 ? NUMBER.format(value) : WHOLE.format(value);
}

export function amount(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : NUMBER.format(value);
}

export function macroLine(macros: Macros): string {
  return [
    `${amount(macros.kcal)} kcal`,
    `${amount(macros.protein)} P`,
    `${amount(macros.fat)} G`,
    `${amount(macros.carbs)} H`,
  ].join(" · ");
}

export function pantryLine(macros: Macros): string {
  return [`P ${grams(macros.protein)}`, `G ${grams(macros.fat)}`, `H ${grams(macros.carbs)}`, "por 100 g"].join(" · ");
}

export function sourceLabel(source: string, corrected: boolean): string {
  if (source === "manual") return "tuyo";
  const name = source === "usda" ? "USDA" : "OpenFoodFacts";
  return corrected ? `${name}, corregido` : name;
}
