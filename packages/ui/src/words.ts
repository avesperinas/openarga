import { createT, resolveLocale, type Catalogs, type Vars } from "./i18n";
import en from "./i18n/en.json";
import es from "./i18n/es.json";
import { locale } from "./regional";

export const PLATFORM_CATALOGS: Catalogs = { en, es };

export function say(key: string, vars?: Vars): string {
  return createT(PLATFORM_CATALOGS, resolveLocale(locale()))(key, vars);
}
