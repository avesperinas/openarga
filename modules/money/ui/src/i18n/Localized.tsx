import { I18nProvider, configureRegional, regionalFrom, resolveLocale } from "@openarga/ui";
import { type ReactNode, useEffect, useState } from "react";

import { catalogs } from ".";

interface Preferences {
  locale: string;
  timezone: string;
  currency: string;
  country?: string | null;
}

// TODO(platform): use usePreferences from @openarga/app once money/ui depends on it.
export function Localized({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  useEffect(() => {
    let alive = true;
    fetch("/api/kernel/me/preferences", { headers: { accept: "application/json" } })
      .then((response) => (response.ok ? (response.json() as Promise<Preferences>) : null))
      .catch(() => null)
      .then((found) => alive && found && setPreferences(found));
    return () => {
      alive = false;
    };
  }, []);
  if (preferences) configureRegional(regionalFrom(preferences));
  const locale = resolveLocale(preferences?.locale);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  const key = preferences ? `${preferences.locale}|${preferences.timezone}|${preferences.currency}` : "default";
  return (
    <I18nProvider key={key} catalogs={catalogs} locale={locale}>
      {children}
    </I18nProvider>
  );
}
