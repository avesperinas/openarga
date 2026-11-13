"use client";

import * as React from "react";
import { locale } from "./regional";

export interface YearDay {
  day: string;
  value: number;
}

export interface YearCalendarProps {
  days: YearDay[];
  label: string;
  end?: string;
  goal?: number | null;
  format?: (value: number) => string;
  formatDay?: (day: string) => string;
}

const DAY_MS = 86_400_000;
const WEEKS = 53;
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

function toTime(day: string): number {
  const [year = 1970, month = 1, date = 1] = day.split("-").map(Number);
  return Date.UTC(year, month - 1, date);
}

const toDay = (time: number) => new Date(time).toISOString().slice(0, 10);

export function yearLevel(value: number | undefined, top: number, goal = false): "none" | 0 | 1 | 2 | 3 | 4 {
  if (value === undefined || !Number.isFinite(value)) return "none";
  if (value <= 0) return 0;
  const share = value / (top || 1);
  if (goal) return share >= 1 ? 4 : (Math.max(1, Math.floor(share * 3) + 1) as 1 | 2 | 3);
  return Math.max(1, Math.min(4, Math.ceil(share * 4))) as 1 | 2 | 3 | 4;
}

export interface YearCell {
  day: string;
  value: number | undefined;
  week: number;
  weekday: number;
}

export function yearCells(days: YearDay[], end: string): YearCell[] {
  const values = new Map(days.map((one) => [one.day, one.value]));
  const last = toTime(end);
  const weekday = (new Date(last).getUTCDay() + 6) % 7;
  const firstMonday = last - (weekday + (WEEKS - 1) * 7) * DAY_MS;
  const cells: YearCell[] = [];
  for (let time = firstMonday; time <= last; time += DAY_MS) {
    const index = Math.round((time - firstMonday) / DAY_MS);
    const day = toDay(time);
    cells.push({ day, value: values.get(day), week: Math.floor(index / 7), weekday: index % 7 });
  }
  return cells;
}

export function monthStarts(cells: YearCell[]): { week: number; label: string }[] {
  return cells
    .filter((cell) => cell.day.endsWith("-01"))
    .map((cell) => ({ week: cell.week, label: MONTHS[Number(cell.day.slice(5, 7)) - 1] ?? "" }));
}

const longDay = (day: string) =>
  new Date(`${day}T12:00:00Z`).toLocaleDateString(locale(), {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });

export function YearCalendar({
  days,
  label,
  end,
  goal,
  format = (value) => value.toLocaleString(locale()),
  formatDay = longDay,
}: YearCalendarProps) {
  const scroller = React.useRef<HTMLDivElement>(null);
  const [picked, setPicked] = React.useState<YearCell | null>(null);
  const last = end ?? [...days].sort((a, b) => a.day.localeCompare(b.day)).at(-1)?.day;

  React.useEffect(() => {
    const box = scroller.current;
    if (box) box.scrollLeft = box.scrollWidth;
  }, [last]);

  if (!last) return <p className="widget-note">Sin datos en este año</p>;

  const cells = yearCells(days, last);
  const against = Boolean(goal && goal > 0);
  const top = against ? (goal as number) : Math.max(0, ...days.map((one) => one.value));
  const byDay = new Map(cells.map((cell) => [cell.day, cell]));
  const withData = cells.filter((cell) => cell.value !== undefined).length;

  return (
    <figure className="year-calendar" aria-label={label} data-scale={against ? "goal" : undefined}>
      <div className="year-calendar-scroll" ref={scroller}>
        <div className="year-calendar-grid" style={{ "--year-weeks": WEEKS } as React.CSSProperties}>
          <ol className="year-calendar-months" aria-hidden="true">
            {monthStarts(cells).map((month) => (
              <li key={`${month.week}-${month.label}`} style={{ gridColumn: month.week + 1 }}>
                {month.label}
              </li>
            ))}
          </ol>
          <div
            className="year-calendar-days"
            role="img"
            aria-label={`${label}: ${withData} de ${cells.length} días con dato`}
            onClick={(event) => {
              const day = (event.target as HTMLElement).dataset.day;
              setPicked(day ? (byDay.get(day) ?? null) : null);
            }}
          >
            {cells.map((cell) => (
              <span
                key={cell.day}
                className="year-calendar-day"
                data-day={cell.day}
                data-level={yearLevel(cell.value, top, against)}
                data-picked={picked?.day === cell.day ? "" : undefined}
                title={`${formatDay(cell.day)}: ${cell.value === undefined ? "sin dato" : format(cell.value)}`}
                style={{ gridColumn: cell.week + 1, gridRow: cell.weekday + 1 }}
              />
            ))}
          </div>
        </div>
      </div>
      <div className="year-calendar-foot">
        <p className="year-calendar-picked" role="status">
          {picked
            ? `${formatDay(picked.day)} · ${picked.value === undefined ? "sin dato" : format(picked.value)}`
            : "Toca un día para ver su cifra"}
        </p>
        <ul className="year-calendar-legend" aria-hidden="true">
          <li>
            <span className="year-calendar-day" data-level="none" /> sin dato
          </li>
          <li>
            <span className="year-calendar-day" data-level="0" />
            <span className="year-calendar-day" data-level="1" />
            <span className="year-calendar-day" data-level="2" />
            <span className="year-calendar-day" data-level="3" />
            <span className="year-calendar-day" data-level="4" /> {against ? "objetivo" : "más"}
          </li>
        </ul>
      </div>
    </figure>
  );
}
