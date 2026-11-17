import { createT, regional, resolveLocale, type Catalogs, type Vars } from "@openarga/ui";

import en from "./i18n/en.json";
import es from "./i18n/es.json";

export const CATALOGS: Catalogs = { en, es };

export function say(key: string, vars?: Vars): string {
  return createT(CATALOGS, resolveLocale(regional().locale))(key, vars);
}
