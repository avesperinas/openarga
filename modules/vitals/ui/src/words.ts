import type { Locale, Translate } from "@openarga/ui";

export function unitName(t: Translate, unit: string): string {
  const key = `unit.${unit}`;
  const found = t(key);
  return found === key ? unit : found;
}

export const plural = (t: Translate, key: string, count: number, vars: Record<string, string | number> = {}) =>
  t(`${key}.${count === 1 ? "one" : "other"}`, { count, ...vars });

export const decimal = (value: number, locale: Locale, digits = 1): string =>
  new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(value);

export const fixed = (value: number, locale: Locale, digits = 1): string =>
  new Intl.NumberFormat(locale, { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
