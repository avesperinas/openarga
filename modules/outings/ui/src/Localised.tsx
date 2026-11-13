import { usePreferences } from "@openarga/app";
import { I18nProvider } from "@openarga/ui";
import type { ReactNode } from "react";

import { CATALOGS, setLocale, setTimeZone } from "./lang";

export function Localised({ children }: { children: ReactNode }) {
  const { locale, timezone } = usePreferences();
  setLocale(locale);
  setTimeZone(timezone);
  return (
    <I18nProvider key={`${locale}:${timezone}`} catalogs={CATALOGS} locale={locale}>
      {children}
    </I18nProvider>
  );
}
