import { useCallback, useEffect, useState } from "react";
import { flushSync } from "react-dom";

type Transitioning = Document & { startViewTransition?: (update: () => void) => unknown };

export function withTransition(update: () => void): void {
  const doc = document as Transitioning;
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (typeof doc.startViewTransition !== "function" || reduced) {
    update();
    return;
  }
  doc.startViewTransition(() => flushSync(update));
}

export function useRoute<R>(parse: (path: string) => R, format: (route: R) => string): [R, (to: R) => void] {
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const back = () => withTransition(() => setPath(window.location.pathname));
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);

  const navigate = useCallback(
    (to: R) => {
      const target = format(to);
      if (target === window.location.pathname) return;
      withTransition(() => {
        window.history.pushState(null, "", target);
        setPath(target);
        window.scrollTo(0, 0);
      });
    },
    [format],
  );

  return [parse(path), navigate];
}
