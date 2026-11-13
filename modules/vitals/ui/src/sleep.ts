import type { Locale, Translate } from "@openarga/ui";

import type { Night, SleepStage } from "./api";

export const STAGES: { id: SleepStage }[] = [{ id: "deep" }, { id: "rem" }, { id: "light" }, { id: "awake" }];

export const stageName = (t: Translate, stage: SleepStage) => t(`stage.${stage}`);

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

export function stageSeries(nights: Night[], t: Translate): { key: SleepStage; name: string; values: number[] }[] {
  return STAGES.map((one) => ({
    key: one.id,
    name: stageName(t, one.id),
    values: nights.map((night) => Math.round(((night.stages?.[one.id] ?? 0) / 60) * 10) / 10),
  }));
}

export function against(minutes: number, mean: number | null, t: Translate): string {
  if (mean === null) return "";
  const gap = Math.round(minutes - mean);
  if (gap === 0) return t("average.same");
  return t(gap > 0 ? "average.above" : "average.below", { amount: hours(Math.abs(gap)) });
}

export function shortDay(day: string, locale: Locale): string {
  const [year = 1970, month = 1, date = 1] = day.split("-").map(Number);
  return new Date(year, month - 1, date).toLocaleDateString(locale, { day: "numeric", month: "numeric" });
}
