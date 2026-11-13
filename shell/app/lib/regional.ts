import { request } from "./session";

export interface PersonPreferences {
  locale: "en" | "es";
  timezone: string;
  currency: string;
  country: string | null;
  region: string | null;
  area: string | null;
}

export const HEADERS: Record<keyof PersonPreferences, string> = {
  locale: "x-arga-locale",
  timezone: "x-arga-timezone",
  currency: "x-arga-currency",
  country: "x-arga-country",
  region: "x-arga-region",
  area: "x-arga-area",
};

export function instanceDefaults(env: Record<string, string | undefined> = process.env): PersonPreferences {
  return {
    locale: env.OPENARGA_LOCALE === "es" ? "es" : "en",
    timezone: env.OPENARGA_TIMEZONE || "UTC",
    currency: env.OPENARGA_CURRENCY || "EUR",
    country: env.OPENARGA_COUNTRY || null,
    region: env.OPENARGA_REGION || null,
    area: env.OPENARGA_AREA || null,
  };
}

export function fromHeaders(incoming: Pick<Headers, "get">, base = instanceDefaults()): PersonPreferences {
  const found = { ...base };
  for (const key of Object.keys(HEADERS) as (keyof PersonPreferences)[]) {
    const value = incoming.get(HEADERS[key]);
    if (!value) continue;
    if (key === "locale") found.locale = value === "es" ? "es" : "en";
    else found[key] = value;
  }
  return found;
}

const URL_ = "/api/kernel/me/preferences";

export class PreferencesError extends Error {}

export async function readPersonPreferences(): Promise<PersonPreferences> {
  const response = await request(URL_, { headers: { accept: "application/json" } });
  if (!response.ok) throw new PreferencesError(String(response.status));
  return (await response.json()) as PersonPreferences;
}

export async function changePersonPreferences(change: Partial<PersonPreferences>): Promise<PersonPreferences> {
  const response = await request(URL_, {
    method: "PATCH",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify(change),
  });
  if (!response.ok) throw new PreferencesError(String(response.status));
  return (await response.json()) as PersonPreferences;
}

function supported(kind: "timeZone" | "currency"): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  try {
    return intl.supportedValuesOf?.(kind) ?? [];
  } catch {
    return [];
  }
}

export function timeZones(current: string): string[] {
  const found = supported("timeZone");
  return found.includes(current) ? found : [current, ...found];
}

export function currencies(current: string): string[] {
  const found = supported("currency");
  return found.includes(current) ? found : [current, ...found];
}

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const NOT_COUNTRIES = new Set(["EU", "EZ", "QO", "UN", "XA", "XB", "ZZ"]);

export function countries(locale: string): { code: string; name: string }[] {
  let names: Intl.DisplayNames;
  try {
    names = new Intl.DisplayNames([locale], { type: "region", fallback: "none" });
  } catch {
    return [];
  }
  const found: { code: string; name: string }[] = [];
  for (const first of LETTERS)
    for (const second of LETTERS) {
      const code = first + second;
      const name = names.of(code);
      if (name && name !== code && !NOT_COUNTRIES.has(code)) found.push({ code, name });
    }
  return found.sort((a, b) => a.name.localeCompare(b.name, locale));
}

export const REGION = /^[A-Z]{2}-[A-Z0-9]{1,3}$/;
export const AREA = /^[a-z0-9][a-z0-9-]{0,63}$/;
