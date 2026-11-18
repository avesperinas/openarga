import type { PositionBody } from "./api";

export interface PositionDraft {
  symbol: string;
  name: string;
  units: string;
  cost: string;
  price: string;
  priceOn: string;
}

export const EMPTY_DRAFT: PositionDraft = { symbol: "", name: "", units: "", cost: "", price: "", priceOn: "" };

const ISIN = /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/;

export function symbolOf(text: string): string {
  return text.replace(/\s/g, "").toUpperCase();
}

export function looksLikeIsin(symbol: string): boolean {
  return ISIN.test(symbol);
}

export function decimalOf(text: string, places: number, mark: string): string | null {
  const clean = text.replace(/\s/g, "");
  if (!clean) return null;
  const group = mark === "," ? /\.(?=\d{3}(\D|$))/g : /,(?=\d{3}(\D|$))/g;
  const plain = clean.replace(group, "").replace(",", ".");
  if (!new RegExp(`^\\d+(\\.\\d{1,${places}})?$`).test(plain)) return null;
  return plain;
}

export function bodyOf(draft: PositionDraft, mark: string, today: string): PositionBody | null {
  const symbol = symbolOf(draft.symbol);
  const units = decimalOf(draft.units, 4, mark);
  const cost = decimalOf(draft.cost, 2, mark);
  if (!symbol || units === null || Number(units) <= 0 || cost === null) return null;
  const body: PositionBody = { symbol, name: draft.name.trim(), units, cost };
  if (draft.price.trim()) {
    const price = decimalOf(draft.price, 4, mark);
    if (price === null || !draft.priceOn || draft.priceOn > today) return null;
    body.price = price;
    body.price_on = draft.priceOn;
  }
  return body;
}

export function draftOf(row: { symbol: string; name: string; units: number; cost: number }): PositionDraft {
  return { ...EMPTY_DRAFT, symbol: row.symbol, name: row.name, units: String(row.units), cost: String(row.cost) };
}
