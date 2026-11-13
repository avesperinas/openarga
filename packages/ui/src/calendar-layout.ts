import { dates } from "./regional";
export type Tone = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10;

export const TONES: { tone: Tone; name: string }[] = [
  { tone: 1, name: "Azul" },
  { tone: 2, name: "Verde" },
  { tone: 3, name: "Ámbar" },
  { tone: 4, name: "Rojo" },
  { tone: 5, name: "Violeta" },
  { tone: 6, name: "Turquesa" },
  { tone: 7, name: "Rosa" },
  { tone: 8, name: "Grafito" },
  { tone: 9, name: "Naranja" },
  { tone: 10, name: "Cacao" },
];

export type EventStatus = "confirmed" | "tentative" | "cancelled";

export interface CalendarEvent {
  id: string;
  title: string;
  start: string | Date;
  end: string | Date;
  allDay?: boolean;
  tone: Tone;
  subtitle?: string;
  status?: EventStatus;
  readOnly?: boolean;
  subscribed?: boolean;
  recurring?: boolean;
  duplicateOf?: string;
  background?: boolean;
}

export const MINUTES_PER_DAY = 24 * 60;
export const SNAP_MINUTES = 15;

export function dayKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function dayStart(key: string): Date {
  const [year, month, day] = key.split("-").map(Number) as [number, number, number];
  return new Date(year, month - 1, day);
}

export function addDays(key: string, days: number): string {
  const date = dayStart(key);
  date.setDate(date.getDate() + days);
  return dayKey(date);
}

export function daysBetween(from: string, to: string): number {
  const a = dayStart(from);
  const b = dayStart(to);
  return Math.round((Date.UTC(b.getFullYear(), b.getMonth(), b.getDate()) -
    Date.UTC(a.getFullYear(), a.getMonth(), a.getDate())) / 86_400_000);
}

export function mondayOf(key: string): string {
  const weekday = (dayStart(key).getDay() + 6) % 7;
  return addDays(key, -weekday);
}

export function dayRange(first: string, count: number): string[] {
  return Array.from({ length: count }, (_, index) => addDays(first, index));
}

export function isoWeek(key: string): number {
  const date = dayStart(key);
  const thursday = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  thursday.setUTCDate(thursday.getUTCDate() + 3 - ((thursday.getUTCDay() + 6) % 7));
  const firstThursday = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 4));
  firstThursday.setUTCDate(firstThursday.getUTCDate() + 3 - ((firstThursday.getUTCDay() + 6) % 7));
  return 1 + Math.round((thursday.getTime() - firstThursday.getTime()) / (7 * 86_400_000));
}

export function wallMinutes(date: Date): number {
  return date.getHours() * 60 + date.getMinutes();
}

export function atMinute(key: string, minute: number): Date {
  const [year, month, day] = key.split("-").map(Number) as [number, number, number];
  return new Date(year, month - 1, day, 0, minute);
}

export function snap(minute: number, step = SNAP_MINUTES): number {
  return Math.round(minute / step) * step;
}

export function toDate(value: string | Date): Date {
  if (value instanceof Date) return value;
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? dayStart(value) : new Date(value);
}

export function isStripEvent(event: CalendarEvent): boolean {
  if (event.allDay) return true;
  return toDate(event.end).getTime() - toDate(event.start).getTime() >= MINUTES_PER_DAY * 60_000;
}

export function stripDays(event: CalendarEvent): [string, string] {
  const start = toDate(event.start);
  const end = toDate(event.end);
  const first = dayKey(start);
  const lastInstant = event.allDay || wallMinutes(end) === 0 ? new Date(end.getTime() - 1) : end;
  const last = dayKey(lastInstant);
  return [first, last < first ? first : last];
}

export interface Segment {
  event: CalendarEvent;
  day: string;
  top: number;
  bottom: number;
  continuesBefore: boolean;
  continuesAfter: boolean;
}

export function segmentsOf(events: CalendarEvent[], day: string): Segment[] {
  const out: Segment[] = [];
  for (const event of events) {
    if (isStripEvent(event)) continue;
    const segment = clipToDay(event, day);
    if (segment) out.push(segment);
  }
  return out;
}

