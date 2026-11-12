import { useEffect, useState } from "react";

export const REFRESH_MS = 5 * 60_000;

export const CHECK_MS = 15_000;

export function useTick(every: number = REFRESH_MS): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let last = Date.now();
    const check = () => {
      if (document.visibilityState !== "visible" || Date.now() - last < every) return;
      last = Date.now();
      setTick((now) => now + 1);
    };
    const timer = window.setInterval(check, Math.min(CHECK_MS, every));
    document.addEventListener("visibilitychange", check);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
    };
  }, [every]);
  return tick;
}
