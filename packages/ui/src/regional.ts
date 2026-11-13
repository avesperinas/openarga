export interface Regional {
  locale: string;
  timeZone: string;
  currency: string;
}

export interface RegionalPreferences {
  locale: string;
  timezone: string;
  currency: string;
  country?: string | null;
}

function browserZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function browserLocale(): string {
  return (typeof navigator !== "undefined" && navigator.language) || "en";
}

// TODO: remove once every app's tests load @openarga/app's test setup (issue for Apps-1).
const TEST_INSTANCE: Regional = { locale: "es-ES", timeZone: "Europe/Madrid", currency: "EUR" };
const underTest = Boolean((globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env?.VITEST);

let current: Regional = underTest ? TEST_INSTANCE : { locale: browserLocale(), timeZone: browserZone(), currency: "EUR" };
const listeners = new Set<() => void>();

export function intlLocale(language: string, country?: string | null): string {
  const tag = country ? `${language}-${country}` : language;
  try {
    return Intl.getCanonicalLocales(tag)[0] ?? language;
  } catch {
    return language;
  }
}

function validZone(zone: string): boolean {
  try {
    new Intl.DateTimeFormat("en", { timeZone: zone });
    return true;
  } catch {
    return false;
  }
}

export function configureRegional(next: Partial<Regional>): void {
  const merged = { ...current, ...next };
  if (!validZone(merged.timeZone)) merged.timeZone = current.timeZone;
  if (!/^[A-Z]{3}$/.test(merged.currency)) merged.currency = current.currency;
  merged.locale = intlLocale(merged.locale);
  if (merged.locale === current.locale && merged.timeZone === current.timeZone && merged.currency === current.currency) return;
  current = merged;
  numberCache.clear();
  dateCache.clear();
  for (const listener of listeners) listener();
}

export function regionalFrom(preferences: RegionalPreferences): Regional {
  return {
    locale: intlLocale(preferences.locale, preferences.country),
    timeZone: preferences.timezone,
    currency: preferences.currency,
  };
}

export function onRegionalChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export const regional = (): Regional => current;
export const locale = (): string => current.locale;
export const timeZone = (): string => current.timeZone;
export const currency = (): string => current.currency;

const numberCache = new Map<string, Intl.NumberFormat>();
const dateCache = new Map<string, Intl.DateTimeFormat>();

export function numbers(options: Intl.NumberFormatOptions = {}): Intl.NumberFormat {
  const key = JSON.stringify(options);
  let found = numberCache.get(key);
  if (!found) {
    found = new Intl.NumberFormat(current.locale, options);
    numberCache.set(key, found);
  }
  return found;
}

/** Without `timeZone` in the options, dates are shown in the device's zone, as `Date` computes them. */
export function dates(options: Intl.DateTimeFormatOptions = {}): Intl.DateTimeFormat {
  const key = JSON.stringify(options);
  let found = dateCache.get(key);
  if (!found) {
    found = new Intl.DateTimeFormat(current.locale, options);
    dateCache.set(key, found);
  }
  return found;
}

export function zonedDates(options: Intl.DateTimeFormatOptions = {}): Intl.DateTimeFormat {
  return dates({ ...options, timeZone: current.timeZone });
}
