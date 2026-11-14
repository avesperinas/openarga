"use client";

import * as React from "react";

import {
  type CalendarEvent,
  addDays,
  dayKey,
  dayStart,
  formatClock,
  isStripEvent,
  isoWeek,
  dayRange,
  layoutBars,
  mondayOf,
  monthDays,
  toDate,
} from "./calendar-layout";
import { IconButton } from "./controls";
import { describe } from "./time-grid";
import { dates } from "./regional";
import { say } from "./words";

const weekdays = (weekday: "short" | "narrow") =>
  Array.from({ length: 7 }, (_, index) =>
    dates({ weekday, timeZone: "UTC" }).format(new Date(Date.UTC(2024, 0, 1 + index))).replace(".", ""),
  );
const monthTitle = () => dates({ month: "long", year: "numeric" });
const dayLong = () => dates({ weekday: "long", day: "numeric", month: "long" });

const capitalise = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export function formatMonth(day: string): string {
  return capitalise(monthTitle().format(dayStart(day)).replace(" de ", " "));
}

const COMPACT_BELOW = 560;
const LINE = 20;
const LINE_COMPACT = 6;
const HEAD = 28;
const HEAD_COMPACT = 26;

export interface MonthGridProps {
  month: string;
  from?: string;
  events: CalendarEvent[];
  label?: string;
  selectedDay?: string | null;
  selectedId?: string | null;
  onDayClick?: (day: string) => void;
  onEventClick?: (id: string) => void;
  onNavigate?: (step: -1 | 1) => void;
  onScroll?: (weeks: number) => void;
  now?: Date;
}

const SWIPE_SLOP = 8;
const WHEEL_WEEK = 80;
const WHEEL_LINE = 33;
const SCROLL_MS = 150;

const weeksOf = (root: HTMLElement | null) => Array.from(root?.querySelectorAll<HTMLElement>(".mg-week") ?? []);
const rowOf = (root: HTMLElement | null) => root?.querySelector<HTMLElement>(".mg-week")?.clientHeight || 120;
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

