import type { IconName } from "@openarga/ui";

import type { Category, Movement, Nature, Ownership, Payer, Status } from "./api";

const EUR = new Intl.NumberFormat("es-ES", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
  useGrouping: "always",
} as unknown as Intl.NumberFormatOptions);

const EUR_WHOLE = new Intl.NumberFormat("es-ES", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
  useGrouping: "always",
} as unknown as Intl.NumberFormatOptions);

export function moneyWhole(value: number, signed = false): string {
  const text = EUR_WHOLE.format(Math.abs(value));
  if (!signed || Math.round(value) === 0) return text;
  return `${value < 0 ? "−" : "+"}${text}`;
}

export function money(value: number, signed = true): string {
  const text = EUR.format(Math.abs(value));
  if (!signed || value === 0) return text;
  return `${value < 0 ? "−" : "+"}${text}`;
}

export const MONTHS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

const WEEKDAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];

export function capital(text: string): string {
  return text ? `${text[0]?.toUpperCase()}${text.slice(1)}` : text;
}

export function monthName(month: number): string {
  return MONTHS[month - 1] ?? "";
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
  const year = date.getFullYear() === today.getFullYear() ? "" : ` de ${date.getFullYear()}`;
  const weekday = WEEKDAYS[date.getDay()] ?? "";
  return `${capital(weekday)}, ${date.getDate()} de ${monthName(date.getMonth() + 1)}${year}`;
}

export function shortDay(iso: string): string {
  const date = parseDay(iso);
  return `${date.getDate()} ${monthName(date.getMonth() + 1).slice(0, 3)}`;
}

export function monthTitle(year: number, month: number): string {
  return `${capital(monthName(month))} ${year}`;
}

export const NATURE: Record<Nature, string> = { income: "Ingreso", expense: "Gasto" };
export const OWNERSHIP: Record<Ownership, string> = { individual: "Individual", shared: "Compartido" };

export function payerLabel(payer: Payer | null, me: string, other: string): string {
  if (payer === "account") return "Cuenta común";
  if (payer === "me") return me;
  if (payer === "other") return other;
  return "";
}

export const STATUS: Record<Status, string> = {
  transfer: "Traspaso",
  return: "Rentabilidad",
  settlement: "Liquidación",
  manual: "Etiquetado a mano",
  auto: "Automático",
  default: "Por defecto de la cuenta",
  ask: "Por etiquetar",
  pending: "Sin interpretar",
};

export function title(m: Movement): string {
  if (m.kind === "transfer" && m.transfer) {
    if (m.transfer.basis === "other_member") return `Aportación de ${m.transfer.name}`;
    if (m.transfer.account === m.account) return "Cambio de producto";
    return m.amount < 0 ? `A ${m.transfer.name}` : `Desde ${m.transfer.name}`;
  }
  return m.merchant;
}

export function subtitle(m: Movement): string {
  if (m.kind === "transfer") return "Traspaso";
  if (m.status === "ask") return "Efectivo · por etiquetar";
  if (m.status === "pending") return "Sin interpretar";
  if (m.status === "return") return "Rentabilidad";
  if (m.status === "settlement") return "Liquidación entre vosotros";
  const cats = m.parts.map((p) => p.category_name);
  const unique = [...new Set(cats)];
  const label = unique.length > 2 ? `${unique.slice(0, 2).join(", ")} y ${unique.length - 2} más` : unique.join(", ");
  const shared = m.parts.some((p) => p.ownership === "shared");
  return shared ? `${label} · compartido` : label;
}

const ICONS: [RegExp, IconName][] = [
  [/alquiler|vivienda|hogar|casa/i, "home"],
  [/super|shopping|compra/i, "basket"],
  [/gato|mascota|perro/i, "paw"],
  [/salud|farmacia|médic|medic/i, "heart"],
  [/viaje/i, "plane"],
  [/transporte|gasolina|coche/i, "car"],
  [/suministro|luz|agua|gas/i, "bolt"],
  [/internet|teléfono|telefono|móvil/i, "phone"],
  [/suscrip/i, "clock"],
  [/formaci|curso|libro/i, "book"],
  [/ocio|restaur|bar/i, "ticket"],
  [/trabajo/i, "contract"],
  [/salario|nómina|nomina|bonus|bono|extra/i, "wallet"],
  [/hacienda|impuesto/i, "file"],
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
  return `${c.name} · ${NATURE[c.nature].toLowerCase()} ${OWNERSHIP[c.ownership].toLowerCase()}`;
}

export function parseAmount(text: string): number | null {
  const clean = text.replace(/\s|€/g, "").replace(/\.(?=\d{3}(\D|$))/g, "").replace(",", ".");
  if (!/^-?\d+(\.\d{1,2})?$/.test(clean)) return null;
  return Number(clean);
}

export function amountText(value: number): string {
  return value.toFixed(2).replace(".", ",");
}

export function percentText(ratio: number): string {
  return `${(Math.round(ratio * 1000) / 10).toLocaleString("es-ES")} %`;
}
