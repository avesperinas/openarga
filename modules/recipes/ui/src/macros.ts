import { type Translate, numbers } from "@openarga/ui";

import type { Macros } from "./api";

const GROUPED = { useGrouping: "always" } as unknown as Intl.NumberFormatOptions;

const one = () => numbers({ ...GROUPED, maximumFractionDigits: 1 });
const whole = () => numbers({ ...GROUPED, maximumFractionDigits: 0 });

export function kcal(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : whole().format(value);
}

export function grams(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return Math.abs(value) < 10 ? one().format(value) : whole().format(value);
}

export function amount(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : one().format(value);
}

export function macroLine(macros: Macros, t: Translate): string {
  return [
    `${amount(macros.kcal)} kcal`,
    `${amount(macros.protein)} ${t("macro.p")}`,
    `${amount(macros.fat)} ${t("macro.f")}`,
    `${amount(macros.carbs)} ${t("macro.c")}`,
  ].join(" · ");
}

export function pantryLine(macros: Macros, t: Translate): string {
  return [
    `${t("macro.p")} ${grams(macros.protein)}`,
    `${t("macro.f")} ${grams(macros.fat)}`,
    `${t("macro.c")} ${grams(macros.carbs)}`,
    t("macro.per_100"),
  ].join(" · ");
}

export function sourceLabel(source: string, corrected: boolean, t: Translate): string {
  if (source === "manual") return t("source.yours");
  const name = source === "usda" ? "USDA" : "Open Food Facts";
  return corrected ? t("source.corrected", { name }) : name;
}
