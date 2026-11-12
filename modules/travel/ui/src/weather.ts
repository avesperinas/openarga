import type { ClimateMonth, ForecastDay } from "./api";

export function sky(code: number | null): string {
  if (code === null) return "";
  if (code <= 1) return "☀️";
  if (code === 2) return "⛅";
  if (code === 3) return "☁️";
  if (code === 45 || code === 48) return "🌫️";
  if (code >= 71 && code <= 77) return "❄️";
  if (code === 85 || code === 86) return "❄️";
  if (code >= 95) return "⛈️";
  return "🌧️";
}

export function dayLine(day: ForecastDay): string {
  const temps = day.max_c !== null && day.min_c !== null ? `${Math.round(day.max_c)}° / ${Math.round(day.min_c)}°` : "";
  const rain = day.rain_chance !== null && day.rain_chance >= 30 ? ` · ${day.rain_chance} % lluvia` : "";
  return `${sky(day.code)} ${temps}${rain}`.trim();
}

export function goodMonths(months: ClimateMonth[]): number[] {
  return months.filter((one) => one.max_c >= 15 && one.max_c <= 29 && one.rain_days <= 10).map((one) => one.month);
}
