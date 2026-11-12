import { type VitalTone, type WeekDayState, plain } from "@openarga/ui";

import type { Baseline, Load, Score, Today, Workout } from "./api";

const number = (value: number) => plain(Math.round(value));

export interface Verdict {
  verdict: string;
  tone: VitalTone;
}

export function sleepVerdict(score: Score | null | undefined): Verdict | null {
  if (!score) return null;
  if (score.quality === "excellent") return { verdict: "Excelente", tone: "good" };
  if (score.quality === "good") return { verdict: "Buena", tone: "good" };
  if (score.quality === "fair") return { verdict: "Regular", tone: "fair" };
  return { verdict: "Mala", tone: "poor" };
}

export function recoveryVerdict(score: number | null | undefined): Verdict | null {
  if (score === null || score === undefined) return null;
  if (score >= 60) return { verdict: "Mejor que de costumbre", tone: "good" };
  if (score >= 40) return { verdict: "Como siempre", tone: "neutral" };
  return { verdict: "Peor que de costumbre", tone: "fair" };
}

export function recoveryLine(hrvZ: number | null, restingZ: number | null): string | undefined {
  const word = (z: number | null) => (z === null ? null : z >= 0.5 ? "alta" : z <= -0.5 ? "baja" : "normal");
  const hrv = word(hrvZ);
  const rest = restingZ === null ? null : restingZ >= 0.5 ? "alto" : restingZ <= -0.5 ? "bajo" : "normal";
  const parts = [hrv && `VFC ${hrv}`, rest && `reposo ${rest}`].filter(Boolean);
  return parts.length > 0 ? parts.join(", ") : undefined;
}

export function moveVerdict(steps: Today["steps"]): Verdict & { detail: string } {
  const today = steps.today ?? 0;
  const reached = steps.goal !== null && steps.goal > 0 && today >= steps.goal;
  const mean = steps.mean_7_past ?? steps.mean_7;
  return {
    verdict: `${number(today)} pasos`,
    tone: reached ? "good" : "neutral",
    detail: mean !== null ? `media de 7 días: ${number(mean)}` : "sin media todavía",
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

export function trainVerdict(share: number | null): Verdict {
  if (share === null) return { verdict: "Sin media aún", tone: "neutral" };
  if (share >= 1.15) return { verdict: "Por encima de tu ritmo", tone: "good" };
  if (share >= 0.85) return { verdict: "A tu ritmo", tone: "good" };
  if (share >= 0.6) return { verdict: "Algo por debajo", tone: "neutral" };
  return { verdict: "Por debajo de tu ritmo", tone: "fair" };
}

export function daySentence(parts: { sleep?: Verdict | null; recovery?: Verdict | null; train?: Verdict | null }): string {
  const first: string[] = [];
  if (parts.sleep) {
    const said: Record<string, string> = {
      Excelente: "Dormiste muy bien",
      Buena: "Dormiste bien",
      Regular: "Dormiste regular",
      Mala: "Dormiste mal",
    };
    first.push(said[parts.sleep.verdict] ?? "Dormiste");
  }
  if (parts.recovery) first.push(`llegas ${parts.recovery.verdict.toLowerCase()}`);
  const sentences: string[] = [];
  if (first.length > 0) {
    const joined = first.join(" y ");
    sentences.push(`${joined.charAt(0).toUpperCase()}${joined.slice(1)}.`);
  }
  if (parts.train && parts.train.verdict !== "Sin media aún") {
    const words: Record<string, string> = {
      "Por encima de tu ritmo": "vas por encima de tu ritmo",
      "A tu ritmo": "vas a tu ritmo",
      "Algo por debajo": "vas algo por debajo de tu ritmo",
      "Por debajo de tu ritmo": "vas por debajo de tu ritmo",
    };
    sentences.push(`Esta semana ${words[parts.train.verdict] ?? ""}.`);
  }
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
