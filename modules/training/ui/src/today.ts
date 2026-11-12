import type { Locale } from "@openarga/ui";

export function todayLabel(date: Date, locale: Locale): string {
  const text = new Intl.DateTimeFormat(locale, {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(date);
  return text.charAt(0).toUpperCase() + text.slice(1);
}
