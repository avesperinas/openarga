"use client";

import * as React from "react";

import { IconButton } from "./controls";
import { Icon, type IconName } from "./icons";
import { type AgendaEntry, MonthWithEntries, onDay, parseEntries } from "./agenda";
import type { Layout } from "./sizes";
import { useWidgetLayout } from "./Widget";
import { dates } from "./regional";

const WEEK = ["L", "M", "X", "J", "V", "S", "D"];

function monthGrid(reference: Date): { days: number; offset: number } {
  const year = reference.getFullYear();
  const month = reference.getMonth();
  const days = new Date(year, month + 1, 0).getDate();
  const offset = (new Date(year, month, 1).getDay() + 6) % 7;
  return { days, offset };
}

export interface WidgetCalendarProps {
  month?: Date;
  marked?: number[];
  today?: number;
  entries?: AgendaEntry[];
}

export function WidgetCalendar({ month, marked: given = [], today, entries }: WidgetCalendarProps) {
  const layout = useWidgetLayout();
  const marked = given.length || !entries ? given : markedDays(entries, month ?? new Date());
  if (entries && layout !== "tiny" && layout !== "strip" && layout !== "narrow") {
    return <MonthWithEntries entries={entries} month={month} />;
  }
  return <PlainCalendar month={month} marked={marked} today={today} />;
}

function markedDays(entries: AgendaEntry[], reference: Date): number[] {
  const all = parseEntries(entries);
  const length = new Date(reference.getFullYear(), reference.getMonth() + 1, 0).getDate();
  return Array.from({ length }, (_, index) => index + 1).filter(
    (day) => onDay(all, new Date(reference.getFullYear(), reference.getMonth(), day)).length > 0,
  );
}

