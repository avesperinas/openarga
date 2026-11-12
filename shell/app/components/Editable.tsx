"use client";

import { Button } from "@openarga/ui";
import * as React from "react";

import type { Breakpoint, DesktopLayout, Device, LayoutPage, WidgetSize } from "../lib/kernel";
import { request } from "../lib/session";
import {
  COLUMNS,
  type Desk,
  GAP,
  cellAt,
  cellNear,
  clampToGrid,
  createPage,
  move,
  movePage,
  nearestSize,
  remove,
  removePage,
  resize,
  spanOf,
} from "../lib/layout";

const SAVE_DEBOUNCE = 800;
const UNDO_MS = 5000;

const LONG_PRESS_MS = 420;
const SLOP = 10;

const DESKTOPS = "/api/kernel/ui/desktops";

const QUERIES = {
  desktop: "(min-width: 1024px) and (hover: hover) and (pointer: fine)",
  tablet: "(min-width: 640px)",
} as const;

function currentBreakpoint(): Breakpoint {
  if (window.matchMedia(QUERIES.desktop).matches) return "desktop";
  if (window.matchMedia(QUERIES.tablet).matches) return "tablet";
  return "mobile";
}

function onBreakpointChange(notify: () => void) {
  const lists = Object.values(QUERIES).map((query) => window.matchMedia(query));
  lists.forEach((list) => list.addEventListener("change", notify));
  return () => lists.forEach((list) => list.removeEventListener("change", notify));
}

export function useBreakpoint(): Breakpoint {
  return React.useSyncExternalStore(onBreakpointChange, currentBreakpoint, () => "mobile");
}

const NARROW = "(max-width: 559px)";
const TOUCH = "(pointer: coarse)";
const PHONE_SIDE = 600;

export function currentDevice(): Device {
  if (window.matchMedia(NARROW).matches) return "mobile";
  const side = Math.min(window.screen.width, window.screen.height);
  if (window.matchMedia(TOUCH).matches && side < PHONE_SIDE) return "mobile";
  return "desktop";
}

function onDeviceChange(notify: () => void) {
  const lists = [NARROW, TOUCH].map((query) => window.matchMedia(query));
  lists.forEach((list) => list.addEventListener("change", notify));
  return () => lists.forEach((list) => list.removeEventListener("change", notify));
}

export function useDevice(guess: Device): Device {
  return React.useSyncExternalStore(onDeviceChange, currentDevice, () => guess);
}

interface Removed {
  desk: Desk;
  label: string;
}

type Operation = (desk: Desk) => Desk;

