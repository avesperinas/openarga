import { useEffect, useState } from "react";

export interface Preferences {
  locale: "en" | "es";
  timezone: string;
  currency: string;
  country: string | null;
  region: string | null;
  area: string | null;
}

export const FALLBACK: Preferences = {
  locale: "en",
  timezone: "UTC",
  currency: "EUR",
  country: null,
  region: null,
  area: null,
};

let cached: Promise<Preferences> | null = null;

export function loadPreferences(fetcher: typeof fetch = fetch): Promise<Preferences> {
  cached ??= fetcher("/api/kernel/me/preferences", { headers: { accept: "application/json" } })
    .then((response) => (response.ok ? (response.json() as Promise<Preferences>) : FALLBACK))
    .catch(() => FALLBACK);
  return cached;
}

export function forgetPreferences(): void {
  cached = null;
}

export function usePreferences(): Preferences {
  const [preferences, setPreferences] = useState<Preferences>(FALLBACK);
  useEffect(() => {
    let alive = true;
    void loadPreferences().then((found) => alive && setPreferences(found));
    return () => {
      alive = false;
    };
  }, []);
  return preferences;
}
