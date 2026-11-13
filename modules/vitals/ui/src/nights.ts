import type { QualityDay, StageShare, Translate, TrendPoint } from "@openarga/ui";

import type { Night, NightDetail, Score, SleepMeans } from "./api";
import { hours } from "./sleep";

export function yearAgo(now: Date): string {
  const back = new Date(now.getTime() - 370 * 86_400_000);
  return `${back.getFullYear()}-${String(back.getMonth() + 1).padStart(2, "0")}-${String(back.getDate()).padStart(2, "0")}`;
}

export function monthsOf(nights: Pick<Night, "day">[]): string[] {
  return [...new Set(nights.map((one) => one.day.slice(0, 7)))].sort();
}

export function scoreDays(nights: Night[]): QualityDay[] {
  return nights.flatMap((one) => (one.score ? [{ day: one.day, value: one.score.value, quality: one.score.quality }] : []));
}

export function scoreTrend(nights: Night[]): TrendPoint[] {
  const scored = nights.filter((one) => one.score);
  return scored.map((one, index) => {
    const window = scored.slice(Math.max(0, index - 6), index + 1);
    const average = window.reduce((sum, night) => sum + (night.score?.value ?? 0), 0) / window.length;
    return { day: one.day, value: one.score?.value ?? 0, average: window.length >= 3 ? Math.round(average * 10) / 10 : null };
  });
}

export function stageShareList(night: Pick<NightDetail, "stages">, usual: SleepMeans): StageShare[] {
  const stages = night.stages ?? {};
  return (["awake", "rem", "light", "deep"] as const)
    .filter((stage) => stages[stage] != null)
    .map((stage) => ({ stage, minutes: stages[stage] ?? 0, usual: usual.nights > 0 ? (usual.stages[stage] ?? null) : null }));
}

export function scoreParts(score: Score, t: Translate): { label: string; value: string; share: number }[] {
  const parts: { label: string; got: number | null; top: number }[] = [
    { label: t("score.duration"), got: score.duration, top: 50 },
    { label: t("score.depth"), got: score.depth, top: 25 },
    { label: t("score.calm"), got: score.calm, top: 25 },
  ];
  return parts.flatMap((one) =>
    one.got === null
      ? []
      : [{ label: one.label, value: t("score.of", { got: Math.round(one.got), top: one.top }), share: one.got / one.top }],
  );
}

export function againstUsual(minutes: number, mean: number | null, t: Translate): string | undefined {
  if (mean === null) return undefined;
  const gap = Math.round(minutes - mean);
  if (Math.abs(gap) < 5) return t("usual.same");
  return t(gap > 0 ? "usual.more" : "usual.less", { amount: hours(Math.abs(gap)) });
}
