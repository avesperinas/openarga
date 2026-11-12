"use client";

import { Icon, PageTabs, type PageTab } from "@openarga/ui";
import * as React from "react";

import { keyDirection, type PageSpan, positionOf, trackHeight, wheelPager } from "../lib/paging";

const SCROLL_QUIET_MS = 120;

const pageNodes = (track: HTMLElement) => Array.from(track.children) as HTMLElement[];

export const WIDE = "(hover: hover) and (pointer: fine) and (min-width: 1800px)";

function useWide(): boolean {
  const [wide, setWide] = React.useState(false);
  React.useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia(WIDE);
    const update = () => setWide(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return wide;
}

const scrollsInside = (from: EventTarget | null, until: Element) => {
  for (let node = from as Element | null; node && node !== until; node = node.parentElement) {
    const { overflowY } = getComputedStyle(node);
    if ((overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight) {
      return true;
    }
  }
  return false;
};

export function Pages({
  children,
  onCurrent,
  tabs,
  jump,
  spans,
}: {
  children: React.ReactNode[];
  spans?: PageSpan[];
  onCurrent?: (index: number) => void;
  tabs?: PageTab[];
  jump?: { index: number; at: number } | null;
}) {
  const track = React.useRef<HTMLDivElement>(null);
  const [current, setCurrent] = React.useState(0);
  const count = children.length;
  const wide = useWide();
  const starts = React.useMemo(
    () =>
      Array.from({ length: count }, (_, index) =>
        wide && spans && spans.length === count ? spans[index]!.start : index,
      ),
    [wide, spans, count],
  );
  const grouped = starts.some((start, index) => start !== index);
  const startsRef = React.useRef(starts);
  startsRef.current = starts;

  const aim = React.useRef<number | null>(null);

  const frame = React.useRef<number>(undefined);
  const fit = React.useCallback(() => {
    frame.current = undefined;
    const node = track.current;
    if (!node) return;
    const pages = pageNodes(node);
    const [first] = pages;
    const offsets = pages.map((page) => page.offsetLeft - (first?.offsetLeft ?? 0));
    const own = pages.map((page) => page.offsetHeight);
    const group = startsRef.current;
    const heights = own.map((_, index) =>
      Math.max(...own.filter((__, other) => group[other] === (group[index] ?? index))),
    );
    const height = trackHeight(heights, positionOf(offsets, node.scrollLeft), 1);
    if (height) node.style.height = `${height}px`;
  }, []);
  const refit = React.useCallback(() => {
    if (frame.current === undefined) frame.current = requestAnimationFrame(fit);
  }, [fit]);
  const quiet = React.useRef<ReturnType<typeof setTimeout>>(undefined);
  const refitWhenQuiet = React.useCallback(() => {
    clearTimeout(quiet.current);
    quiet.current = setTimeout(refit, SCROLL_QUIET_MS);
  }, [refit]);

  const onScroll = React.useCallback(() => {
    const node = track.current;
    if (!node) return;
    refitWhenQuiet();
    const pages = pageNodes(node);
    const [first] = pages;
    const offsets = pages.map((page) => page.offsetLeft - (first?.offsetLeft ?? 0));
    const index = Math.round(positionOf(offsets, node.scrollLeft));
    setCurrent(index);
    if (aim.current === index) aim.current = null;
    onCurrent?.(index);
  }, [onCurrent, refitWhenQuiet]);

  React.useEffect(() => {
    const node = track.current;
    if (!node) return;
    const observer = new ResizeObserver(refit);
    pageNodes(node).forEach((page) => observer.observe(page));
    observer.observe(node);
    refit();
    return () => {
      observer.disconnect();
      if (frame.current !== undefined) cancelAnimationFrame(frame.current);
      frame.current = undefined;
      clearTimeout(quiet.current);
    };
  }, [count, refit]);

  const goTo = React.useCallback((wanted: number) => {
    const node = track.current;
    if (!node) return;
    const pages = pageNodes(node);
    const [first] = pages;
    const index = startsRef.current[wanted] ?? wanted;
    const target = pages[index];
    if (!first || !target) return;
    aim.current = index;
    node.scrollTo({ left: target.offsetLeft - first.offsetLeft, behavior: "smooth" });
  }, []);

  const [scrubbing, setScrubbing] = React.useState(false);
  const scrubbed = React.useRef<number | null>(null);
  const scrub = (event: React.PointerEvent<HTMLElement>) => {
    const dots = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(".pages-dot"));
    let nearest = 0;
    let distance = Number.POSITIVE_INFINITY;
    dots.forEach((dot, index) => {
      const rect = dot.getBoundingClientRect();
      const gap = Math.abs(event.clientX - (rect.left + rect.width / 2));
      if (gap < distance) {
        distance = gap;
        nearest = index;
      }
    });
    if (scrubbed.current === nearest) return;
    scrubbed.current = nearest;
    goTo(nearest);
  };
  const onScrubStart = (event: React.PointerEvent<HTMLElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    scrubbed.current = aim.current ?? currentRef.current;
    setScrubbing(true);
    scrub(event);
  };
  const onScrubMove = (event: React.PointerEvent<HTMLElement>) => {
    if (scrubbing) scrub(event);
  };
  const onScrubEnd = () => {
    scrubbed.current = null;
    setScrubbing(false);
  };

  React.useEffect(() => {
    if (jump) goTo(jump.index);
  }, [jump, goTo]);

  const currentRef = React.useRef(current);
  currentRef.current = current;
  const countRef = React.useRef(count);
  countRef.current = count;

  const stepBy = React.useCallback(
    (direction: number) => {
      const from = startsRef.current[aim.current ?? currentRef.current] ?? 0;
      const firsts = [...new Set(startsRef.current)];
      const at = firsts.indexOf(from);
      const next = firsts[Math.min(Math.max(at + direction, 0), firsts.length - 1)] ?? from;
      if (next !== from) goTo(next);
    },
    [goTo],
  );

  React.useEffect(() => {
    const node = track.current;
    if (!node) return;

    const visible = () => node.getClientRects().length > 0;
    const blocked = () => document.querySelector('[aria-modal="true"]') !== null;

    const onKey = (event: KeyboardEvent) => {
      const direction = keyDirection(event.key);
      if (!direction || event.defaultPrevented) return;
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const target = event.target as Element | null;
      if (target?.closest?.('input, textarea, select, [contenteditable="true"], [role="slider"]')) {
        return;
      }
      if (!visible() || blocked()) return;
      event.preventDefault();
      stepBy(direction);
    };

    const pager = wheelPager();
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey || !visible() || blocked()) return;
      if (Math.abs(event.deltaX) >= Math.abs(event.deltaY)) return;
      const scroller = document.scrollingElement;
      if (scroller && scroller.scrollHeight > scroller.clientHeight + 1) return;
      if (scrollsInside(event.target, document.body)) return;

      event.preventDefault();
      const direction = pager(event.deltaY, event.deltaMode, event.timeStamp, window.innerHeight);
      if (direction) stepBy(direction);
    };

    const onScrollEnd = () => {
      aim.current = null;
      refit();
    };

    window.addEventListener("keydown", onKey);
    window.addEventListener("wheel", onWheel, { passive: false });
    node.addEventListener("scrollend", onScrollEnd);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("wheel", onWheel);
      node.removeEventListener("scrollend", onScrollEnd);
    };
  }, [stepBy, refit]);

  return (
    <div className="pages" data-grouped={grouped || undefined}>
      {tabs && tabs.length > 1 && tabs.length === count && <PageTabs items={tabs} current={current} onSelect={goTo} />}
      <div className="pages-track" ref={track} onScroll={onScroll}>
        {children.map((page, index) => (
          <section
            className="pages-page"
            key={React.isValidElement(page) && page.key !== null ? page.key : index}
            data-edge={grouped ? spans![index]!.edge : undefined}
            style={
              grouped ? ({ "--used": spans![index]!.used, "--group": spans![index]!.group } as React.CSSProperties) : undefined
            }
            aria-label={`Pantalla ${index + 1}`}
          >
            {page}
          </section>
        ))}
      </div>

      {count > 1 && (
        <>
          <button
            type="button"
            className="glass pages-arrow"
            data-side="previous"
            aria-label="Pantalla anterior"
            disabled={starts[current] === 0}
            onClick={() => stepBy(-1)}
          >
            <Icon name="chevron-left" />
          </button>
          <button
            type="button"
            className="glass pages-arrow"
            data-side="next"
            aria-label="Pantalla siguiente"
            disabled={starts[current] === starts[count - 1]}
            onClick={() => stepBy(1)}
          >
            <Icon name="chevron-right" />
          </button>

          <nav
            className="pages-dots"
            aria-label="Pantallas"
            data-scrubbing={scrubbing || undefined}
            onPointerDown={onScrubStart}
            onPointerMove={onScrubMove}
            onPointerUp={onScrubEnd}
            onPointerCancel={onScrubEnd}
          >
            {children.map((_, index) => (
              <button
                key={index}
                type="button"
                className="pages-dot"
                data-active={starts[index] === starts[current] || undefined}
                aria-label={`Ir a la pantalla ${index + 1}`}
                aria-current={index === current}
                onClick={() => goTo(index)}
              />
            ))}
          </nav>
        </>
      )}
    </div>
  );
}
