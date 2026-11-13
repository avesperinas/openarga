"use client";

import * as React from "react";

import {
  type CalendarEvent,
  MINUTES_PER_DAY,
  SNAP_MINUTES,
  type Segment,
  addDays,
  atMinute,
  backdropsOf,
  dayKey,
  dayStart,
  formatClock,
  formatSpan,
  hourLabel,
  isStripEvent,
  isoWeek,
  layoutBars,
  layoutDay,
  segmentsOf,
  snap,
  toDate,
  wallMinutes,
} from "./calendar-layout";
import { Icon } from "./icons";
import { dates } from "./regional";

export interface TimeRange {
  start: Date;
  end: Date;
}

export interface TimeGridProps {
  days: string[];
  events: CalendarEvent[];
  label: string;
  hourHeight?: number;
  onHourHeightChange?: (height: number) => void;
  showDates?: boolean;
  weekNumber?: boolean;
  scrollToHour?: number;
  selectedId?: string | null;
  onEventClick?: (id: string) => void;
  onEventChange?: (id: string, range: TimeRange) => void | Promise<unknown>;
  onCreate?: (range: TimeRange & { allDay?: boolean }, title?: string) => void | Promise<unknown>;
  inlineCreate?: boolean;
  pending?: TimeRange | null;
  onDayClick?: (day: string) => void;
  onNavigate?: (step: -1 | 1) => void;
  onNavigateDays?: (days: number) => void;
  now?: Date;
}

export const HOUR_HEIGHT = { min: 24, default: 48, max: 160 } as const;
const ONE_LINE_PX = 36;
const MIN_EVENT_PX = 18;
const CASCADE_PX = 28;
const BACKDROP_LABEL_PX = 18;
const LONG_PRESS_MS = 380;
const TOUCH_SLOP = 8;
const MOUSE_SLOP = 4;
const EDGE_SCROLL = 48;
const STRIP_MAX_ROWS = 2;
const STRIP_FOLDED_ROWS = 2;

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
const useBrowserLayoutEffect = typeof window === "undefined" ? React.useEffect : React.useLayoutEffect;

type Ghost = {
  kind: "create" | "move" | "resize";
  id?: string;
  day: number;
  top: number;
  bottom: number;
  tone?: CalendarEvent["tone"];
  settling?: boolean;
};

type Gesture = {
  pointerId: number;
  touch: boolean;
  x0: number;
  y0: number;
  x: number;
  y: number;
  target: "empty" | "event" | "handle";
  id?: string;
  mode: "pending" | "create" | "move" | "resize" | "swipe";
  timer?: ReturnType<typeof setTimeout>;
  anchorDay: number;
  anchorMinute: number;
  grab: number;
  duration: number;
  originalDay: number;
  originalTop: number;
};

const weekdayShort = () => dates({ weekday: "short" });
const weekdayLong = () => dates({ weekday: "long", day: "numeric", month: "long" });

