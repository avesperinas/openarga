import { usePreferences } from "@openarga/app";
import { I18nProvider, resolveLocale } from "@openarga/ui";
import { type ReactNode, useEffect } from "react";

import { catalogs } from ".";

export function Localized({ children }: { children: ReactNode }) {
  const locale = resolveLocale(usePreferences().locale);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return (
    <I18nProvider catalogs={catalogs} locale={locale}>
      {children}
    </I18nProvider>
  );
}
