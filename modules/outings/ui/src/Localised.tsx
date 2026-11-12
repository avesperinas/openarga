import { usePreferences } from "@openarga/app";
import { I18nProvider } from "@openarga/ui";
import type { ReactNode } from "react";

import { CATALOGS, setLocale } from "./lang";

export function Localised({ children }: { children: ReactNode }) {
  const { locale } = usePreferences();
  setLocale(locale);
  return (
    <I18nProvider key={locale} catalogs={CATALOGS} locale={locale}>
      {children}
    </I18nProvider>
  );
}
