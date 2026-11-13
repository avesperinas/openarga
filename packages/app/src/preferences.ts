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

const REMEMBERED = "arga-preferences";

let cached: Promise<Preferences> | null = null;

function isPreferences(value: unknown): value is Preferences {
  if (typeof value !== "object" || value === null) return false;
  const found = value as Record<string, unknown>;
  return (
    (found.locale === "en" || found.locale === "es") &&
    typeof found.timezone === "string" &&
    typeof found.currency === "string"
  );
}

export function rememberedPreferences(): Preferences | null {
  try {
    const found: unknown = JSON.parse(localStorage.getItem(REMEMBERED) ?? "null");
    return isPreferences(found) ? { ...FALLBACK, ...found } : null;
  } catch {
    return null;
  }
}

function remember(preferences: Preferences): void {
  try {
    localStorage.setItem(REMEMBERED, JSON.stringify(preferences));
  } catch {
    return;
  }
}

export function loadPreferences(fetcher: typeof fetch = fetch): Promise<Preferences> {
  cached ??= fetcher("/api/kernel/me/preferences", { headers: { accept: "application/json" } })
    .then(async (response) => {
      if (!response.ok) return rememberedPreferences() ?? FALLBACK;
      const found: unknown = await response.json();
      if (!isPreferences(found)) return rememberedPreferences() ?? FALLBACK;
      const preferences = { ...FALLBACK, ...found };
      remember(preferences);
      return preferences;
    })
    .catch(() => rememberedPreferences() ?? FALLBACK);
  return cached;
}

export function forgetPreferences(): void {
  cached = null;
}

export function usePreferences(): Preferences {
  const [preferences, setPreferences] = useState<Preferences>(() => rememberedPreferences() ?? FALLBACK);
  useEffect(() => {
    let alive = true;
    void loadPreferences().then((found) => alive && setPreferences(found));
    return () => {
      alive = false;
    };
  }, []);
  return preferences;
}
