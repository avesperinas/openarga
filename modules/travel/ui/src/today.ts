import type { TodayEntry } from "./api";

function minutes(at: string): number {
  const [hours, mins] = at.split(":").map(Number);
  return (hours ?? 0) * 60 + (mins ?? 0);
}

export function progress(entries: TodayEntry[], now: string): { done: boolean[]; next: number | null } {
  const at = minutes(now);
  const done = entries.map((entry) => {
    const until = entry.ends_at ?? entry.starts_at;
    return until !== null && minutes(until) <= at;
  });
  const started = entries.reduce(
    (last, entry, index) => (entry.starts_at !== null && minutes(entry.starts_at) <= at ? index : last),
    -1,
  );
  for (let index = 0; index < started; index += 1) done[index] = true;
  const next = done.indexOf(false);
  return { done, next: next < 0 ? null : next };
}

export function clock(now: Date = new Date()): { day: string; time: string } {
  const pad = (value: number) => String(value).padStart(2, "0");
  return {
    day: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
    time: `${pad(now.getHours())}:${pad(now.getMinutes())}`,
  };
}

export function onApple(agent: string = navigator.userAgent, touch = navigator.maxTouchPoints): boolean {
  return /iPhone|iPad|iPod/.test(agent) || (/Macintosh/.test(agent) && touch > 1);
}