function clipToDay(event: CalendarEvent, day: string): Segment | null {
  const from = dayStart(day).getTime();
  const to = dayStart(addDays(day, 1)).getTime();
  const start = toDate(event.start);
  const end = toDate(event.end);
  const s = Math.max(start.getTime(), from);
  const e = Math.min(Math.max(end.getTime(), start.getTime() + 60_000), to);
  if (e <= s || start.getTime() >= to) return null;
  return {
    event,
    day,
    top: s === from ? 0 : wallMinutes(new Date(s)),
    bottom: e === to ? MINUTES_PER_DAY : Math.max(wallMinutes(new Date(e)), 1),
    continuesBefore: start.getTime() < from,
    continuesAfter: end.getTime() > to,
  };
}

export interface Backdrop {
  segment: Segment;
  inStrip: boolean;
  labelAt: number | null;
}

export interface BackdropOptions {
  labelMinutes?: number;
  busy?: [number, number][];
}

export function backdropsOf(
  events: CalendarEvent[],
  day: string,
  { labelMinutes = 20, busy = [] }: BackdropOptions = {},
): Backdrop[] {
  const out: Backdrop[] = [];
  for (const event of events) {
    if (!event.background) continue;
    if (event.allDay) {
      const [first, last] = stripDays(event);
      if (day < first || day > last) continue;
      out.push({
        segment: { event, day, top: 0, bottom: MINUTES_PER_DAY, continuesBefore: day > first, continuesAfter: day < last },
        inStrip: true,
        labelAt: null,
      });
      continue;
    }
    const segment = clipToDay(event, day);
    if (segment) out.push({ segment, inStrip: isStripEvent(event), labelAt: null });
  }
  out.sort((a, b) => a.segment.top - b.segment.top || b.segment.bottom - a.segment.bottom);
  const taken: [number, number][] = [...busy];
  const free = (at: number) => taken.every(([top, bottom]) => at + labelMinutes <= top || at >= bottom);
  for (const one of out) {
    if (one.inStrip) continue;
    const { top, bottom } = one.segment;
    const candidates = [top, ...taken.map(([, end]) => end).filter((end) => end > top)].sort((a, b) => a - b);
    const at = candidates.find((minute) => minute + labelMinutes <= bottom && free(minute));
    if (at === undefined) continue;
    one.labelAt = at;
    taken.push([at, at + labelMinutes]);
  }
  return out;
}

export interface Placed {
  segment: Segment;
  left: number;
  width: number;
  layer: number;
  nested: boolean;
}

export const NEST_INDENT = 0.14;
const MIN_NESTED_WIDTH = 0.4;

