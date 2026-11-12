import * as React from "react";

import { Icon, type IconName } from "./icons";

export interface SwipeAction {
  label: string;
  icon: IconName;
  onAction: () => void;
  tone?: "danger" | "accent";
}

const SWIPE_OPEN = 48;
const SWIPE_FULL = 0.6;
const ACTION_WIDTH = 72;

export function swipeEnd(dx: number, width: number, actions: number): "open" | "closed" | "full" {
  const left = -dx;
  if (left >= width * SWIPE_FULL) return "full";
  if (left >= Math.min(SWIPE_OPEN, actions * ACTION_WIDTH)) return "open";
  return "closed";
}

export function SwipeRow({ children, actions, label }: { children: React.ReactNode; actions: SwipeAction[]; label: string }) {
  const [dx, setDx] = React.useState(0);
  const [settled, setSettled] = React.useState<"open" | "closed">("closed");
  const [moving, setMoving] = React.useState(false);
  const start = React.useRef<{ x: number; y: number; base: number; horizontal: boolean | null } | null>(null);
  const row = React.useRef<HTMLDivElement>(null);
  const reveal = actions.length * ACTION_WIDTH;

  const finish = (moved: number) => {
    const width = row.current?.getBoundingClientRect().width ?? 320;
    const end = swipeEnd(moved, width, actions.length);
    if (end === "full") {
      setDx(0);
      setSettled("closed");
      actions[0]?.onAction();
    } else {
      setSettled(end);
      setDx(end === "open" ? -reveal : 0);
    }
  };

  return (
    <div
      ref={row}
      className="swipe-row"
      data-open={settled === "open" || undefined}
      data-moving={moving || undefined}
      onPointerDown={(event) => {
        if (event.pointerType === "mouse") return;
        start.current = { x: event.clientX, y: event.clientY, base: dx, horizontal: null };
      }}
      onPointerMove={(event) => {
        const s = start.current;
        if (!s) return;
        const mx = event.clientX - s.x;
        const my = event.clientY - s.y;
        if (s.horizontal === null && Math.hypot(mx, my) > 8) s.horizontal = Math.abs(mx) > Math.abs(my);
        if (!s.horizontal) return;
        (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
        setMoving(true);
        setDx(Math.min(0, s.base + mx));
      }}
      onPointerUp={() => {
        const s = start.current;
        start.current = null;
        setMoving(false);
        if (s?.horizontal) finish(dx);
      }}
      onPointerCancel={() => {
        start.current = null;
        setMoving(false);
        setDx(settled === "open" ? -reveal : 0);
      }}
    >
      <div className="swipe-row-actions" role="group" aria-label={`Acciones de ${label}`}>
        {actions.map((action) => (
          <button
            key={action.label}
            type="button"
            className="swipe-row-action"
            data-tone={action.tone}
            tabIndex={0}
            onFocus={() => {
              setSettled("open");
              setDx(-reveal);
            }}
            onBlur={() => {
              setSettled("closed");
              setDx(0);
            }}
            onClick={() => {
              setSettled("closed");
              setDx(0);
              action.onAction();
            }}
          >
            <Icon name={action.icon} />
            <span>{action.label}</span>
          </button>
        ))}
      </div>
      <div
        className="swipe-row-content"
        data-moving={moving || undefined}
        style={dx ? { transform: `translateX(${dx}px)` } : undefined}
      >
        {children}
      </div>
    </div>
  );
}

const PULL_THRESHOLD = 64;
const PULL_RESISTANCE = 0.5;

export const pullDistance = (finger: number) => Math.max(0, finger) * PULL_RESISTANCE;

export function PullToRefresh({ onRefresh, children }: { onRefresh: () => Promise<unknown>; children: React.ReactNode }) {
  const [pull, setPull] = React.useState(0);
  const [busy, setBusy] = React.useState(false);
  const start = React.useRef<{ x: number; y: number } | null>(null);

  return (
    <div
      className="pull-to-refresh"
      data-busy={busy || undefined}
      onTouchStart={(event) => {
        if (busy || window.scrollY > 0 || !event.currentTarget.contains(event.target as Node)) return;
        const touch = event.touches[0];
        start.current = touch ? { x: touch.clientX, y: touch.clientY } : null;
      }}
      onTouchMove={(event) => {
        const s = start.current;
        const touch = event.touches[0];
        if (!s || !touch) return;
        if (Math.abs(touch.clientX - s.x) > Math.abs(touch.clientY - s.y)) {
          start.current = null;
          setPull(0);
          return;
        }
        setPull(pullDistance(touch.clientY - s.y));
      }}
      onTouchEnd={() => {
        if (start.current === null) return;
        start.current = null;
        if (pull >= PULL_THRESHOLD * PULL_RESISTANCE) {
          setBusy(true);
          setPull(0);
          void Promise.resolve()
            .then(onRefresh)
            .catch(() => undefined)
            .finally(() => setBusy(false));
        } else {
          setPull(0);
        }
      }}
    >
      <div
        className="pull-to-refresh-ring"
        aria-hidden={!busy}
        role={busy ? "status" : undefined}
        aria-label={busy ? "Actualizando" : undefined}
        style={pull ? { opacity: Math.min(1, pull / (PULL_THRESHOLD * PULL_RESISTANCE)) } : undefined}
      >
        <Icon name="repeat" />
      </div>
      <div className="pull-to-refresh-content" style={pull ? { transform: `translateY(${pull}px)` } : undefined}>
        {children}
      </div>
    </div>
  );
}

const PAGE_SWIPE = 80;

export function pageSwipe(start: number, end: number): "next" | "previous" | null {
  if (Math.abs(end - start) < PAGE_SWIPE) return null;
  return end < start ? "next" : "previous";
}

export function SwipeArea({
  onNext,
  onPrevious,
  children,
}: {
  onNext?: () => void;
  onPrevious?: () => void;
  children: React.ReactNode;
}) {
  const start = React.useRef<number | null>(null);
  return (
    <div
      className="swipe-area"
      onTouchStart={(event) => {
        start.current = event.touches[0]?.clientX ?? null;
      }}
      onTouchEnd={(event) => {
        const from = start.current;
        const to = event.changedTouches[0]?.clientX;
        start.current = null;
        if (from === null || to === undefined) return;
        const way = pageSwipe(from, to);
        if (way === "next") onNext?.();
        if (way === "previous") onPrevious?.();
      }}
    >
      {children}
    </div>
  );
}
