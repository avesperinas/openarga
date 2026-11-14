"use client";

import * as React from "react";

import { dayLabel, isoDay } from "./calendar";
import { useWidgetLayout } from "./Widget";
import { dates } from "./regional";
import { say } from "./words";

const DAY_MS = 86_400_000;

export interface AgendaEntry {
  start: string;
  end?: string;
  allDay?: boolean;
  title: string;
  detail?: string;
  tone?: number;
}

interface Parsed extends AgendaEntry {
  from: Date;
  to: Date;
  allDay: boolean;
}

function parseDay(value: string): Date {
  const [year, month, day] = value.slice(0, 10).split("-").map(Number) as [number, number, number];
  return new Date(year, month - 1, day);
}

const dateOnly = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value);

export function parseEntries(entries: AgendaEntry[]): Parsed[] {
  return entries
    .map((entry) => {
      const allDay = Boolean(entry.allDay) || dateOnly(entry.start);
      const from = allDay ? parseDay(entry.start) : new Date(entry.start);
      let to: Date;
      if (entry.end) to = allDay ? parseDay(entry.end) : new Date(entry.end);
      else to = allDay ? new Date(from.getTime() + DAY_MS) : new Date(from.getTime() + 3_600_000);
      if (allDay && to.getTime() <= from.getTime()) to = new Date(from.getTime() + DAY_MS);
      return { ...entry, allDay, from, to };
    })
    .filter((entry) => !Number.isNaN(entry.from.getTime()))
    .sort((a, b) => Number(b.allDay) - Number(a.allDay) || a.from.getTime() - b.from.getTime());
}

const midnight = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());
const addDays = (date: Date, days: number) =>
  new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);

export function onDay(entries: Parsed[], day: Date): Parsed[] {
  const start = midnight(day).getTime();
  const end = addDays(day, 1).getTime();
  return entries.filter((entry) => entry.from.getTime() < end && entry.to.getTime() > start);
}

const clock = (date: Date) =>
  dates({ hour: "2-digit", minute: "2-digit" }).format(date);

