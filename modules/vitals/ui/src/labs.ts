import type { Locale, Translate } from "@openarga/ui";

import type { Analyte, Cell } from "./api";

export const PANELS: Analyte["panel"][] = ["lipids", "biochemistry", "blood_count", "urine", "other"];

export const panelName = (t: Translate, panel: Analyte["panel"]) => t(`panel.${panel}`);

export function analyteName(t: Translate, analyte: Pick<Analyte, "id" | "name">): string {
  const key = `analyte.${analyte.id}.name`;
  const found = t(key);
  return found === key ? analyte.name : found;
}

export function number(value: number, locale: Locale, unit?: string | null): string {
  const digits = Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 2;
  const text = value.toLocaleString(locale, { maximumFractionDigits: digits });
  return unit ? `${text} ${unit}` : text;
}

export function cellText(cell: Cell, locale: Locale): string {
  if (cell.value === null) return cell.value_text ?? "";
  const arrow = !cell.out
    ? ""
    : cell.ref_high !== null && cell.value > cell.ref_high
      ? " ↑"
      : " ↓";
  return `${number(cell.value, locale)}${arrow}`;
}

export function cellShort(cell: Cell, locale: Locale): string {
  const text = cellText(cell, locale);
  return cell.value === null && text.length > 5 ? `${text.slice(0, 3)}.` : text;
}

export function rangeText(low: number | null, high: number | null, locale: Locale, unit?: string | null): string {
  const suffix = unit ? ` ${unit}` : "";
  if (low !== null && high !== null && low > 0) return `${number(low, locale)}–${number(high, locale)}${suffix}`;
  if (high !== null) return `≤ ${number(high, locale)}${suffix}`;
  if (low !== null) return `≥ ${number(low, locale)}${suffix}`;
  return "";
}

export function parseNumber(text: string): number | null {
  if (!text.trim()) return null;
  const value = Number(text.trim().replace(",", "."));
  return Number.isFinite(value) ? value : null;
}
