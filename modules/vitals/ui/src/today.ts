import { type Locale, type Translate, type VitalTone, type WeekDayState } from "@openarga/ui";

import type { Baseline, Load, Score, Today, Workout } from "./api";

const number = (value: number, locale: Locale) => Math.round(value).toLocaleString(locale);

export interface Verdict {
  code: string;
  verdict: string;
  tone: VitalTone;
}

const verdict = (t: Translate, code: string, tone: VitalTone): Verdict => ({ code, verdict: t(`verdict.${code}`), tone });

export function sleepVerdict(score: Score | null | undefined, t: Translate): Verdict | null {
  if (!score) return null;
  if (score.quality === "excellent") return verdict(t, "excellent", "good");
  if (score.quality === "good") return verdict(t, "good", "good");
  if (score.quality === "fair") return verdict(t, "fair", "fair");
  return verdict(t, "poor", "poor");
}

export function recoveryVerdict(score: number | null | undefined, t: Translate): Verdict | null {
  if (score === null || score === undefined) return null;
  if (score >= 60) return verdict(t, "better", "good");
  if (score >= 40) return verdict(t, "usual", "neutral");
  return verdict(t, "worse", "fair");
}

export function recoveryLine(hrvZ: number | null, restingZ: number | null, t: Translate): string | undefined {
  const level = (z: number | null) => (z === null ? null : z >= 0.5 ? "high" : z <= -0.5 ? "low" : "normal");
  const hrv = level(hrvZ);
  const rest = level(restingZ);
  const parts = [hrv && t(`recovery.hrv.${hrv}`), rest && t(`recovery.resting.${rest}`)].filter(Boolean);
  return parts.length > 0 ? parts.join(", ") : undefined;
}

export function moveVerdict(steps: Today["steps"], t: Translate, locale: Locale): Verdict & { detail: string } {
  const today = steps.today ?? 0;
  const reached = steps.goal !== null && steps.goal > 0 && today >= steps.goal;
  const mean = steps.mean_7_past ?? steps.mean_7;
  return {
    code: reached ? "reached" : "moving",
    verdict: t("steps.count", { count: number(today, locale) }),
    tone: reached ? "good" : "neutral",
    detail: mean !== null ? t("verdict.mean_7", { value: number(mean, locale) }) : t("verdict.no_mean"),
  };
}

export function daysStarted(now: Date): number {
  return ((now.getDay() + 6) % 7) + 1;
}

export function pace(done: number, mean: number | null, now: Date): number | null {
  if (mean === null || mean <= 0) return null;
  return done / ((mean * daysStarted(now)) / 7);
}

export function expectedByNow(mean: number | null, now: Date): number | null {
  if (mean === null || mean <= 0) return null;
  return (mean * daysStarted(now)) / 7;
}

export function trainVerdict(share: number | null, t: Translate): Verdict {
  if (share === null) return verdict(t, "no_pace", "neutral");
  if (share >= 1.15) return verdict(t, "above_pace", "good");
  if (share >= 0.85) return verdict(t, "on_pace", "good");
  if (share >= 0.6) return verdict(t, "slightly_below", "neutral");
  return verdict(t, "below_pace", "fair");
}

export function daySentence(
  parts: { sleep?: Verdict | null; recovery?: Verdict | null; train?: Verdict | null },
  t: Translate,
): string {
  const first: string[] = [];
  if (parts.sleep) first.push(t(`sentence.slept.${parts.sleep.code}`));
  if (parts.recovery) first.push(t(`sentence.start.${parts.recovery.code}`));
  const sentences: string[] = [];
  if (first.length > 0) {
    const joined = first.join(t("sentence.and"));
    sentences.push(`${joined.charAt(0).toUpperCase()}${joined.slice(1)}.`);
  }
  if (parts.train && parts.train.code !== "no_pace") sentences.push(t(`sentence.week.${parts.train.code}`));
  return sentences.join(" ");
}

export function worstTone(tones: (VitalTone | undefined)[]): VitalTone {
  if (tones.includes("poor")) return "poor";
  if (tones.includes("fair")) return "fair";
  if (tones.includes("good")) return "good";
  return "neutral";
}

export function weekDots(workouts: Workout[], now: Date): { day: string; state: WeekDayState; kind?: string; today?: boolean }[] {
  const iso = (date: Date) =>
    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const monday = new Date(now);
  monday.setHours(12, 0, 0, 0);
  monday.setDate(monday.getDate() - (daysStarted(now) - 1));
  const todayIso = iso(now);
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(monday);
    date.setDate(monday.getDate() + index);
    const day = iso(date);
    const done = workouts.filter((one) => iso(new Date(one.start)) === day);
    const kind = done.some((one) => one.kind === "strength") ? "hue-4" : done.length > 0 ? "hue-6" : undefined;
    const state: WeekDayState = done.length > 0 ? "met" : day === todayIso ? "today" : day > todayIso ? "future" : "missed";
    return { day, state, kind, today: day === todayIso };
  });
}

export function rangeState(baseline: Baseline): "low" | "ok" | "high" | "none" {
  if (baseline.status === "below") return "low";
  if (baseline.status === "above") return "high";
  if (baseline.status === "inside") return "ok";
  return "none";
}

export function thisWeek(workouts: Workout[], now: Date): Workout[] {
  const keys = new Set(weekDots([], now).map((one) => one.day));
  const iso = (date: Date) =>
    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  return workouts.filter((one) => keys.has(iso(new Date(one.start))));
}

export function loadPace(load: Load, now: Date): { share: number | null; expected: number | null } {
  return { share: pace(load.this_week, load.mean_4, now), expected: expectedByNow(load.mean_4, now) };
}