export function untilLabel(from: Date, to: Date, now: Date = new Date()): string {
  if (from.getTime() <= now.getTime()) return to.getTime() > now.getTime() ? say("agenda.now") : say("agenda.over");
  const minutes = Math.round((from.getTime() - now.getTime()) / 60_000);
  if (minutes < 60) return say("agenda.in_minutes", { minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 12 && midnight(from).getTime() === midnight(now).getTime()) {
    const rest = minutes % 60;
    return rest >= 10 ? say("agenda.in_hours_minutes", { hours, minutes: rest }) : say("agenda.in_hours", { hours });
  }
  return midnight(from).getTime() === midnight(now).getTime() ? clock(from) : dayLabel(from, now);
}

function Row({ entry, now }: { entry: Parsed; now: Date }) {
  const running = !entry.allDay && entry.from <= now && entry.to > now;
  const past = !entry.allDay && entry.to <= now;
  return (
    <li
      className="entry"
      data-tone={entry.tone}
      data-running={running || undefined}
      data-past={past || undefined}
      data-all-day={entry.allDay || undefined}
    >
      <span className="entry-time">
        {entry.allDay ? (
          say("calendar.all_day")
        ) : (
          <>
            <span>{clock(entry.from)}</span>
            <span className="entry-end">{clock(entry.to)}</span>
          </>
        )}
      </span>
      <span className="entry-body">
        <span className="entry-title">{entry.title}</span>
        {entry.detail && <span className="entry-detail">{entry.detail}</span>}
      </span>
    </li>
  );
}

function Day({
  day,
  entries,
  now,
  label,
  empty,
}: {
  day: Date;
  entries: Parsed[];
  now: Date;
  label?: string;
  empty?: string;
}) {
  return (
    <section className="agenda-day">
      <h3 className="agenda-day-label" data-today={isoDay(day) === isoDay(now) || undefined}>
        {label ?? dayLabel(day, now)}
      </h3>
      {entries.length === 0 ? (
        <p className="agenda-free">{empty ?? "Libre"}</p>
      ) : (
        <ul className="entries">
          {entries.map((entry, index) => (
            <Row key={`${entry.title}-${index}`} entry={entry} now={now} />
          ))}
        </ul>
      )}
    </section>
  );
}

function span(entries: Parsed[]): [number, number] {
  const timed = entries.filter((entry) => !entry.allDay);
  const first = Math.min(8, ...timed.map((entry) => entry.from.getHours()));
  const last = Math.max(20, ...timed.map((entry) => Math.min(24, entry.to.getHours() + 1)));
  return [first, last];
}

function Timeline({ entries, now }: { entries: Parsed[]; now: Date }) {
  const today = midnight(now);
  const [first, last] = span(entries);
  const hours = last - first;
  const at = (date: Date) => {
    const minutes = (date.getTime() - today.getTime()) / 60_000 - first * 60;
    return Math.max(0, Math.min(1, minutes / (hours * 60)));
  };
  const allDay = entries.filter((entry) => entry.allDay);
  const timed = entries.filter((entry) => !entry.allDay);
  return (
    <div className="timeline">
      {allDay.length > 0 && (
        <ul className="timeline-all-day">
          {allDay.map((entry, index) => (
            <li key={index} className="entry-chip" data-tone={entry.tone}>
              {entry.title}
            </li>
          ))}
        </ul>
      )}
      <div className="timeline-canvas" style={{ "--hours": hours } as React.CSSProperties}>
        {Array.from({ length: hours }, (_, index) => (
          <span
            key={index}
            className="timeline-hour"
            style={{ "--at": index / hours } as React.CSSProperties}
          >
            {String(first + index).padStart(2, "0")}
          </span>
        ))}
        {timed.map((entry, index) => {
          const top = at(entry.from);
          const height = Math.max(at(entry.to) - top, 0.035);
          return (
            <span
              key={index}
              className="timeline-block"
              data-tone={entry.tone}
              data-past={entry.to <= now || undefined}
              style={{ "--top": top, "--height": height } as React.CSSProperties}
            >
              <span className="entry-title">{entry.title}</span>
              {height > 0.07 && <span className="entry-detail">{clock(entry.from)}</span>}
            </span>
          );
        })}
        <span className="timeline-now" style={{ "--at": at(now) } as React.CSSProperties} />
      </div>
    </div>
  );
}

export function WidgetAgenda({ entries, now: given }: { entries: AgendaEntry[]; now?: Date }) {
  const layout = useWidgetLayout();
  const now = given ?? new Date();
  const all = parseEntries(entries);
  const today = onDay(all, now);
  const tomorrow = onDay(all, addDays(now, 1));
  const ahead = all.filter((entry) => entry.to > now);
  const next = ahead.find((entry) => !entry.allDay) ?? ahead[0];

  if (layout === "tiny" || layout === "strip") {
    if (!next) return <p className="widget-empty">{say("calendar.nothing_ahead")}</p>;
    const pending = today.filter((entry) => entry.to > now && entry !== next).length;
    return (
      <div className="agenda-next" data-tone={next.tone} data-layout={layout}>
        <p className="agenda-next-when">
          {next.allDay ? dayLabel(next.from, now) : untilLabel(next.from, next.to, now)}
        </p>
        <p className="agenda-next-title">{next.title}</p>
        {layout === "strip" && !next.allDay && (
          <p className="agenda-next-detail">
            {clock(next.from)}–{clock(next.to)}
            {next.detail ? ` · ${next.detail}` : ""}
          </p>
        )}
        {layout === "strip" && pending > 0 && (
          <span className="list-strip-more">+{pending} hoy</span>
        )}
      </div>
    );
  }

  if (layout === "wide") {
    return (
      <div className="agenda" data-layout={layout}>
        <Day day={now} entries={today} now={now} />
        <Day day={addDays(now, 1)} entries={tomorrow} now={now} />
      </div>
    );
  }

  const following = (from: number, count: number) =>
    Array.from({ length: count }, (_, index) => addDays(now, from + index))
      .map((day) => ({ day, entries: onDay(all, day) }))
      .filter((day) => day.entries.length > 0);

  if (layout === "large") {
    return (
      <div className="agenda" data-layout={layout}>
        <section className="agenda-day">
          <h3 className="agenda-day-label" data-today="">
            Hoy
          </h3>
          <Timeline entries={today} now={now} />
        </section>
        <div className="agenda-rest">
          {following(1, 6).map(({ day, entries: dayEntries }) => (
            <Day key={isoDay(day)} day={day} entries={dayEntries} now={now} />
          ))}
        </div>
      </div>
    );
  }

  if (layout === "tall") {
    return (
      <div className="agenda" data-layout={layout}>
        <Day day={now} entries={today} now={now} empty={say("agenda.nothing_more_today")} />
        {following(1, 6).map(({ day, entries: dayEntries }) => (
          <Day key={isoDay(day)} day={day} entries={dayEntries} now={now} />
        ))}
      </div>
    );
  }

  const left = today.filter((entry) => entry.allDay || entry.to > now);
  const showTomorrow = left.length === 0 && tomorrow.length > 0;
  return (
    <div className="agenda" data-layout={layout}>
      {showTomorrow ? (
        <Day day={addDays(now, 1)} entries={tomorrow} now={now} />
      ) : (
        <Day day={now} entries={left} now={now} empty={say("agenda.nothing_more_today")} />
      )}
    </div>
  );
}

export function WidgetWeek({ entries, now: given }: { entries: AgendaEntry[]; now?: Date }) {
  const layout = useWidgetLayout();
  const now = given ?? new Date();
  const all = parseEntries(entries);
  const days = Array.from({ length: 7 }, (_, index) => addDays(now, index)).map((day) => ({
    day,
    entries: onDay(all, day),
  }));
  const weekday = (day: Date) =>
    dates({ weekday: "short" }).format(day).replace(".", "");

  if (layout === "tiny") {
    const count = days.reduce((total, day) => total + day.entries.length, 0);
    return (
      <div className="list-count">
        <p className="widget-value kpi-figure">{count}</p>
        <p className="list-count-first">{say("agenda.in_7_days")}</p>
      </div>
    );
  }

  if (layout === "wide" || layout === "large" || layout === "strip") {
    const dotsOnly = layout === "strip";
    return (
      <ol className="week" data-layout={layout}>
        {days.map(({ day, entries: dayEntries }, index) => (
          <li key={index} className="week-day" data-today={index === 0 || undefined}>
            <span className="week-day-name">{weekday(day)}</span>
            <span className="week-day-date">{day.getDate()}</span>
            {dotsOnly ? (
              <span className="week-dots" aria-label={`${dayEntries.length} cosas`}>
                {dayEntries.slice(0, 3).map((entry, dot) => (
                  <span key={dot} className="week-dot" data-tone={entry.tone} />
                ))}
              </span>
            ) : (
              <ul className="week-entries">
                {dayEntries.slice(0, layout === "large" ? 8 : 3).map((entry, item) => (
                  <li key={item} className="entry-chip" data-tone={entry.tone}>
                    {layout === "large" && !entry.allDay && (
                      <span className="entry-chip-time">{clock(entry.from)}</span>
                    )}
                    <span className="entry-chip-title">{entry.title}</span>
                  </li>
                ))}
                {dayEntries.length > (layout === "large" ? 8 : 3) && (
                  <li className="week-more">+{dayEntries.length - (layout === "large" ? 8 : 3)}</li>
                )}
              </ul>
            )}
          </li>
        ))}
      </ol>
    );
  }

  return (
    <ol className="week-rows">
      {days.map(({ day, entries: dayEntries }, index) => (
        <li key={index} className="week-row" data-today={index === 0 || undefined}>
          <span className="week-row-day">
            <span className="week-day-name">{weekday(day)}</span>
            <span className="week-day-date">{day.getDate()}</span>
          </span>
          {dayEntries[0] ? (
            <span className="week-row-first" data-tone={dayEntries[0].tone}>
              {dayEntries[0].title}
            </span>
          ) : (
            <span className="week-row-free">—</span>
          )}
          {dayEntries.length > 1 && <span className="week-more">+{dayEntries.length - 1}</span>}
        </li>
      ))}
    </ol>
  );
}

const WEEK_LETTERS = ["L", "M", "X", "J", "V", "S", "D"];

export function MonthWithEntries({
  entries,
  now: given,
  month,
}: {
  entries: AgendaEntry[];
  now?: Date;
  month?: Date;
}) {
  const layout = useWidgetLayout();
  const now = given ?? new Date();
  const reference = month ?? now;
  const all = parseEntries(entries);
  const first = new Date(reference.getFullYear(), reference.getMonth(), 1);
  const offset = (first.getDay() + 6) % 7;
  const length = new Date(reference.getFullYear(), reference.getMonth() + 1, 0).getDate();
  const weeks = Math.ceil((offset + length) / 7);
  const cells = Array.from({ length: weeks * 7 }, (_, index) => addDays(first, index - offset));
  const title = dates({ month: "long" }).format(reference);

  const grid = (
    <div className="month-entries">
      <p className="calendar-month">{title}</p>
      <div className="month-entries-grid" style={{ "--weeks": weeks } as React.CSSProperties}>
        {WEEK_LETTERS.map((letter) => (
          <span key={letter} className="calendar-weekday">
            {letter}
          </span>
        ))}
        {cells.map((day) => (
          <div
            key={isoDay(day)}
            className="month-cell"
            data-outside={day.getMonth() !== reference.getMonth() || undefined}
            data-today={isoDay(day) === isoDay(now) || undefined}
            data-past={day < midnight(now) || undefined}
          >
            <span className="month-cell-date">{day.getDate()}</span>
          </div>
        ))}
      </div>
    </div>
  );

  if (layout !== "wide" && layout !== "large" && layout !== "tall") return grid;

  const today = onDay(all, now).filter((entry) => entry.allDay || entry.to > now);
  const tomorrow = onDay(all, addDays(now, 1));
  const showTomorrow = today.length === 0 && tomorrow.length > 0;
  return (
    <div className="month-split" data-stacked={layout === "tall" || undefined}>
      {grid}
      {showTomorrow ? (
        <Day day={addDays(now, 1)} entries={tomorrow} now={now} />
      ) : (
        <Day day={now} entries={today} now={now} empty={say("agenda.nothing_more_today")} />
      )}
    </div>
  );
}
