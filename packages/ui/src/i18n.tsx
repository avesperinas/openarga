"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

import { type Catalogs, type Locale, SOURCE_LOCALE, type Translate, createT, fill } from "./i18n-core";

export * from "./i18n-core";

interface I18n {
  locale: Locale;
  t: Translate;
}

const I18nContext = createContext<I18n>({ locale: SOURCE_LOCALE, t: (key, vars) => fill(key, vars) });

export function I18nProvider({
  catalogs,
  locale,
  children,
}: {
  catalogs: Catalogs;
  locale: Locale;
  children: ReactNode;
}) {
  const value = useMemo(() => ({ locale, t: createT(catalogs, locale) }), [catalogs, locale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useT(): Translate {
  return useContext(I18nContext).t;
}

export function useLocale(): Locale {
  return useContext(I18nContext).locale;
}
