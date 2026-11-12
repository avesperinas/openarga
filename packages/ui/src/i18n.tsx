import { createContext, useContext, useMemo, type ReactNode } from "react";

export type Locale = "en" | "es";

export const LOCALES: readonly Locale[] = ["en", "es"];

export const SOURCE_LOCALE: Locale = "en";

export type Catalog = Record<string, string>;

export type Catalogs = { en: Catalog } & Partial<Record<Locale, Catalog>>;

export type Vars = Record<string, string | number>;

export type Translate = (key: string, vars?: Vars) => string;

function fill(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (name in vars ? String(vars[name]) : match));
}

export function createT(catalogs: Catalogs, locale: Locale): Translate {
  const wanted = catalogs[locale] ?? {};
  const source = catalogs.en;
  return (key, vars) => fill(wanted[key] ?? source[key] ?? key, vars);
}

export function resolveLocale(preferred?: string | null): Locale {
  const candidates = [preferred, typeof navigator === "undefined" ? undefined : navigator.language];
  for (const candidate of candidates) {
    const base = candidate?.toLowerCase().split(/[-_]/)[0];
    if (base && (LOCALES as readonly string[]).includes(base)) return base as Locale;
  }
  return SOURCE_LOCALE;
}

export function missingKeys(catalogs: Catalogs): { locale: Locale; key: string }[] {
  const keys = new Set(LOCALES.flatMap((locale) => Object.keys(catalogs[locale] ?? {})));
  const missing: { locale: Locale; key: string }[] = [];
  for (const locale of LOCALES) {
    const catalog = catalogs[locale] ?? {};
    for (const key of keys) if (!(key in catalog)) missing.push({ locale, key });
  }
  return missing;
}

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
