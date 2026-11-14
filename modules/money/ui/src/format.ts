import { type IconName, type Translate, createT, dates, numbers, regional, resolveLocale } from "@openarga/ui";

import type { Category, Movement, Nature, Ownership, Payer, Status } from "./api";
import { catalogs } from "./i18n";

export const say: Translate = (key, vars) => createT(catalogs, resolveLocale(regional().locale))(key, vars);

function currencyFormat(digits: number): Intl.NumberFormat {
  return numbers({
    style: "currency",
    currency: regional().currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    useGrouping: "always",
  } as unknown as Intl.NumberFormatOptions);
}

export function moneyWhole(value: number, signed = false): string {
  const text = currencyFormat(0).format(Math.abs(value));
  if (!signed || Math.round(value) === 0) return text;
  return `${value < 0 ? "−" : "+"}${text}`;
}

export function money(value: number, signed = true): string {
  const text = currencyFormat(2).format(Math.abs(value));
  if (!signed || value === 0) return text;
  return `${value < 0 ? "−" : "+"}${text}`;
}

export function currencySymbol(): string {
  const part = currencyFormat(0)
    .formatToParts(0)
    .find((one) => one.type === "currency");
  return part?.value ?? regional().currency;
}

export function capital(text: string): string {
  return text ? `${text[0]?.toUpperCase()}${text.slice(1)}` : text;
}

export function monthName(month: number): string {
  if (month < 1 || month > 12) return "";
  return dates({ month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2000, month - 1, 1)));
}

export function parseDay(iso: string): Date {
  const [y = 1970, m = 1, d = 1] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function isoDay(date: Date): string {
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${m}-${d}`;
}

export function dayTitle(iso: string, today = new Date()): string {
  const date = parseDay(iso);
  const sameYear = date.getFullYear() === today.getFullYear();
  return capital(dates({ weekday: "long", day: "numeric", month: "long", ...(sameYear ? {} : { year: "numeric" }) }).format(date));
}

export function shortDay(iso: string): string {
  return dates({ day: "numeric", month: "short" }).format(parseDay(iso)).replace(".", "");
}

export function monthTitle(year: number, month: number): string {
  return capital(dates({ month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(year, month - 1, 1))));
}

const TYPES = new Set(["current", "savings", "fund", "etf", "pension", "crypto", "real_estate", "deposit"]);
const GROUPS = new Set(["Cash", "Funds", "Stocks", "Pension", "Crypto", "Property", "Deposits"]);

export const typeName = (type: string, fallback = type): string => (TYPES.has(type) ? say(`type.${type}`) : fallback);
export const groupName = (group: string): string => (GROUPS.has(group) ? say(`group.${group}`) : group);

export const natureName = (nature: Nature): string => say(`nature.${nature}`);
export const ownershipName = (ownership: Ownership): string => say(`ownership.${ownership}`);

export function payerLabel(payer: Payer | null, me: string, other: string): string {
  if (payer === "account") return say("payer.account");
  if (payer === "me") return me;
  if (payer === "other") return other;
  return "";
}

export const statusName = (status: Status): string => say(`status.${status}`);

export function title(m: Movement): string {
  if (m.kind === "transfer" && m.transfer) {
    if (m.transfer.basis === "other_member") return say("movement.contribution_of", { name: m.transfer.name });
    if (m.transfer.account === m.account) return say("movement.product_change");
    return say(m.amount < 0 ? "movement.to" : "movement.from", { name: m.transfer.name });
  }
  return m.merchant;
}

export function subtitle(m: Movement): string {
  if (m.kind === "transfer") return say("status.transfer");
  if (m.status === "ask") return say("movement.cash_to_label");
  if (m.status === "pending") return say("status.pending");
  if (m.status === "return") return say("status.return");
  if (m.status === "settlement") return say("movement.settlement");
  const cats = m.parts.map((p) => p.category_name);
  const unique = [...new Set(cats)];
  const label = unique.length > 2 ? say("list.more", { first: unique.slice(0, 2).join(", "), count: unique.length - 2 }) : unique.join(", ");
  const shared = m.parts.some((p) => p.ownership === "shared");
  return shared ? say("movement.shared_suffix", { label }) : label;
}

const ICONS: [RegExp, IconName][] = [
  [/rent|housing|home|alquiler|vivienda|hogar|casa/i, "home"],
  [/super|grocer|shopping|compra/i, "basket"],
  [/\bcat\b|\bpet|\bdog|gato|mascota|perro/i, "paw"],
  [/health|pharmac|doctor|salud|farmacia|m\u00e9dic|medic/i, "heart"],
  [/travel|holiday|viaje/i, "plane"],
  [/transport|fuel|petrol|\bcar\b|gasolina|coche/i, "car"],
  [/utilit|electric|water|\bgas\b|suministro|luz|agua/i, "bolt"],
  [/internet|phone|mobile|tel\u00e9fono|telefono|m\u00f3vil/i, "phone"],
  [/subscri|suscrip/i, "clock"],
  [/course|training|book|formaci|curso|libro/i, "book"],
  [/leisure|restaur|\bbar\b|ocio/i, "ticket"],
  [/\bwork\b|trabajo/i, "contract"],
  [/salary|payroll|bonus|extra|salario|n\u00f3mina|nomina|bono/i, "wallet"],
  [/\btax|hacienda|impuesto/i, "file"],
];

export function categoryIcon(name: string | undefined, nature: Nature | undefined): IconName {
  for (const [pattern, icon] of ICONS) if (name && pattern.test(name)) return icon;
  return nature === "income" ? "wallet" : "basket";
}

export function rowIcon(m: Movement): { icon: IconName; hue: number } {
  if (m.kind === "transfer") return { icon: "repeat", hue: 8 };
  if (m.status === "ask" || m.status === "pending") return { icon: "alert", hue: 3 };
  if (m.status === "return") return { icon: "chart", hue: 2 };
  if (m.status === "settlement") return { icon: "people", hue: 6 };
  const first = m.parts[0];
  const icon = categoryIcon(first?.category_name, first?.nature);
  if (first?.nature === "income") return { icon, hue: 2 };
  return { icon, hue: first?.ownership === "shared" ? 6 : 4 };
}

export function categoryLabel(c: Category): string {
  return say("category.label", { name: c.name, nature: natureName(c.nature).toLowerCase(), ownership: ownershipName(c.ownership).toLowerCase() });
}

function decimalMark(): string {
  return numbers().formatToParts(1.5).find((one) => one.type === "decimal")?.value ?? ".";
}

export function parseAmount(text: string): number | null {
  const mark = decimalMark();
  const group = mark === "," ? /\.(?=\d{3}(\D|$))/g : /,(?=\d{3}(\D|$))/g;
  const clean = text.replace(/\s/g, "").split(currencySymbol()).join("").replace(group, "").replace(",", ".");
  if (!/^-?\d+(\.\d{1,2})?$/.test(clean)) return null;
  return Number(clean);
}

export function amountText(value: number): string {
  return value.toFixed(2).replace(".", decimalMark());
}

export function percentText(ratio: number): string {
  return numbers({ style: "percent", maximumFractionDigits: 1 }).format(Math.round(ratio * 1000) / 1000);
}