function useMonthSwipe(
  ref: React.RefObject<HTMLDivElement | null>,
  onNavigate?: (step: -1 | 1) => void,
  onScroll?: (weeks: number) => void,
) {
  const gesture = React.useRef<{
    id: number;
    x0: number;
    y0: number;
    dx: number;
    swiping: boolean;
    scrolling: boolean;
    dy: number;
    consumed: number;
  } | null>(null);
  const suppressClick = React.useRef(false);

  const weeks = () => weeksOf(ref.current);
  const move = (dx: number) => weeks().forEach((week) => (week.style.transform = dx ? `translate3d(${dx}px,0,0)` : ""));
  const lift = (dy: number) => weeks().forEach((week) => (week.style.transform = dy ? `translate3d(0,${dy}px,0)` : ""));

  React.useLayoutEffect(() => {
    const g = gesture.current;
    if (g?.scrolling) lift(g.dy - g.consumed);
  });

  const settle = (step: -1 | 0 | 1) => {
    const elements = weeks();
    const width = ref.current?.clientWidth ?? 0;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const from = (element: HTMLElement) => element.style.transform || "translate3d(0,0,0)";
    if (step === 0 || !onNavigate) {
      elements.forEach((element) =>
        element.animate([{ transform: from(element) }, { transform: "translate3d(0,0,0)" }], {
          duration: reduced ? 1 : 260,
          easing: "cubic-bezier(.2,.9,.3,1)",
        }),
      );
      move(0);
      return;
    }
    const out = elements.map((element) =>
      element.animate([{ transform: from(element) }, { transform: `translate3d(${-step * width}px,0,0)`, opacity: 0.4 }], {
        duration: reduced ? 1 : 170,
        easing: "cubic-bezier(.3,.6,.4,1)",
        fill: "forwards",
      }),
    );
    void Promise.all(out.map((animation) => animation.finished)).then(() => {
      move(0);
      onNavigate(step);
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          out.forEach((animation) => animation.cancel());
          weeks().forEach((element) =>
            element.animate(
              [
                { transform: `translate3d(${step * width * 0.3}px,0,0)`, opacity: 0.4 },
                { transform: "translate3d(0,0,0)", opacity: 1 },
              ],
              { duration: reduced ? 1 : 280, easing: "cubic-bezier(.2,.9,.3,1)" },
            ),
          );
        }),
      );
    });
  };

  const end = (event: React.PointerEvent, cancelled: boolean) => {
    const g = gesture.current;
    if (!g || g.id !== event.pointerId) return;
    gesture.current = null;
    if (g.scrolling) {
      if (ref.current) delete ref.current.dataset.dragging;
      suppressClick.current = true;
      setTimeout(() => (suppressClick.current = false), 0);
      const from = g.dy - g.consumed;
      lift(0);
      weeks().forEach((week) =>
        week.animate([{ transform: `translate3d(0,${from}px,0)` }, { transform: "translate3d(0,0,0)" }], {
          duration: reducedMotion() ? 1 : 220,
          easing: "cubic-bezier(.2,.9,.3,1)",
        }),
      );
      return;
    }
    if (!g.swiping) return;
    suppressClick.current = true;
    setTimeout(() => (suppressClick.current = false), 0);
    const width = ref.current?.clientWidth ?? 1;
    settle(!cancelled && Math.abs(g.dx) > width * 0.22 ? (g.dx < 0 ? 1 : -1) : 0);
  };

  if (!onNavigate && !onScroll) return {};
  return {
    onPointerDown: (event: React.PointerEvent) => {
      if (event.pointerType === "mouse" || gesture.current) return;
      gesture.current = {
        id: event.pointerId,
        x0: event.clientX,
        y0: event.clientY,
        dx: 0,
        swiping: false,
        scrolling: false,
        dy: 0,
        consumed: 0,
      };
    },
    onPointerMove: (event: React.PointerEvent) => {
      const g = gesture.current;
      if (!g || g.id !== event.pointerId) return;
      const dx = event.clientX - g.x0;
      const dy = event.clientY - g.y0;
      if (!g.swiping && !g.scrolling) {
        if (Math.hypot(dx, dy) < SWIPE_SLOP) return;
        const sideways = Math.abs(dx) > Math.abs(dy);
        if (sideways ? !onNavigate : !onScroll) {
          gesture.current = null;
          return;
        }
        if (sideways) g.swiping = true;
        else {
          g.scrolling = true;
          if (ref.current) ref.current.dataset.dragging = "true";
        }
        ref.current?.setPointerCapture?.(event.pointerId);
      }
      if (g.scrolling) {
        g.dy = dy;
        const row = rowOf(ref.current);
        let passed = 0;
        while (g.dy - g.consumed > row / 2) {
          g.consumed += row;
          passed -= 1;
        }
        while (g.dy - g.consumed < -row / 2) {
          g.consumed -= row;
          passed += 1;
        }
        if (passed) onScroll?.(passed);
        lift(g.dy - g.consumed);
        return;
      }
      g.dx = dx;
      move(dx * 0.9);
    },
    onPointerUp: (event: React.PointerEvent) => end(event, false),
    onPointerCancel: (event: React.PointerEvent) => end(event, true),
    onClickCapture: (event: React.MouseEvent) => {
      if (suppressClick.current) {
        event.stopPropagation();
        event.preventDefault();
      }
    },
  };
}

