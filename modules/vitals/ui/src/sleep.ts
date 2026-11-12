import type { Night, SleepStage } from "./api";

export const STAGES: { id: SleepStage; name: string }[] = [
  { id: "deep", name: "Profundo" },
  { id: "rem", name: "REM" },
  { id: "light", name: "Ligero" },
  { id: "awake", name: "Despierto" },
];

export function hours(minutes: number | null): string {
  if (minutes === null) return "—";
  const rounded = Math.round(minutes);
  const whole = Math.floor(rounded / 60);
  const rest = rounded % 60;
  if (whole === 0) return `${rest} min`;
  return rest ? `${whole} h ${rest} min` : `${whole} h`;
}

export function clock(minutes: number | null): string {
  if (minutes === null) return "—";
  const day = ((Math.round(minutes) % 1440) + 1440) % 1440;
  return `${String(Math.floor(day / 60)).padStart(2, "0")}:${String(day % 60).padStart(2, "0")}`;
}

export function timeOf(instant: string): string {
  return instant.slice(11, 16);
}

export function stageShares(night: Pick<Night, "stages">): Partial<Record<SleepStage, number>> {
  const stages = night.stages ?? {};
  const total = STAGES.reduce((sum, one) => sum + (stages[one.id] ?? 0), 0);
  if (total === 0) return {};
  return Object.fromEntries(STAGES.filter((one) => stages[one.id] != null).map((one) => [one.id, Math.round(((stages[one.id] ?? 0) / total) * 100)]));
}

export function stageSeries(nights: Night[]): { key: SleepStage; name: string; values: number[] }[] {
  return STAGES.map((one) => ({
    key: one.id,
    name: one.name,
    values: nights.map((night) => Math.round(((night.stages?.[one.id] ?? 0) / 60) * 10) / 10),
  }));
}

export function against(minutes: number, mean: number | null): string {
  if (mean === null) return "";
  const gap = Math.round(minutes - mean);
  if (gap === 0) return "como tu media";
  return `${hours(Math.abs(gap))} ${gap > 0 ? "sobre" : "bajo"} tu media`;
}

export function shortDay(day: string): string {
  const [, month = "", date = ""] = day.split("-");
  return `${Number(date)}/${Number(month)}`;
}
