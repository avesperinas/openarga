import { type Catalogs, type Locale, type Translate, createT } from "@openarga/ui";

import en from "./i18n/en.json";
import es from "./i18n/es.json";

export const CATALOGS: Catalogs = { en, es };

let locale: Locale = "en";
let translate = createT(CATALOGS, locale);

export function setLocale(next: Locale): void {
  locale = next;
  translate = createT(CATALOGS, next);
}

export const currentLocale = (): Locale => locale;

export const t: Translate = (key, vars) => translate(key, vars);

export const intl = (): string => (locale === "es" ? "es-ES" : "en-GB");
