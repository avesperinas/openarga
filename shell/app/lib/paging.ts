export type Direction = -1 | 0 | 1;

export const WHEEL_THRESHOLD = 40;

export const WHEEL_QUIET_MS = 180;

const LINE_PX = 16;

export function wheelPager(threshold = WHEEL_THRESHOLD, quiet = WHEEL_QUIET_MS) {
  let accumulated = 0;
  let spent = false;
  let last = Number.NEGATIVE_INFINITY;

  return (delta: number, deltaMode: number, now: number, page = 800): Direction => {
    if (now - last > quiet) {
      accumulated = 0;
      spent = false;
    }
    last = now;
    if (spent) return 0;

    accumulated += delta * (deltaMode === 1 ? LINE_PX : deltaMode === 2 ? page : 1);
    if (Math.abs(accumulated) < threshold) return 0;

    spent = true;
    return accumulated > 0 ? 1 : -1;
  };
}

export function keyDirection(key: string): Direction {
  if (key === "ArrowLeft") return -1;
  if (key === "ArrowRight") return 1;
  return 0;
}

export function pairStart(index: number, count: number, perView: number): number {
  if (perView <= 1) return index;
  return Math.max(0, Math.min(Math.floor(index / perView) * perView, count - 1));
}

export function positionOf(offsets: number[], scrollLeft: number): number {
  if (offsets.length < 2) return 0;
  const last = offsets.length - 1;
  if (scrollLeft <= offsets[0]!) return 0;
  if (scrollLeft >= offsets[last]!) return last;
  let index = 0;
  while (index < last && offsets[index + 1]! <= scrollLeft) index += 1;
  const from = offsets[index]!;
  const to = offsets[index + 1]!;
  return index + (to > from ? (scrollLeft - from) / (to - from) : 0);
}

export const GROUP_COLUMNS = 16;
export const GROUP_PAGES = 4;

export interface PageSpan {
  used: number;
  start: number;
  group: number;
  edge: "only" | "start" | "middle" | "end";
}

export function groupPages(used: number[], columns = GROUP_COLUMNS, most = GROUP_PAGES): PageSpan[] {
  const groups: number[][] = [];
  for (const [index, own] of used.entries()) {
    const last = groups[groups.length - 1];
    const taken = last ? last.reduce((sum, at) => sum + used[at]!, 0) : 0;
    if (last && last.length < most && taken + own <= columns) last.push(index);
    else groups.push([index]);
  }
  return groups.flatMap((members) => {
    const total = members.reduce((sum, at) => sum + used[at]!, 0);
    return members.map((at, position) => ({
      used: used[at]!,
      start: members[0]!,
      group: total,
      edge:
        members.length === 1
          ? "only"
          : position === 0
            ? "start"
            : position === members.length - 1
              ? "end"
              : "middle",
    }));
  });
}

export function clampPage(index: number, count: number): number {
  return Math.min(Math.max(index, 0), Math.max(count - 1, 0));
}

const SETTLED = 0.01;

export function trackHeight(heights: number[], scrollLeft: number, step: number): number | null {
  if (heights.length === 0) return 0;
  const last = heights.length - 1;
  const position = step > 0 ? Math.min(last, Math.max(0, scrollLeft / step)) : 0;
  const nearest = Math.round(position);
  if (Math.abs(position - nearest) < SETTLED) return heights[nearest]!;
  return null;
}
