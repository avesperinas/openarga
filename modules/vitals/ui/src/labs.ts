import type { Analyte, Cell } from "./api";

export const PANELS: { id: Analyte["panel"]; label: string }[] = [
  { id: "lipidos", label: "Lípidos" },
  { id: "bioquimica", label: "Bioquímica" },
  { id: "hemograma", label: "Hemograma" },
  { id: "orina", label: "Orina" },
  { id: "otros", label: "Otros" },
];

export function number(value: number, unit?: string | null): string {
  const digits = Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 2;
  const text = value.toLocaleString("es-ES", { maximumFractionDigits: digits });
  return unit ? `${text} ${unit}` : text;
}

export function cellText(cell: Cell): string {
  if (cell.value === null) return cell.value_text ?? "";
  const arrow = !cell.out
    ? ""
    : cell.ref_high !== null && cell.value > cell.ref_high
      ? " ↑"
      : " ↓";
  return `${number(cell.value)}${arrow}`;
}

export function cellShort(cell: Cell): string {
  const text = cellText(cell);
  return cell.value === null && text.length > 5 ? `${text.slice(0, 3)}.` : text;
}

export function rangeText(low: number | null, high: number | null, unit?: string | null): string {
  const suffix = unit ? ` ${unit}` : "";
  if (low !== null && high !== null && low > 0) return `${number(low)}–${number(high)}${suffix}`;
  if (high !== null) return `≤ ${number(high)}${suffix}`;
  if (low !== null) return `≥ ${number(low)}${suffix}`;
  return "";
}

export function parseNumber(text: string): number | null {
  if (!text.trim()) return null;
  const value = Number(text.trim().replace(",", "."));
  return Number.isFinite(value) ? value : null;
}