function PlainCalendar({ month, marked = [], today }: WidgetCalendarProps) {
  const reference = month ?? new Date();
  const { days, offset } = monthGrid(reference);
  const flagged = new Set(marked);
  const layout = useWidgetLayout();

  const now = new Date();
  const isCurrentMonth =
    reference.getFullYear() === now.getFullYear() && reference.getMonth() === now.getMonth();
  const highlighted = today ?? (isCurrentMonth ? now.getDate() : undefined);

  const title = dates({ month: "long" }).format(reference);

  if (layout === "tiny") {
    const weekday = dates({ weekday: "short" }).format(now);
    return (
      <div className="calendar-today">
        <p className="calendar-today-weekday">{weekday}</p>
        <p className="calendar-today-date">{now.getDate()}</p>
      </div>
    );
  }

  if (layout === "narrow" && highlighted !== undefined) {
    const weekday = dates({ weekday: "short" }).format(now);
    const monday = highlighted - ((offset + highlighted - 1) % 7);
    return (
      <div className="calendar-narrow">
        <div className="calendar-today">
          <p className="calendar-today-weekday">{weekday}</p>
          <p className="calendar-today-date">{now.getDate()}</p>
        </div>
        <WeekDays
          monday={monday}
          days={days}
          reference={reference}
          highlighted={highlighted}
          flagged={flagged}
          vertical
        />
      </div>
    );
  }

  if (layout === "strip" && highlighted !== undefined) {
    const monday = highlighted - ((offset + highlighted - 1) % 7);
    return (
      <WeekDays
        monday={monday}
        days={days}
        reference={reference}
        highlighted={highlighted}
        flagged={flagged}
      />
    );
  }

  return (
    <div className="calendar">
      <p className="calendar-month">{title}</p>
      <div className="calendar-grid" role="grid" aria-label={title}>
        {WEEK.map((day, index) => (
          <span key={`head-${index}`} className="calendar-weekday" role="columnheader">
            {day}
          </span>
        ))}
        {Array.from({ length: offset }, (_, index) => (
          <span key={`gap-${index}`} className="calendar-day" data-empty="true" />
        ))}
        {Array.from({ length: days }, (_, index) => {
          const day = index + 1;
          return (
            <span
              key={day}
              className="calendar-day"
              role="gridcell"
              data-marked={flagged.has(day) || undefined}
              data-today={day === highlighted || undefined}
            >
              {day}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function WeekDays({
  monday,
  days,
  reference,
  highlighted,
  flagged,
  vertical,
}: {
  monday: number;
  days: number;
  reference: Date;
  highlighted: number;
  flagged: Set<number>;
  vertical?: boolean;
}) {
  return (
    <ol className="calendar-week" data-vertical={vertical || undefined} aria-label="Esta semana">
      {Array.from({ length: 7 }, (_, index) => {
        const day = monday + index;
        const inMonth = day >= 1 && day <= days;
        const date = new Date(reference.getFullYear(), reference.getMonth(), day);
        return (
          <li
            key={index}
            className="calendar-week-day"
            data-today={day === highlighted || undefined}
            data-marked={(inMonth && flagged.has(day)) || undefined}
          >
            <span className="calendar-weekday">{WEEK[index]}</span>
            <span className="calendar-week-date">{date.getDate()}</span>
          </li>
        );
      })}
    </ol>
  );
}

export interface Upcoming {
  at: string | Date;
  title: string;
  detail?: string;
}

const DAY_MS = 86_400_000;

export function whenLabel(at: Date, now: Date = new Date()): string {
  const midnight = (date: Date) =>
    new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const days = Math.round((midnight(at) - midnight(now)) / DAY_MS);
  const allDay = at.getHours() === 0 && at.getMinutes() === 0;
  const time = dates({ hour: "2-digit", minute: "2-digit" }).format(at);
  const day =
    days === 0
      ? "Hoy"
      : days === 1
        ? "Mañana"
        : days === -1
          ? "Ayer"
          : days > 1 && days < 7
            ? dates({ weekday: "long" }).format(at)
            : dates({
                day: "numeric",
                month: "short",
                ...(at.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }),
              }).format(at);
  const capital = day.charAt(0).toUpperCase() + day.slice(1);
  if (allDay) return capital;
  return days === 0 ? time : `${capital}, ${time}`;
}

const UPNEXT_ROWS: Record<Layout, number> = {
  tiny: 1,
  strip: 1,
  narrow: 3,
  square: 3,
  wide: 6,
  tall: 8,
  large: 12,
};

export function dayLabel(at: Date, now: Date = new Date()): string {
  const midnight = (date: Date) =>
    new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const days = Math.round((midnight(at) - midnight(now)) / DAY_MS);
  const day =
    days === 0
      ? "Hoy"
      : days === 1
        ? "Mañana"
        : days > 1 && days < 7
          ? dates({ weekday: "long" }).format(at)
          : dates({ weekday: "short", day: "numeric", month: "short" }).format(at);
  return day.charAt(0).toUpperCase() + day.slice(1);
}

const clock = (at: Date): string =>
  at.getHours() === 0 && at.getMinutes() === 0
    ? "Todo el día"
    : dates({ hour: "2-digit", minute: "2-digit" }).format(at);

export function WidgetUpNext({ events }: { events: Upcoming[] }) {
  const layout = useWidgetLayout();
  if (events.length === 0) {
    return <p className="widget-empty">Nada a la vista</p>;
  }
  const parsed = events
    .map((event) => ({ ...event, when: event.at instanceof Date ? event.at : new Date(event.at) }))
    .map((event) => ({ ...event, valid: !Number.isNaN(event.when.getTime()) }));

  if (layout === "tiny") {
    const first = parsed[0]!;
    return (
      <div className="upnext-tiny">
        <p className="upnext-tiny-when">{first.valid ? whenLabel(first.when) : "—"}</p>
        <p className="upnext-tiny-title">{first.title}</p>
      </div>
    );
  }

  const shown = parsed.slice(0, UPNEXT_ROWS[layout]);
  const grouped = layout === "tall" || layout === "large";

  if (grouped) {
    const days: { key: string; label: string; items: typeof shown }[] = [];
    for (const event of shown) {
      const key = event.valid ? isoDay(event.when) : "—";
      const last = days[days.length - 1];
      if (last && last.key === key) last.items.push(event);
      else days.push({ key, label: event.valid ? dayLabel(event.when) : "—", items: [event] });
    }
    let index = 0;
    return (
      <div className="upnext-days" data-layout={layout}>
        {days.map((day) => (
          <section key={day.key} className="upnext-day">
            <h3 className="upnext-day-label">{day.label}</h3>
            <ul className="upnext">
              {day.items.map((event) => (
                <li
                  key={index}
                  className="upnext-row"
                  style={{ "--cell-index": index++ } as React.CSSProperties}
                >
                  <span className="upnext-title">{event.title}</span>
                  <span className="upnext-when">
                    <span className="upnext-time">{event.valid ? clock(event.when) : "—"}</span>
                    {event.detail && <span className="upnext-detail">{event.detail}</span>}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    );
  }

  return (
    <ul className="upnext" data-layout={layout}>
      {shown.map((event, index) => (
        <li key={index} className="upnext-row" style={{ "--cell-index": index } as React.CSSProperties}>
          <span className="upnext-title">{event.title}</span>
          <span className="upnext-when">
            <span className="upnext-time">{event.valid ? whenLabel(event.when) : "—"}</span>
            {event.detail && <span className="upnext-detail">{event.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

export interface Shortcut {
  label: string;
  icon?: IconName;
  href: string;
}

export function WidgetShortcuts({ actions }: { actions: Shortcut[] }) {
  const shown = actions.slice(0, 4);
  return (
    <ul className="shortcuts" data-count={shown.length}>
      {shown.map((action, index) => (
        <li key={action.href} style={{ "--cell-index": index } as React.CSSProperties}>
          <a className="shortcut" href={action.href}>
            {action.icon && (
              <span className="shortcut-icon">
                <Icon name={action.icon} />
              </span>
            )}
            <span className="shortcut-label">{action.label}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}

export function isoDay(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export interface DayMark {
  kind?: string;
  label?: string;
}

export interface MonthWeek {
  monday: string;
  cells: ({ day: string; date: number } | null)[];
}

export function monthWeeks(year: number, month: number): MonthWeek[] {
  const { days, offset } = monthGrid(new Date(year, month, 1));
  const cells: ({ day: string; date: number } | null)[] = [
    ...Array.from({ length: offset }, () => null),
    ...Array.from({ length: days }, (_, index) => ({
      day: isoDay(new Date(year, month, index + 1)),
      date: index + 1,
    })),
  ];
  while (cells.length % 7 !== 0) cells.push(null);
  const weeks: MonthWeek[] = [];
  for (let start = 0; start < cells.length; start += 7) {
    const row = cells.slice(start, start + 7);
    const first = row.find((cell) => cell !== null)!;
    const firstDate = new Date(year, month, first.date);
    const monday = new Date(firstDate);
    monday.setDate(firstDate.getDate() - ((firstDate.getDay() + 6) % 7));
    weeks.push({ monday: isoDay(monday), cells: row });
  }
  return weeks;
}

export interface MonthCalendarProps {
  year: number;
  month: number;
  marks: Record<string, DayMark[]>;
  today: string;
  selected?: string | null;
  onSelect?: (day: string) => void;
  onPrevious: () => void;
  onNext: () => void;
  weekBelow?: (monday: string) => boolean;
  disabled?: (day: string) => boolean;
  weekLabel?: (monday: string) => string | null;
}

export function MonthCalendar({
  year,
  month,
  marks,
  today,
  selected,
  onSelect,
  onPrevious,
  onNext,
  weekBelow,
  disabled,
  weekLabel,
}: MonthCalendarProps) {
  const reference = new Date(year, month, 1);
  const title = dates({ month: "long", year: "numeric" }).format(reference);
  const long = dates({ weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="month" data-labelled={weekLabel ? "" : undefined}>
      <header className="month-head">
        <IconButton icon="chevron-left" label="Mes anterior" size="small" variant="plain" onClick={onPrevious} />
        <h2 className="month-title">{title.charAt(0).toUpperCase() + title.slice(1)}</h2>
        <IconButton icon="chevron-right" label="Mes siguiente" size="small" variant="plain" onClick={onNext} />
      </header>
      <div className="month-grid" role="grid" aria-label={title}>
        <div className="month-row" role="row">
          {weekLabel && <span className="month-week-label" aria-hidden="true" />}
          {WEEK.map((day, index) => (
            <span key={index} className="month-weekday" role="columnheader">
              {day}
            </span>
          ))}
        </div>
        {monthWeeks(year, month).map((week) => (
          <div
            key={week.monday}
            className="month-row"
            role="row"
            data-below={weekBelow?.(week.monday) || undefined}
          >
            {weekLabel && (
              <span className="month-week-label" aria-hidden="true">
                {weekLabel(week.monday) ?? ""}
              </span>
            )}
            {week.cells.map((cell, index) => {
              if (!cell) return <span key={`gap-${index}`} className="month-day" data-empty="true" />;
              const dayMarks = marks[cell.day] ?? [];
              const [year_, month_, date_] = cell.day.split("-").map(Number) as [number, number, number];
              const name = long.format(new Date(year_, month_ - 1, date_));
              const detail = dayMarks.map((mark) => mark.label).filter(Boolean).join(", ");
              return (
                <button
                  key={cell.day}
                  type="button"
                  role="gridcell"
                  className="month-day"
                  data-marked={dayMarks.length > 0 || undefined}
                  data-kind={dayMarks[0]?.kind}
                  data-today={cell.day === today || undefined}
                  aria-selected={cell.day === selected}
                  disabled={disabled?.(cell.day)}
                  aria-label={detail ? `${name}: ${detail}` : name}
                  onClick={() => onSelect?.(cell.day)}
                >
                  <span className="month-date">
                    {cell.date}
                    {dayMarks.length > 1 && <span className="month-count">{dayMarks.length}</span>}
                  </span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