export function layoutDay(
  segments: Segment[],
  { cascadeAfter = 30, minimumMinutes = 0 }: { cascadeAfter?: number; minimumMinutes?: number } = {},
): Placed[] {
  const items = segments
    .map((segment) => ({
      segment,
      top: segment.top,
      bottom: Math.min(MINUTES_PER_DAY, Math.max(segment.bottom, segment.top + minimumMinutes)),
    }))
    .sort(
      (a, b) =>
        a.top - b.top ||
        b.bottom - a.bottom ||
        a.segment.event.id.localeCompare(b.segment.event.id),
    );
  const n = items.length;
  if (n === 0) return [];

  const overlaps = (i: number, j: number) =>
    items[i]!.top < items[j]!.bottom && items[j]!.top < items[i]!.bottom;

  const parent = Array.from({ length: n }, (_, i) => i);
  const find = (i: number): number => (parent[i] === i ? i : (parent[i] = find(parent[i]!)));
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n && items[j]!.top < items[i]!.bottom; j++) {
      if (items[j]!.top - items[i]!.top < cascadeAfter && overlaps(i, j)) {
        parent[find(j)] = find(i);
      }
    }
  }
  const groups = new Map<number, number[]>();
  for (let i = 0; i < n; i++) {
    const root = find(i);
    groups.set(root, [...(groups.get(root) ?? []), i]);
  }
  const ordered = [...groups.values()].sort((a, b) => a[0]! - b[0]!);

  const left = new Array<number>(n).fill(0);
  const width = new Array<number>(n).fill(1);
  const layer = new Array<number>(n).fill(0);
  const nested = new Array<boolean>(n).fill(false);
  const placed: number[] = [];

  ordered.forEach((group, groupIndex) => {
    let from = 0;
    for (const i of group) {
      for (const k of placed) {
        if (overlaps(i, k)) from = Math.max(from, left[k]! + NEST_INDENT);
      }
    }
    from = Math.min(from, 1 - MIN_NESTED_WIDTH);
    const span = 1 - from;

    const columnEnds: number[] = [];
    const column = new Map<number, number>();
    for (const i of group) {
      let c = columnEnds.findIndex((end) => end <= items[i]!.top);
      if (c === -1) c = columnEnds.length;
      columnEnds[c] = items[i]!.bottom;
      column.set(i, c);
    }
    const count = columnEnds.length;
    for (const i of group) {
      const c = column.get(i)!;
      let reach = count;
      for (const j of group) {
        const cj = column.get(j)!;
        if (cj > c && cj < reach && overlaps(i, j)) reach = cj;
      }
      left[i] = from + (span * c) / count;
      width[i] = (span * (reach - c)) / count;
      layer[i] = groupIndex;
      nested[i] = from > 0;
    }
    placed.push(...group);
  });

  return items.map((item, i) => ({
    segment: item.segment,
    left: left[i]!,
    width: width[i]!,
    layer: layer[i]!,
    nested: nested[i]!,
  }));
}

export interface Bar {
  event: CalendarEvent;
  column: number;
  span: number;
  row: number;
  continuesBefore: boolean;
  continuesAfter: boolean;
}

export function layoutBars(
  events: CalendarEvent[],
  days: string[],
  singles: CalendarEvent[] = [],
): { bars: Bar[]; rows: number; perDay: number[] } {
  if (days.length === 0) return { bars: [], rows: 0, perDay: [] };
  const first = days[0]!;
  const last = days[days.length - 1]!;
  type Item = { event: CalendarEvent; from: number; to: number; before: boolean; after: boolean };
  const clip = (event: CalendarEvent, a: string, b: string): Item | null =>
    b < first || a > last
      ? null
      : {
          event,
          from: Math.max(0, daysBetween(first, a)),
          to: Math.min(days.length - 1, daysBetween(first, b)),
          before: a < first,
          after: b > last,
        };
  const long = events
    .map((event) => clip(event, ...stripDays(event)))
    .filter((item): item is Item => item !== null)
    .sort(
      (x, y) =>
        x.from - y.from ||
        y.to - y.from - (x.to - x.from) ||
        x.event.title.localeCompare(y.event.title),
    );
  const short = singles
    .map((event) => {
      const key = dayKey(toDate(event.start));
      return clip(event, key, key);
    })
    .filter((item): item is Item => item !== null)
    .sort((x, y) => x.from - y.from || toDate(x.event.start).getTime() - toDate(y.event.start).getTime());
  const unique = [...long, ...short];

  const occupied: boolean[][] = [];
  const perDay = new Array<number>(days.length).fill(0);
  const out: Bar[] = [];
  for (const item of unique) {
    let row = 0;
    while (occupied[row]?.slice(item.from, item.to + 1).some(Boolean)) row++;
    occupied[row] ??= new Array<boolean>(days.length).fill(false);
    for (let d = item.from; d <= item.to; d++) {
      occupied[row]![d] = true;
      perDay[d]!++;
    }
    out.push({
      event: item.event,
      column: item.from,
      span: item.to - item.from + 1,
      row,
      continuesBefore: item.before,
      continuesAfter: item.after,
    });
  }
  return { bars: out, rows: occupied.length, perDay };
}

export function monthDays(month: string): string[] {
  const first = `${month.slice(0, 7)}-01`;
  return dayRange(mondayOf(first), 42);
}

const clock = () => dates({ hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

export function formatClock(date: Date): string {
  return clock().format(date);
}

export function formatSpan(start: Date, end: Date): string {
  return `${formatClock(start)} – ${formatClock(end)}`;
}

export function hourLabel(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}
