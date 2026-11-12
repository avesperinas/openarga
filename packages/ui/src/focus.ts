import * as React from "react";

export const useBrowserLayoutEffect = typeof window === "undefined" ? React.useEffect : React.useLayoutEffect;

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useBodyHost(): HTMLElement | null {
  const [host, setHost] = React.useState<HTMLElement | null>(null);
  useBrowserLayoutEffect(() => setHost(document.body), []);
  return host;
}

export function useFocusTrap(ref: React.RefObject<HTMLElement | null>, active = true): void {
  const before = React.useRef<HTMLElement | null>(null);
  if (before.current === null && typeof document !== "undefined") before.current = document.activeElement as HTMLElement | null;
  React.useEffect(() => {
    const box = ref.current;
    if (!active || !box) return;
    const previous = before.current;
    const inside = () => Array.from(box.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (!box.contains(document.activeElement)) (box.querySelector<HTMLElement>("[autofocus]") ?? box).focus();
    const keep = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const all = inside();
      if (all.length === 0) {
        event.preventDefault();
        return;
      }
      const first = all[0]!;
      const last = all[all.length - 1]!;
      if (event.shiftKey && (document.activeElement === first || document.activeElement === box)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    box.addEventListener("keydown", keep);
    return () => {
      box.removeEventListener("keydown", keep);
      if (previous && previous !== document.body && document.contains(previous) && !box.contains(previous)) previous.focus();
    };
  }, [ref, active]);
}

const escapes: (() => void)[] = [];
export function useEscape(onEscape: () => void, active = true): void {
  const latest = React.useRef(onEscape);
  latest.current = onEscape;
  React.useEffect(() => {
    if (!active) return;
    const mine = () => latest.current();
    escapes.push(mine);
    const listen = (event: KeyboardEvent) => {
      if (event.key === "Escape" && escapes[escapes.length - 1] === mine) {
        event.stopPropagation();
        mine();
      }
    };
    window.addEventListener("keydown", listen);
    return () => {
      window.removeEventListener("keydown", listen);
      escapes.splice(escapes.indexOf(mine), 1);
    };
  }, [active]);
}