export function TimeGrid({
  days,
  events,
  label,
  hourHeight,
  onHourHeightChange,
  showDates = true,
  weekNumber = false,
  scrollToHour,
  selectedId,
  onEventClick,
  onEventChange,
  onCreate,
  inlineCreate = false,
  pending,
  onDayClick,
  onNavigate: onNavigateView,
  onNavigateDays,
  now: fixedNow,
}: TimeGridProps) {
  const [ownHeight, setOwnHeight] = React.useState<number>(HOUR_HEIGHT.default);
  const hh = hourHeight ?? ownHeight;
  const commitHeight = React.useCallback(
    (height: number) => {
      const next = Math.round(clamp(height, HOUR_HEIGHT.min, HOUR_HEIGHT.max));
      setOwnHeight(next);
      onHourHeightChange?.(next);
    },
    [onHourHeightChange],
  );

  const swipeByDay = !!onNavigateDays;
  const onNavigate = onNavigateDays ?? onNavigateView;
  const now = useMinute(fixedNow);
  const today = dayKey(now);

  const rootRef = React.useRef<HTMLDivElement>(null);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const columnsRef = React.useRef<HTMLDivElement>(null);
  const slidersRef = React.useRef<(HTMLElement | null)[]>([]);
  const gestureRef = React.useRef<Gesture | null>(null);
  const suppressClickRef = React.useRef(false);
  const liveHeightRef = React.useRef(hh);
  liveHeightRef.current = hh;

  const [ghost, setGhostState] = React.useState<Ghost | null>(null);
  const ghostRef = React.useRef<Ghost | null>(null);
  const setGhost = React.useCallback((next: Ghost | null) => {
    ghostRef.current = next;
    setGhostState(next);
  }, []);
  const [draft, setDraft] = React.useState<{ day: number; top: number; bottom: number } | null>(null);
  const [stripOpen, setStripOpen] = React.useState(false);

  const foreground = React.useMemo(() => events.filter((event) => !event.background), [events]);
  const strip = React.useMemo(
    () => layoutBars(events.filter(isStripEvent), days),
    [events, days],
  );
  const placed = React.useMemo(() => {
    const minimumMinutes = Math.min((MIN_EVENT_PX / hh) * 60, SNAP_MINUTES);
    const cascadeAfter = Math.max(30, (CASCADE_PX / hh) * 60);
    return days.map((day) => layoutDay(segmentsOf(foreground, day), { minimumMinutes, cascadeAfter }));
  }, [foreground, days, hh]);
  const backdrops = React.useMemo(() => {
    const labelMinutes = (BACKDROP_LABEL_PX / hh) * 60;
    const minimumMinutes = (MIN_EVENT_PX / hh) * 60;
    return days.map((day, index) =>
      backdropsOf(events, day, {
        labelMinutes,
        busy: placed[index]!.map((p): [number, number] => [
          p.segment.top,
          Math.max(p.segment.bottom, p.segment.top + minimumMinutes),
        ]),
      }),
    );
  }, [events, days, placed, hh]);
  const byId = React.useMemo(() => new Map(events.map((event) => [event.id, event])), [events]);

  const initialHour = scrollToHour ?? (days.includes(today) ? Math.max(0, wallMinutes(now) / 60 - 1.5) : 7);
  useBrowserLayoutEffect(() => {
    const scroller = scrollRef.current;
    if (scroller) scroller.scrollTop = initialHour * hh;
  }, []);

  const locate = React.useCallback(
    (clientX: number, clientY: number) => {
      const rect = columnsRef.current!.getBoundingClientRect();
      const width = rect.width / days.length;
      const day = clamp(Math.floor((clientX - rect.left) / width), 0, days.length - 1);
      const minute = clamp(((clientY - rect.top) / liveHeightRef.current) * 60, 0, MINUTES_PER_DAY);
      return { day, minute };
    },
    [days.length],
  );

  const rangeOf = (day: number, top: number, bottom: number): TimeRange => ({
    start: atMinute(days[day]!, top),
    end: atMinute(days[day]!, bottom),
  });

  const update = React.useCallback(() => {
    const g = gestureRef.current;
    if (!g) return;
    const { day, minute } = locate(g.x, g.y);
    if (g.mode === "create") {
      const a = snap(g.anchorMinute - SNAP_MINUTES / 2);
      const b = snap(minute - SNAP_MINUTES / 2);
      const top = clamp(Math.min(a, b), 0, MINUTES_PER_DAY - SNAP_MINUTES);
      const bottom = clamp(Math.max(a, b) + SNAP_MINUTES, top + SNAP_MINUTES, MINUTES_PER_DAY);
      setGhost({ kind: "create", day: g.anchorDay, top, bottom });
    } else if (g.mode === "move") {
      const top = clamp(snap(minute - g.grab), 0, MINUTES_PER_DAY - Math.min(g.duration, MINUTES_PER_DAY));
      setGhost({
        kind: "move",
        id: g.id,
        day,
        top,
        bottom: Math.min(MINUTES_PER_DAY, top + g.duration),
        tone: byId.get(g.id!)?.tone,
      });
    } else if (g.mode === "resize") {
      const bottom = clamp(snap(minute), g.originalTop + SNAP_MINUTES, MINUTES_PER_DAY);
      setGhost({ kind: "resize", id: g.id, day: g.originalDay, top: g.originalTop, bottom, tone: byId.get(g.id!)?.tone });
    }
  }, [locate, byId, setGhost]);

  const edgeFrame = React.useRef<number | null>(null);
  const edgeScroll = React.useCallback(() => {
    const g = gestureRef.current;
    const scroller = scrollRef.current;
    edgeFrame.current = null;
    if (!g || !scroller || !["create", "move", "resize"].includes(g.mode)) return;
    const rect = scroller.getBoundingClientRect();
    const speed =
      g.y < rect.top + EDGE_SCROLL ? -(rect.top + EDGE_SCROLL - g.y) / 3
      : g.y > rect.bottom - EDGE_SCROLL ? (g.y - (rect.bottom - EDGE_SCROLL)) / 3
      : 0;
    if (speed !== 0) {
      scroller.scrollTop += speed;
      update();
      edgeFrame.current = requestAnimationFrame(edgeScroll);
    }
  }, [update]);

  const activate = (g: Gesture, mode: Gesture["mode"]) => {
    g.mode = mode;
    if (g.timer) clearTimeout(g.timer);
    if (g.touch && mode !== "swipe") navigator.vibrate?.(8);
    try {
      columnsRef.current?.setPointerCapture(g.pointerId);
    } catch {
    }
    setDraft(null);
    update();
  };

  const onPointerDown = (event: React.PointerEvent) => {
    if (event.button !== 0 || gestureRef.current) return;
    const element = (event.target as HTMLElement).closest<HTMLElement>("[data-event-id], [data-handle], [data-draft]");
    if (element?.hasAttribute("data-draft")) return;
    const id = element?.closest<HTMLElement>("[data-event-id]")?.dataset.eventId;
    const source = id ? byId.get(id) : undefined;
    const editable = !!source && !source.readOnly && !!onEventChange && !isStripEvent(source);
    const target: Gesture["target"] = !id ? "empty" : element?.hasAttribute("data-handle") && editable ? "handle" : "event";
    const touch = event.pointerType !== "mouse";
    const { day, minute } = locate(event.clientX, event.clientY);

    let grab = 0;
    let duration = 60;
    let originalDay = day;
    let originalTop = 0;
    if (source && id) {
      const segmentDay = Number(element!.closest<HTMLElement>("[data-day-index]")?.dataset.dayIndex ?? day);
      const start = toDate(source.start);
      const end = toDate(source.end);
      duration = Math.max(SNAP_MINUTES, Math.round((end.getTime() - start.getTime()) / 60_000));
      originalDay = segmentDay;
      originalTop = days[segmentDay] === dayKey(start) ? wallMinutes(start) : 0;
      grab = minute - originalTop;
      if (days[segmentDay] !== dayKey(start)) grab = minute;
    }

    const g: Gesture = {
      pointerId: event.pointerId,
      touch,
      x0: event.clientX,
      y0: event.clientY,
      x: event.clientX,
      y: event.clientY,
      target,
      id,
      mode: "pending",
      anchorDay: day,
      anchorMinute: minute,
      grab,
      duration,
      originalDay,
      originalTop,
    };
    gestureRef.current = g;

    if (touch) {
      const wants = target === "empty" ? !!onCreate : editable;
      if (wants) {
        g.timer = setTimeout(() => {
          if (gestureRef.current !== g || g.mode !== "pending") return;
          activate(g, target === "empty" ? "create" : target === "handle" ? "resize" : "move");
        }, LONG_PRESS_MS);
      }
    } else if (target === "handle") {
      event.preventDefault();
      activate(g, "resize");
    }
  };

  const onPointerMove = (event: React.PointerEvent) => {
    const g = gestureRef.current;
    if (!g || g.pointerId !== event.pointerId) return;
    g.x = event.clientX;
    g.y = event.clientY;
    const dx = g.x - g.x0;
    const dy = g.y - g.y0;

    if (g.mode === "pending") {
      const slop = g.touch ? TOUCH_SLOP : MOUSE_SLOP;
      if (Math.hypot(dx, dy) < slop) return;
      if (g.touch) {
        if (g.timer) clearTimeout(g.timer);
        if (onNavigate && Math.abs(dx) > Math.abs(dy)) {
          g.mode = "swipe";
        } else {
          gestureRef.current = null;
          return;
        }
      } else if (g.target === "empty" && onCreate) {
        activate(g, "create");
      } else if (g.target === "event" && byId.get(g.id!) && !byId.get(g.id!)!.readOnly && onEventChange && !isStripEvent(byId.get(g.id!)!)) {
        activate(g, "move");
      } else {
        gestureRef.current = null;
        return;
      }
    }

    if (g.mode === "swipe") {
      slide(dx);
      return;
    }
    update();
    if (edgeFrame.current === null) edgeFrame.current = requestAnimationFrame(edgeScroll);
  };

  const finish = (event: React.PointerEvent, cancelled: boolean) => {
    const g = gestureRef.current;
    if (!g || g.pointerId !== event.pointerId) return;
    gestureRef.current = null;
    if (g.timer) clearTimeout(g.timer);
    if (edgeFrame.current !== null) cancelAnimationFrame(edgeFrame.current);
    edgeFrame.current = null;

    if (g.mode !== "pending") {
      suppressClickRef.current = true;
      setTimeout(() => (suppressClickRef.current = false), 0);
    }

    if (g.mode === "swipe") {
      const width = columnsRef.current?.getBoundingClientRect().width ?? 1;
      const dx = g.x - g.x0;
      if (cancelled) settleSlide(0);
      else if (swipeByDay) {
        const column = width / days.length;
        const moved = Math.abs(dx) / column;
        const count = Math.min(days.length, moved > 0.3 ? Math.max(1, Math.round(moved)) : 0);
        settleSlide(dx < 0 ? count : -count);
      } else settleSlide(Math.abs(dx) > width * 0.22 ? (dx < 0 ? 1 : -1) : 0);
      return;
    }

    if (g.mode === "pending") {
      if (!cancelled && !g.touch && g.target === "empty" && onCreate) {
        if (draft) {
          setDraft(null);
          return;
        }
        const top = clamp(Math.floor(g.anchorMinute / 30) * 30, 0, MINUTES_PER_DAY - 60);
        commitCreate(g.anchorDay, top, top + 60);
      } else if (g.touch && g.target === "empty") {
        setDraft(null);
      }
      return;
    }

    const current = ghostRef.current;
    if (cancelled || !current) {
      setGhost(null);
      return;
    }
    if (g.mode === "create") {
      commitCreate(current.day, current.top, current.bottom);
      setGhost(null);
      return;
    }
    const source = byId.get(g.id!);
    if (!source || !onEventChange) {
      setGhost(null);
      return;
    }
    const range = rangeOf(current.day, current.top, current.bottom);
    if (g.mode === "move") {
      range.end = new Date(range.start.getTime() + g.duration * 60_000);
    }
    if (
      range.start.getTime() === toDate(source.start).getTime() &&
      range.end.getTime() === toDate(source.end).getTime()
    ) {
      setGhost(null);
      return;
    }
    setGhost({ ...current, settling: true });
    Promise.resolve(onEventChange(source.id, range)).finally(() => setGhost(null));
  };

  const commitCreate = (day: number, top: number, bottom: number) => {
    if (!onCreate) return;
    if (inlineCreate) {
      setDraft({ day, top, bottom });
    } else {
      void onCreate(rangeOf(day, top, bottom));
    }
  };

  React.useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) return;
    let pinch: { distance: number; height: number; focus: number; offset: number } | null = null;
    const distance = (t: TouchList) => Math.hypot(t[0]!.clientX - t[1]!.clientX, t[0]!.clientY - t[1]!.clientY);
    const middle = (t: TouchList) => (t[0]!.clientY + t[1]!.clientY) / 2;

    const setLive = (height: number, focusMinute: number, offset: number) => {
      liveHeightRef.current = height;
      rootRef.current?.style.setProperty("--hour-height", `${height}px`);
      scroller.scrollTop = (focusMinute / 60) * height - offset;
    };

    const onTouchStart = (event: TouchEvent) => {
      if (event.touches.length !== 2) return;
      const g = gestureRef.current;
      if (g?.timer) clearTimeout(g.timer);
      gestureRef.current = null;
      setGhost(null);
      const rect = scroller.getBoundingClientRect();
      const offset = middle(event.touches) - rect.top;
      pinch = {
        distance: distance(event.touches),
        height: liveHeightRef.current,
        focus: ((scroller.scrollTop + offset) / liveHeightRef.current) * 60,
        offset,
      };
    };
    const onTouchMove = (event: TouchEvent) => {
      if (pinch && event.touches.length === 2) {
        event.preventDefault();
        const height = clamp(pinch.height * (distance(event.touches) / pinch.distance), HOUR_HEIGHT.min, HOUR_HEIGHT.max);
        setLive(height, pinch.focus, pinch.offset);
        return;
      }
      const g = gestureRef.current;
      if (g && g.mode !== "pending" && event.cancelable) event.preventDefault();
    };
    const onTouchEnd = (event: TouchEvent) => {
      if (pinch && event.touches.length < 2) {
        pinch = null;
        commitHeight(liveHeightRef.current);
      }
    };

    let wheelCommit: ReturnType<typeof setTimeout> | undefined;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      const rect = scroller.getBoundingClientRect();
      const offset = event.clientY - rect.top;
      const focus = ((scroller.scrollTop + offset) / liveHeightRef.current) * 60;
      const height = clamp(liveHeightRef.current * Math.exp(-event.deltaY * (event.deltaMode === 1 ? 0.05 : 0.004)), HOUR_HEIGHT.min, HOUR_HEIGHT.max);
      setLive(height, focus, offset);
      clearTimeout(wheelCommit);
      wheelCommit = setTimeout(() => commitHeight(liveHeightRef.current), 160);
    };

    scroller.addEventListener("touchstart", onTouchStart, { passive: true });
    scroller.addEventListener("touchmove", onTouchMove, { passive: false });
    scroller.addEventListener("touchend", onTouchEnd);
    scroller.addEventListener("touchcancel", onTouchEnd);
    scroller.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      scroller.removeEventListener("touchstart", onTouchStart);
      scroller.removeEventListener("touchmove", onTouchMove);
      scroller.removeEventListener("touchend", onTouchEnd);
      scroller.removeEventListener("touchcancel", onTouchEnd);
      scroller.removeEventListener("wheel", onWheel);
      clearTimeout(wheelCommit);
    };
  }, [commitHeight]);

  const slide = (dx: number) => {
    const eased = dx * 0.9;
    for (const element of slidersRef.current) {
      if (element) element.style.transform = `translate3d(${eased}px, 0, 0)`;
    }
  };

  const settleSlide = (step: number) => {
    const elements = slidersRef.current.filter((element): element is HTMLElement => !!element);
    const width = columnsRef.current?.getBoundingClientRect().width ?? 0;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    const clear = () => elements.forEach((element) => (element.style.transform = ""));
    if (step === 0 || !onNavigate) {
      elements.forEach((element) => {
        const from = element.style.transform || "translate3d(0,0,0)";
        element.animate([{ transform: from }, { transform: "translate3d(0,0,0)" }], {
          duration: reduced ? 1 : 260,
          easing: "cubic-bezier(.2,.9,.3,1)",
        });
      });
      clear();
      return;
    }
    if (swipeByDay) {
      const distance = -step * (width / days.length);
      const run = elements.map((element) =>
        element.animate(
          [{ transform: element.style.transform || "translate3d(0,0,0)" }, { transform: `translate3d(${distance}px,0,0)` }],
          { duration: reduced ? 1 : 180, easing: "cubic-bezier(.2,.9,.3,1)", fill: "forwards" },
        ),
      );
      void Promise.all(run.map((animation) => animation.finished)).then(() => {
        clear();
        onNavigateDays?.(step);
        requestAnimationFrame(() => requestAnimationFrame(() => run.forEach((animation) => animation.cancel())));
      });
      return;
    }
    const out = elements.map((element) =>
      element.animate(
        [
          { transform: element.style.transform || "translate3d(0,0,0)" },
          { transform: `translate3d(${-step * width}px,0,0)`, opacity: 0.4 },
        ],
        { duration: reduced ? 1 : 170, easing: "cubic-bezier(.3,.6,.4,1)", fill: "forwards" },
      ),
    );
    void Promise.all(out.map((animation) => animation.finished)).then(() => {
      clear();
      onNavigateView?.(step < 0 ? -1 : 1);
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          out.forEach((animation) => animation.cancel());
          elements.forEach((element) =>
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

  const pendingSlot =
    pending && days.includes(dayKey(pending.start))
      ? {
          day: days.indexOf(dayKey(pending.start)),
          top: wallMinutes(pending.start),
          bottom: dayKey(pending.end) === dayKey(pending.start) ? wallMinutes(pending.end) : MINUTES_PER_DAY,
        }
      : null;

  const folded = strip.rows > STRIP_MAX_ROWS && !stripOpen;
  const shownRows = folded ? STRIP_FOLDED_ROWS : Math.max(strip.rows, 1);
  const hiddenPerDay = days.map((_, index) =>
    folded ? strip.bars.filter((bar) => bar.row >= shownRows && bar.column <= index && index < bar.column + bar.span).length : 0,
  );

  const createAllDay = (index: number) => {
    if (!onCreate) return;
    const start = dayStart(days[index]!);
    const end = dayStart(addDays(days[index]!, 1));
    void onCreate({ start, end, allDay: true });
  };

  const style = {
    "--hour-height": `${hh}px`,
    "--days": days.length,
    "--strip-rows": shownRows,
  } as React.CSSProperties;

  return (
    <div
      ref={rootRef}
      className="tg"
      style={style}
      data-count={days.length}
      data-gesture={ghost ? ghost.kind : undefined}
    >
      <div
        ref={scrollRef}
        className="tg-scroll"
        role="region"
        aria-label={label}
        tabIndex={-1}
      >
        <div className="tg-top">
          <div className="tg-head">
            <div className="tg-corner">{weekNumber && days[0] && <span>S{isoWeek(days[0])}</span>}</div>
            <div className="tg-days-clip">
              <div className="tg-days" ref={(element) => { slidersRef.current[0] = element; }}>
                {days.map((day) => {
                  const date = dayStart(day);
                  const isToday = day === today;
                  const content = (
                    <>
                      <span className="tg-day-name">{weekdayShort().format(date).replace(".", "")}</span>
                      {showDates && <span className="tg-day-number">{date.getDate()}</span>}
                    </>
                  );
                  return onDayClick && showDates ? (
                    <button
                      key={day}
                      type="button"
                      className="tg-day"
                      data-today={isToday || undefined}
                      data-weekend={date.getDay() % 6 === 0 || undefined}
                      aria-label={weekdayLong().format(date)}
                      onClick={() => onDayClick(day)}
                    >
                      {content}
                    </button>
                  ) : (
                    <div key={day} className="tg-day" data-today={(showDates && isToday) || undefined}>
                      {content}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="tg-strip">
            <div className="tg-strip-gutter">
              {strip.rows > STRIP_MAX_ROWS && (
                <button
                  type="button"
                  className="tg-strip-toggle"
                  aria-expanded={stripOpen}
                  aria-label={stripOpen ? "Plegar lo de todo el día" : "Desplegar lo de todo el día"}
                  onClick={() => setStripOpen((open) => !open)}
                >
                  <Icon name={stripOpen ? "chevron-up" : "chevron-down"} />
                </button>
              )}
            </div>
            <div className="tg-strip-clip">
              <div className="tg-strip-body" ref={(element) => { slidersRef.current[1] = element; }}>
                {days.map((day, index) => (
                  <div
                    key={day}
                    className="tg-strip-cell"
                    data-weekend={dayStart(day).getDay() % 6 === 0 || undefined}
                    onDoubleClick={() => createAllDay(index)}
                  >
                    {backdrops[index]!
                      .filter((one) => one.inStrip)
                      .map((one) => (
                        <div key={one.segment.event.id} className="tg-backdrop" data-whole data-tone={one.segment.event.tone} aria-hidden="true" />
                      ))}
                    {hiddenPerDay[index]! > 0 && (
                      <button type="button" className="tg-strip-more" onClick={() => setStripOpen(true)}>
                        {hiddenPerDay[index]} más
                      </button>
                    )}
                  </div>
                ))}
                {strip.bars
                  .filter((bar) => bar.row < shownRows)
                  .map((bar) => (
                    <button
                      key={`${bar.event.id}-${bar.column}`}
                      type="button"
                      className="tg-bar"
                      {...eventData(bar.event, now, selectedId)}
                      data-background={bar.event.background || undefined}
                      data-before={bar.continuesBefore || undefined}
                      data-after={bar.continuesAfter || undefined}
                      style={{ "--column": bar.column, "--span": bar.span, "--row": bar.row } as React.CSSProperties}
                      aria-label={describe(bar.event)}
                      onClick={() => onEventClick?.(bar.event.id)}
                    >
                      <span className="tg-bar-title">{bar.event.title}</span>
                      {bar.event.recurring && <Icon name="repeat" />}
                      {bar.event.duplicateOf && <Icon name="layers" label={`También en ${bar.event.duplicateOf}`} />}
                    </button>
                  ))}
              </div>
            </div>
          </div>
        </div>

        <div className="tg-body">
          <div className="tg-gutter" aria-hidden="true">
            {Array.from({ length: 23 }, (_, index) => (
              <span key={index} className="tg-hour" style={{ "--hour": index + 1 } as React.CSSProperties}>
                {hourLabel(index + 1)}
              </span>
            ))}
            {days.includes(today) && showDates && (
              <span className="tg-now-label" style={{ "--at": wallMinutes(now) } as React.CSSProperties}>
                {formatClock(now)}
              </span>
            )}
          </div>
          <div className="tg-columns-clip">
            <div
              ref={(element) => {
                columnsRef.current = element;
                slidersRef.current[2] = element;
              }}
              className="tg-columns"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={(event) => finish(event, false)}
              onPointerCancel={(event) => finish(event, true)}
              onContextMenu={(event) => gestureRef.current?.touch && event.preventDefault()}
            >
              {days.map((day, dayIndex) => (
                <div
                  key={day}
                  className="tg-column"
                  data-day-index={dayIndex}
                  data-today={(showDates && day === today) || undefined}
                  data-weekend={dayStart(day).getDay() % 6 === 0 || undefined}
                >
                  {backdrops[dayIndex]!.map((one) => (
                    <div
                      key={`backdrop-${one.segment.event.id}`}
                      className="tg-backdrop"
                      data-tone={one.segment.event.tone}
                      data-subscribed={one.segment.event.subscribed || undefined}
                      data-before={one.segment.continuesBefore || undefined}
                      data-after={one.segment.continuesAfter || undefined}
                      data-lifted={(ghost?.id === one.segment.event.id && ghost.kind === "move") || undefined}
                      data-hidden={(ghost?.id === one.segment.event.id && ghost.kind === "resize") || undefined}
                      style={{ "--top": one.segment.top, "--bottom": one.segment.bottom } as React.CSSProperties}
                    >
                      {one.labelAt !== null && (
                        <button
                          type="button"
                          className="tg-backdrop-label"
                          data-backdrop
                          data-event-id={one.segment.event.id}
                          data-editable={(!one.segment.event.readOnly && !!onEventChange) || undefined}
                          data-selected={selectedId === one.segment.event.id || undefined}
                          style={{ "--label-at": one.labelAt - one.segment.top } as React.CSSProperties}
                          aria-label={describe(one.segment.event)}
                          onClick={() => {
                            if (suppressClickRef.current) {
                              suppressClickRef.current = false;
                              return;
                            }
                            onEventClick?.(one.segment.event.id);
                          }}
                        >
                          {one.segment.event.title || "Sin título"}
                        </button>
                      )}
                      {!one.segment.event.readOnly && !!onEventChange && !one.segment.continuesAfter && (
                        <span className="tg-backdrop-handle" data-event-id={one.segment.event.id} data-handle aria-hidden="true" />
                      )}
                    </div>
                  ))}
                  {placed[dayIndex]!.map((p) => (
                    <EventBlock
                      key={`${p.segment.event.id}-${day}`}
                      segment={p.segment}
                      left={p.left}
                      width={p.width}
                      layer={p.layer}
                      nested={p.nested}
                      hh={hh}
                      now={now}
                      selected={selectedId === p.segment.event.id}
                      lifted={ghost?.id === p.segment.event.id && ghost.kind === "move"}
                      hidden={ghost?.id === p.segment.event.id && ghost.kind === "resize"}
                      editable={!p.segment.event.readOnly && !!onEventChange}
                      onOpen={() => {
                        if (suppressClickRef.current) {
                          suppressClickRef.current = false;
                          return;
                        }
                        onEventClick?.(p.segment.event.id);
                      }}
                    />
                  ))}
                  {ghost && ghost.day === dayIndex && (
                    <GhostBlock ghost={ghost} source={ghost.id ? byId.get(ghost.id) : undefined} day={day} hh={hh} />
                  )}
                  {pendingSlot && pendingSlot.day === dayIndex && !ghost && (
                    <GhostBlock ghost={{ kind: "create", ...pendingSlot }} day={day} hh={hh} />
                  )}
                  {draft && draft.day === dayIndex && (
                    <DraftBlock
                      day={day}
                      top={draft.top}
                      bottom={draft.bottom}
                      onCancel={() => setDraft(null)}
                      onSave={(title) => {
                        setDraft(null);
                        void onCreate?.(rangeOf(dayIndex, draft.top, draft.bottom), title);
                      }}
                    />
                  )}
                  {showDates && day === today && (
                    <div className="tg-now" style={{ "--at": wallMinutes(now) } as React.CSSProperties} aria-hidden="true" />
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function eventData(event: CalendarEvent, now: Date, selectedId?: string | null) {
  return {
    "data-tone": event.tone,
    "data-status": event.status && event.status !== "confirmed" ? event.status : undefined,
    "data-subscribed": event.subscribed || undefined,
    "data-past": toDate(event.end).getTime() <= now.getTime() || undefined,
    "data-selected": selectedId === event.id || undefined,
  };
}

const dayMonth = () => dates({ weekday: "long", day: "numeric", month: "long" });

export function describe(event: CalendarEvent): string {
  const start = toDate(event.start);
  const end = toDate(event.end);
  const when = event.allDay || isStripEvent(event)
    ? `${dayMonth().format(start)}, todo el día`
    : `${dayMonth().format(start)}, ${formatSpan(start, end)}`;
  const status = event.status === "cancelled" ? ", cancelado" : event.status === "tentative" ? ", por confirmar" : "";
  const title = `${event.title || "Sin título"}${event.background ? ", de fondo" : ""}`;
  const twin = event.duplicateOf ? `también en ${event.duplicateOf}` : null;
  return [title, when + status, event.subtitle, twin].filter(Boolean).join(". ");
}

interface EventBlockProps {
  segment: Segment;
  left: number;
  width: number;
  layer: number;
  nested: boolean;
  hh: number;
  now: Date;
  selected: boolean;
  lifted: boolean;
  hidden: boolean;
  editable: boolean;
  onOpen: () => void;
}

const EventBlock = React.memo(function EventBlock({
  segment,
  left,
  width,
  layer,
  nested,
  hh,
  now,
  selected,
  lifted,
  hidden,
  editable,
  onOpen,
}: EventBlockProps) {
  const { event } = segment;
  const start = toDate(event.start);
  const end = toDate(event.end);
  const height = ((segment.bottom - segment.top) / 60) * hh;
  const oneLine = height < ONE_LINE_PX;
  return (
    <button
      type="button"
      className="tg-event"
      data-event-id={event.id}
      {...eventData(event, now, selected ? event.id : null)}
      data-one-line={oneLine || undefined}
      data-nested={nested || undefined}
      data-lifted={lifted || undefined}
      data-hidden={hidden || undefined}
      data-before={segment.continuesBefore || undefined}
      data-after={segment.continuesAfter || undefined}
      style={
        {
          "--top": segment.top,
          "--bottom": segment.bottom,
          "--left": left,
          "--width": width,
          "--layer": layer,
        } as React.CSSProperties
      }
      aria-label={describe(event)}
      onClick={onOpen}
    >
      <span className="tg-event-title">
        {event.title || "Sin título"}
        {event.recurring && <Icon name="repeat" />}
        {event.duplicateOf && <Icon name="layers" label={`También en ${event.duplicateOf}`} />}
      </span>
      <span className="tg-event-time">{oneLine ? formatClock(start) : formatSpan(start, end)}</span>
      {event.subtitle && !oneLine && <span className="tg-event-subtitle">{event.subtitle}</span>}
      {editable && !segment.continuesAfter && <span className="tg-event-handle" data-handle aria-hidden="true" />}
    </button>
  );
});

function GhostBlock({ ghost, source, day, hh }: { ghost: Ghost; source?: CalendarEvent; day: string; hh: number }) {
  const start = atMinute(day, ghost.top);
  const end = atMinute(day, ghost.bottom);
  const oneLine = ((ghost.bottom - ghost.top) / 60) * hh < ONE_LINE_PX;
  return (
    <div
      className="tg-event tg-ghost"
      data-kind={ghost.kind}
      data-tone={source?.tone ?? ghost.tone}
      data-subscribed={source?.subscribed || undefined}
      data-settling={ghost.settling || undefined}
      data-one-line={oneLine || undefined}
      style={{ "--top": ghost.top, "--bottom": ghost.bottom, "--left": 0, "--width": 1, "--layer": 90 } as React.CSSProperties}
      aria-hidden="true"
    >
      <span className="tg-event-title">{source?.title || "Nuevo evento"}</span>
      <span className="tg-event-time">{formatSpan(start, end)}</span>
    </div>
  );
}

function DraftBlock({
  day,
  top,
  bottom,
  onSave,
  onCancel,
}: {
  day: string;
  top: number;
  bottom: number;
  onSave: (title: string) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = React.useState("");
  const inputRef = React.useRef<HTMLInputElement>(null);
  React.useEffect(() => inputRef.current?.focus(), []);
  const done = React.useRef(false);
  const close = (save: boolean) => {
    if (done.current) return;
    done.current = true;
    if (save && title.trim()) onSave(title.trim());
    else onCancel();
  };
  return (
    <div
      className="tg-event tg-draft"
      data-draft
      style={{ "--top": top, "--bottom": bottom, "--left": 0, "--width": 1, "--layer": 95 } as React.CSSProperties}
    >
      <input
        ref={inputRef}
        className="tg-draft-input"
        value={title}
        placeholder="Título"
        aria-label="Título del evento nuevo"
        enterKeyHint="done"
        onChange={(event) => setTitle(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            close(true);
          } else if (event.key === "Escape") {
            event.stopPropagation();
            close(false);
          }
        }}
        onBlur={() => close(true)}
      />
      <span className="tg-event-time">{formatSpan(atMinute(day, top), atMinute(day, bottom))}</span>
    </div>
  );
}

function useMinute(fixed?: Date): Date {
  const fixedTime = fixed?.getTime();
  const [now, setNow] = React.useState(() => fixed ?? new Date());
  React.useEffect(() => {
    if (fixedTime !== undefined) {
      setNow(new Date(fixedTime));
      return;
    }
    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      setNow(new Date());
      timer = setTimeout(tick, 60_000 - (Date.now() % 60_000) + 50);
    };
    timer = setTimeout(tick, 60_000 - (Date.now() % 60_000) + 50);
    return () => clearTimeout(timer);
  }, [fixedTime]);
  return now;
}