function useWheelWeeks(ref: React.RefObject<HTMLDivElement | null>, onScroll?: (weeks: number) => void) {
  const latest = React.useRef(onScroll);
  latest.current = onScroll;
  const enabled = Boolean(onScroll);
  React.useEffect(() => {
    const element = ref.current;
    if (!element || !enabled) return;
    let turned = 0;
    let last = 0;
    const wheel = (event: WheelEvent) => {
      if (event.ctrlKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
      event.preventDefault();
      if (event.timeStamp - last > 400) turned = 0;
      last = event.timeStamp;
      turned += event.deltaMode === 1 ? event.deltaY * WHEEL_LINE : event.deltaMode === 2 ? event.deltaY * 400 : event.deltaY;
      const weeks = Math.trunc(turned / WHEEL_WEEK);
      if (!weeks) return;
      turned -= weeks * WHEEL_WEEK;
      latest.current?.(weeks);
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [ref, enabled]);
}

export function MonthGrid({
  month,
  from,
  events,
  label,
  selectedDay,
  selectedId,
  onDayClick,
  onEventClick,
  onNavigate,
  onScroll,
  now: fixedNow,
}: MonthGridProps) {
  const days = React.useMemo(() => (from ? dayRange(mondayOf(from), 42) : monthDays(month)), [from, month]);
  const today = dayKey(fixedNow ?? new Date());
  const current = month.slice(0, 7);
  const ref = React.useRef<HTMLDivElement>(null);
  const [size, setSize] = React.useState({ width: 1024, row: 120 });
  const swipe = useMonthSwipe(ref, onNavigate, onScroll);
  useWheelWeeks(ref, onScroll);

  const first = days[0]!;
  const shownFirst = React.useRef(first);
  React.useLayoutEffect(() => {
    const before = shownFirst.current;
    shownFirst.current = first;
    if (before === first || ref.current?.dataset.dragging) return;
    const weeks = Math.round((dayStart(first).getTime() - dayStart(before).getTime()) / (7 * 86_400_000));
    if (Math.abs(weeks) > 2 || reducedMotion()) return;
    const row = rowOf(ref.current);
    weeksOf(ref.current).forEach((week) =>
      week.animate?.([{ transform: `translate3d(0,${weeks * row}px,0)` }, { transform: "translate3d(0,0,0)" }], {
        duration: SCROLL_MS,
        easing: "cubic-bezier(.2,.8,.3,1)",
      }),
    );
  }, [first]);

  React.useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      const row = element.querySelector<HTMLElement>(".mg-week");
      setSize({ width: element.clientWidth, row: row?.clientHeight ?? 120 });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const compact = size.width < COMPACT_BELOW;
  const step = compact ? LINE_COMPACT : LINE;
  const lines = Math.max(1, Math.floor((size.row - (compact ? HEAD_COMPACT : HEAD) - 4) / step));

  const strip = React.useMemo(() => events.filter(isStripEvent), [events]);
  const timed = React.useMemo(
    () =>
      events
        .filter((event) => !isStripEvent(event) && !event.background)
        .sort((a, b) => toDate(a.start).getTime() - toDate(b.start).getTime()),
    [events],
  );
  const backgrounds = React.useMemo(() => strip.filter((event) => event.background), [strip]);

  const weeks = React.useMemo(
    () =>
      Array.from({ length: 6 }, (_, index) => {
        const week = days.slice(index * 7, index * 7 + 7);
        return { week, ...layoutBars(strip, week, timed), tints: layoutBars(backgrounds, week).bars };
      }),
    [days, strip, timed, backgrounds],
  );

  return (
    <div
      ref={ref}
      className="mg"
      data-compact={compact || undefined}
      data-swipe={onNavigate ? true : undefined}
      data-scroll={onScroll ? true : undefined}
      role="grid"
      aria-label={label ?? formatMonth(month)}
      {...swipe}
    >
      <div className="mg-weekdays" role="row">
        {weekdays(compact ? "narrow" : "short").map((name, index) => (
          <span key={index} className="mg-weekday" role="columnheader">
            {name}
          </span>
        ))}
      </div>
      {weeks.map(({ week, bars, perDay, tints }) => {
        const shownPerDay = perDay.map((count) => (count > lines ? lines - 1 : lines));
        return (
          <div key={week[0]} className="mg-week" role="row" style={{ "--lines": lines } as React.CSSProperties}>
            {tints.map((tint) => (
              <div
                key={`tint-${tint.event.id}`}
                className="mg-backdrop"
                data-tone={tint.event.tone}
                style={{ "--column": tint.column, "--span": tint.span } as React.CSSProperties}
                aria-hidden="true"
              />
            ))}
            {week.map((day, index) => {
              const date = dayStart(day);
              const hidden = bars.filter(
                (bar) => bar.row >= shownPerDay[index]! && bar.column <= index && index < bar.column + bar.span,
              ).length;
              return (
                <div
                  key={day}
                  className="mg-day"
                  role="gridcell"
                  data-outside={day.slice(0, 7) !== current || undefined}
                  data-today={day === today || undefined}
                  data-selected={day === selectedDay || undefined}
                  data-weekend={date.getDay() % 6 === 0 || undefined}
                  onClick={() => onDayClick?.(day)}
                >
                  <button
                    type="button"
                    className="mg-date"
                    aria-label={dayLong().format(date)}
                    onClick={(event) => {
                      event.stopPropagation();
                      onDayClick?.(day);
                    }}
                  >
                    {date.getDate() === 1 && !compact
                      ? `${date.getDate()} ${dates({ month: "short" }).format(date).replace(".", "")}`
                      : date.getDate()}
                  </button>
                  {hidden > 0 && (
                    <button
                      type="button"
                      className="mg-more"
                      style={{ "--row": shownPerDay[index] } as React.CSSProperties}
                      onClick={(event) => {
                        event.stopPropagation();
                        onDayClick?.(day);
                      }}
                    >
                      {compact ? `+${hidden}` : say("month.more", { count: hidden })}
                    </button>
                  )}
                </div>
              );
            })}
            <div className="mg-items" role="gridcell" aria-label={say("month.this_week")}>
            {bars.map((bar) => {
              const fits = Array.from({ length: bar.span }, (_, k) => bar.row < shownPerDay[bar.column + k]!).every(Boolean);
              if (!fits) return null;
              const isBar = isStripEvent(bar.event);
              const start = toDate(bar.event.start);
              return (
                <button
                  key={`${bar.event.id}-${week[0]}`}
                  type="button"
                  className="mg-item"
                  data-kind={isBar ? "bar" : "timed"}
                  data-tone={bar.event.tone}
                  data-background={bar.event.background || undefined}
                  data-subscribed={bar.event.subscribed || undefined}
                  data-status={bar.event.status && bar.event.status !== "confirmed" ? bar.event.status : undefined}
                  data-past={toDate(bar.event.end).getTime() <= (fixedNow ?? new Date()).getTime() || undefined}
                  data-selected={selectedId === bar.event.id || undefined}
                  data-before={bar.continuesBefore || undefined}
                  data-after={bar.continuesAfter || undefined}
                  style={{ "--column": bar.column, "--span": bar.span, "--row": bar.row } as React.CSSProperties}
                  aria-label={describe(bar.event)}
                  onClick={(event) => {
                    event.stopPropagation();
                    onEventClick?.(bar.event.id);
                  }}
                >
                  {!compact && (
                    <>
                      {!isBar && <span className="mg-dot" aria-hidden="true" />}
                      {!isBar && <span className="mg-time">{formatClock(start)}</span>}
                      <span className="mg-title">{bar.event.title || say("untitled")}</span>
                    </>
                  )}
                </button>
              );
            })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export interface MiniMonthProps {
  month: string;
  range?: string[];
  marked?: Set<string>;
  weekNumbers?: boolean;
  onSelect: (day: string) => void;
  onMonthChange: (step: -1 | 1) => void;
  now?: Date;
}

export function MiniMonth({ month, range = [], marked, weekNumbers = false, onSelect, onMonthChange, now }: MiniMonthProps) {
  const days = monthDays(month);
  const today = dayKey(now ?? new Date());
  const current = month.slice(0, 7);
  const inRange = new Set(range);
  return (
    <div className="mini" data-weeks={weekNumbers || undefined}>
      <header className="mini-head">
        <h3 className="mini-title">{formatMonth(month)}</h3>
        <IconButton icon="chevron-left" label={say("calendar.previous_month")} size="small" variant="plain" onClick={() => onMonthChange(-1)} />
        <IconButton icon="chevron-right" label={say("calendar.next_month")} size="small" variant="plain" onClick={() => onMonthChange(1)} />
      </header>
      <div className="mini-grid" role="grid" aria-label={formatMonth(month)}>
        <div className="mini-row" role="row">
          {weekNumbers && <span className="mini-weekday" aria-hidden="true" />}
          {weekdays("narrow").map((name, index) => (
            <span key={index} className="mini-weekday" role="columnheader">
              {name}
            </span>
          ))}
        </div>
        {Array.from({ length: Math.ceil(days.length / 7) }, (_, week) => (
          <div key={days[week * 7]} className="mini-row" role="row">
            {weekNumbers && <span className="mini-week">{isoWeek(days[week * 7]!)}</span>}
            {days.slice(week * 7, week * 7 + 7).map((day, column) => {
              const index = week * 7 + column;
              const date = dayStart(day);
              const first = index % 7 === 0 || !inRange.has(addDays(day, -1));
              const last = index % 7 === 6 || !inRange.has(addDays(day, 1));
              return (
                <button
                  key={day}
                  type="button"
                  className="mini-day"
                  role="gridcell"
                  data-outside={day.slice(0, 7) !== current || undefined}
                  data-today={day === today || undefined}
                  data-in-range={inRange.has(day) || undefined}
                  data-range-start={(inRange.has(day) && first) || undefined}
                  data-range-end={(inRange.has(day) && last) || undefined}
                  aria-label={dayLong().format(date)}
                  aria-current={day === today ? "date" : undefined}
                  onClick={() => onSelect(day)}
                >
                  <span className="mini-number">{date.getDate()}</span>
                  {marked?.has(day) && <span className="mini-dot" aria-hidden="true" />}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

