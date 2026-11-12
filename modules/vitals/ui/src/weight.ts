import type { Against, Day, Goal, Source } from "./api";

export type Period = "3m" | "1y" | "all";

export const PERIODS: { id: Period; label: string }[] = [
  { id: "3m", label: "3 meses" },
  { id: "1y", label: "1 año" },
  { id: "all", label: "Todo" },
];

export function monthsBefore(day: string, months: number): string {
  const [year = 1970, month = 1, date = 1] = day.split("-").map(Number);
  const back = new Date(Date.UTC(year, month - 1 - months, date));
  return back.toISOString().slice(0, 10);
}

export function inPeriod(days: Day[], period: Period): Day[] {
  const last = days[days.length - 1];
  if (!last || period === "all") return days;
  const from = monthsBefore(last.day, period === "3m" ? 3 : 12);
  return days.filter((one) => one.day > from);
}

export function extremes(days: Day[]): { min: Day; max: Day } | null {
  if (days.length === 0) return null;
  let min = days[0]!;
  let max = days[0]!;
  for (const one of days) {
    if (one.kg < min.kg) min = one;
    if (one.kg > max.kg) max = one;
  }
  return { min, max };
}

export const kg = (value: number) => `${value.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} kg`;

export const signedKg = (value: number) =>
  `${value.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: "exceptZero" })} kg`;

export function goodWay(against: Against | null): "down" | "up" | "stay" | null {
  if (against === "above") return "down";
  if (against === "below") return "up";
  if (against === "inside") return "stay";
  return null;
}

export function changeTone(change: number | null, against: Against | null): "positive" | "negative" | "neutral" {
  const way = goodWay(against);
  if (change === null || way === null || Math.abs(change) < 0.05) return "neutral";
  if (way === "stay") return Math.abs(change) <= 1 ? "positive" : "negative";
  return (way === "down") === change < 0 ? "positive" : "negative";
}

export function bandFoot(value: number, goal: Goal, against: Against | null): string {
  if (against === "above" && goal.weight_max_kg !== null) return `${kg(value - goal.weight_max_kg)} por encima del objetivo`;
  if (against === "below" && goal.weight_min_kg !== null) return `${kg(goal.weight_min_kg - value)} por debajo del objetivo`;
  if (against === "inside") return "Dentro del objetivo";
  return "Sin objetivo";
}

export function bandLabel(goal: Goal): string {
  const { weight_min_kg: low, weight_max_kg: high } = goal;
  if (low !== null && high !== null) return `Entre ${kg(low)} y ${kg(high)}`;
  if (high !== null) return `Hasta ${kg(high)}`;
  if (low !== null) return `Desde ${kg(low)}`;
  return "Sin objetivo";
}

export const SOURCES: Record<Source, string> = {
  manual: "Apuntada en la app",
  claude: "Apuntada por Claude",
  historico: "Del histórico",
};

export function dayLabel(day: string, withYear = true): string {
  return new Date(`${day}T12:00:00Z`).toLocaleDateString("es-ES", {
    weekday: withYear ? undefined : "short",
    day: "numeric",
    month: "short",
    year: withYear ? "numeric" : undefined,
  });
}

export function today(now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Madrid" }).format(now);
}

export function parseKg(text: string): number | null {
  const value = Number(text.trim().replace(",", "."));
  return Number.isFinite(value) && value >= 20 && value <= 400 ? value : null;
}
