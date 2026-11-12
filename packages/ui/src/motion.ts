"use client";

import * as React from "react";

const STIFFNESS = 170;
const DAMPING = 26;
const REST = 0.001;
const MAX_STEP = 1 / 30;

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = React.useState(false);

  React.useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  return reduced;
}

const useIsomorphicLayoutEffect =
  typeof window === "undefined" ? React.useEffect : React.useLayoutEffect;

export function useAnimatedNumber(target: number, from = 0): number {
  const reduced = usePrefersReducedMotion();
  const [value, setValue] = React.useState(target);

  const state = React.useRef({ value: target, velocity: 0 });
  const frame = React.useRef<number>(undefined);
  const started = React.useRef(false);

  useIsomorphicLayoutEffect(() => {
    if (started.current) return;
    started.current = true;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    state.current = { value: from, velocity: 0 };
    setValue(from);
  }, [from]);

  React.useEffect(() => {
    if (reduced || !Number.isFinite(target)) {
      state.current = { value: target, velocity: 0 };
      setValue(target);
      return;
    }

    let previous = performance.now();

    const step = (now: number) => {
      const scale = Math.max(1, Math.abs(target - from));
      let elapsed = (now - previous) / 1000;
      previous = now;

      while (elapsed > 0) {
        const dt = Math.min(elapsed, MAX_STEP);
        elapsed -= dt;
        const force = -STIFFNESS * (state.current.value - target);
        const drag = -DAMPING * state.current.velocity;
        state.current.velocity += (force + drag) * dt;
        state.current.value += state.current.velocity * dt;
      }

      const settled =
        Math.abs(state.current.value - target) < REST * scale &&
        Math.abs(state.current.velocity) < REST * scale;

      if (settled) {
        state.current = { value: target, velocity: 0 };
        setValue(target);
        return;
      }

      setValue(state.current.value);
      frame.current = requestAnimationFrame(step);
    };

    frame.current = requestAnimationFrame(step);
    return () => {
      if (frame.current !== undefined) cancelAnimationFrame(frame.current);
    };
  }, [target, reduced]);

  return value;
}

export function useHasMounted(): boolean {
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);
  return mounted;
}

export const entrance = (index: number): React.CSSProperties =>
  ({ "--enter-index": index }) as React.CSSProperties;