export function useEditableDesk(initial: DesktopLayout, device: Device) {
  const [desk, setDesk] = React.useState<Desk>({
    pages: initial.pages,
    placements: initial.placements ?? {},
  });
  const [undo, setUndo] = React.useState<Removed | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const current = React.useRef(desk);
  const stamp = React.useRef(initial.updated_at);
  const pending = React.useRef<Operation[]>([]);
  const timer = React.useRef<ReturnType<typeof setTimeout>>(undefined);

  const commit = React.useCallback((next: Desk) => {
    current.current = next;
    setDesk(next);
  }, []);

  const save = React.useCallback(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      const sent = pending.current.length;
      const response = await request(`${DESKTOPS}/${device}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...current.current, updated_at: stamp.current }),
      }).catch(() => null);
      if (response?.ok) {
        stamp.current = (await response.json()).updated_at;
        pending.current = pending.current.slice(sent);
        return;
      }
      if (response?.status !== 409) return;

      const fresh = await request(DESKTOPS, { headers: { accept: "application/json" } })
        .then((answer) =>
          answer.ok ? (answer.json() as Promise<Record<Device, DesktopLayout>>) : null,
        )
        .then((both) => both?.[device] ?? null)
        .catch(() => null);
      if (!fresh) return;
      stamp.current = fresh.updated_at;
      commit(
        pending.current.reduce((acc, operation) => operation(acc), {
          pages: fresh.pages,
          placements: fresh.placements ?? {},
        }),
      );
      setNotice("Había cambios de otro dispositivo. Los tuyos van encima.");
      save();
    }, SAVE_DEBOUNCE);
  }, [commit, device]);

  const apply = React.useCallback(
    (operation: Operation) => {
      commit(operation(current.current));
      pending.current.push(operation);
      save();
    },
    [commit, save],
  );

  return { desk, apply, undo, setUndo, notice, setNotice };
}

export function useLongPress(onLongPress: () => void, enabled: boolean) {
  const timer = React.useRef<ReturnType<typeof setTimeout>>(undefined);
  const origin = React.useRef({ x: 0, y: 0 });

  const cancel = React.useCallback(() => {
    clearTimeout(timer.current);
    timer.current = undefined;
  }, []);

  React.useEffect(() => cancel, [cancel]);

  const onPointerDown = (event: React.PointerEvent) => {
    if (!enabled) return;
    origin.current = { x: event.clientX, y: event.clientY };
    clearTimeout(timer.current);
    timer.current = setTimeout(onLongPress, LONG_PRESS_MS);
  };

  const onPointerMove = (event: React.PointerEvent) => {
    if (timer.current === undefined) return;
    const travelled = Math.hypot(
      event.clientX - origin.current.x,
      event.clientY - origin.current.y,
    );
    if (travelled > SLOP) cancel();
  };

  return { onPointerDown, onPointerMove, onPointerUp: cancel, onPointerCancel: cancel };
}

interface Gesture {
  kind: "move" | "resize";
  id: string;
  sizes: WidgetSize[];
}

export function useGrid(
  pages: LayoutPage[],
  onDrop: (id: string, target: { page: number; x: number; y: number }) => void,
  onResize: (id: string, size: WidgetSize) => void,
  columns: number,
  gap: number,
) {
  const [gesture, setGesture] = React.useState<Gesture | null>(null);
  const [target, setTarget] = React.useState<{ page: number; x: number; y: number } | null>(null);
  const [pending, setPending] = React.useState<WidgetSize | null>(null);

  const node = React.useRef<HTMLElement | null>(null);
  const origin = React.useRef({ x: 0, y: 0 });
  const offset = React.useRef({ x: 0, y: 0 });
  const grip = React.useRef({ x: 0, y: 0 });
  const frame = React.useRef<number>(undefined);

  const outcome = React.useRef<{
    target: typeof target;
    pending: WidgetSize | null;
    gesture: Gesture | null;
  }>({ target: null, pending: null, gesture: null });
  outcome.current.gesture = gesture;

  const release = React.useCallback(() => {
    if (frame.current !== undefined) cancelAnimationFrame(frame.current);
    frame.current = undefined;
    if (node.current) {
      node.current.style.removeProperty("--drag-x");
      node.current.style.removeProperty("--drag-y");
    }
    node.current = null;
  }, []);

  const grab =
    (kind: "move" | "resize", id: string, sizes: WidgetSize[] = []) =>
    (event: React.PointerEvent) => {
      event.preventDefault();
      event.stopPropagation();
      node.current = (event.currentTarget as HTMLElement).closest<HTMLElement>(".grid-cell");
      origin.current = { x: event.clientX, y: event.clientY };
      const grid = node.current?.closest<HTMLElement>(".grid")?.getBoundingClientRect();
      const item = pages.flatMap((page) => page.items).find((i) => i.instance_id === id);
      if (grid && item) {
        const step = (grid.width - gap * (columns - 1)) / columns + gap;
        grip.current = {
          x: event.clientX - (grid.left + item.x * step),
          y: event.clientY - (grid.top + item.y * step),
        };
      } else {
        grip.current = { x: 0, y: 0 };
      }
      offset.current = { x: 0, y: 0 };
      outcome.current = { target: null, pending: null, gesture: { kind, id, sizes } };
      setGesture({ kind, id, sizes });
    };

  React.useEffect(() => {
    if (!gesture) return;

    const item = pages.flatMap((page) => page.items).find((i) => i.instance_id === gesture.id);
    if (!item) return;

    const paint = () => {
      frame.current = undefined;
      if (!node.current) return;
      node.current.style.setProperty("--drag-x", `${offset.current.x}px`);
      node.current.style.setProperty("--drag-y", `${offset.current.y}px`);
    };

    const onMove = (event: PointerEvent) => {
      offset.current = {
        x: event.clientX - origin.current.x,
        y: event.clientY - origin.current.y,
      };

      if (gesture.kind === "move" && frame.current === undefined) {
        frame.current = requestAnimationFrame(paint);
      }

      const under = document
        .elementFromPoint(event.clientX, event.clientY)
        ?.closest<HTMLElement>(".grid");
      if (!under) return;

      const pageIndex = Number(under.dataset.page);
      if (!Number.isInteger(pageIndex)) return;

      const rect = under.getBoundingClientRect();

      if (gesture.kind === "move") {
        const cell = cellNear(rect, columns, gap, {
          x: event.clientX - grip.current.x,
          y: event.clientY - grip.current.y,
        });
        const next = {
          page: pageIndex,
          x: clampToGrid(cell.x, spanOf(item.size)[0], columns),
          y: cell.y,
        };
        outcome.current.target = next;
        setTarget((current) =>
          current && current.page === next.page && current.x === next.x && current.y === next.y
            ? current
            : next,
        );
        return;
      }

      const cell = cellAt(rect, columns, gap, { x: event.clientX, y: event.clientY });
      const size = nearestSize(gesture.sizes, cell.x - item.x + 1, cell.y - item.y + 1);
      outcome.current.pending = size;
      setPending((current) => (current === size ? current : size));
    };

    const onUp = () => {
      const settled = outcome.current;
      if (settled.gesture?.kind === "move" && settled.target) {
        onDrop(settled.gesture.id, settled.target);
      }
      if (settled.gesture?.kind === "resize" && settled.pending) {
        onResize(settled.gesture.id, settled.pending);
      }
      release();
      setGesture(null);
      setTarget(null);
      setPending(null);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [gesture, pages, onDrop, onResize, columns, gap, release]);

  return {
    dragging: gesture?.kind === "move" ? gesture.id : null,
    resizing: gesture?.kind === "resize" ? gesture.id : null,
    pending,
    target,
    start: (id: string) => grab("move", id),
    startResize: (id: string, sizes: WidgetSize[]) => grab("resize", id, sizes),
  };
}

export function UndoToast({
  undo,
  onUndo,
  onDismiss,
}: {
  undo: { label: string } | null;
  onUndo: () => void;
  onDismiss: () => void;
}) {
  React.useEffect(() => {
    if (!undo) return;
    const timer = setTimeout(onDismiss, UNDO_MS);
    return () => clearTimeout(timer);
  }, [undo, onDismiss]);

  if (!undo) return null;
  return (
    <div className="glass toast" role="status">
      <span>{undo.label} quitado</span>
      <Button variant="plain" size="small" icon="undo" onClick={onUndo}>
        Deshacer
      </Button>
    </div>
  );
}

export { COLUMNS, GAP, createPage, move, movePage, remove, removePage, resize };
