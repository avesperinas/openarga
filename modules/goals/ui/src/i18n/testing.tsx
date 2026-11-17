import { I18nProvider, createT, type Locale } from "@openarga/ui";
import type { ReactNode } from "react";

import { catalogs } from ".";

export const english = createT(catalogs, "en");

export const spanish = createT(catalogs, "es");

export function inLocale(node: ReactNode, locale: Locale = "en") {
  return (
    <I18nProvider catalogs={catalogs} locale={locale}>
      {node}
    </I18nProvider>
  );
}
