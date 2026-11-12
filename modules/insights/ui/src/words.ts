import type { IconName } from "@openarga/ui";

import type { Figure, Insight, LastRun, Rating } from "./api";

export const RATINGS: { value: Rating; label: string }[] = [
  { value: "useful", label: "Útil" },
  { value: "known", label: "Ya lo sabía" },
  { value: "not_applicable", label: "No aplica" },
];

export const DOMAINS: Record<Insight["domain"], string> = {
  money: "Dinero",
  body: "Cuerpo",
  time: "Tiempo y metas",
  leisure: "Ocio y viajes",
  cross: "Cruzando",
};

export const DOMAIN_ICONS: Record<Insight["domain"], IconName> = {
  money: "wallet",
  body: "heart",
  time: "clock",
  leisure: "party",
  cross: "layers",
};

export const DOMAIN_HUES: Record<Insight["domain"], 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8> = {
  money: 3,
  body: 4,
  time: 1,
  leisure: 6,
  cross: 5,
};

const number = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });

export function amount(value: number, unit: string | null): string {
  const shown = number.format(value);
  return unit ? `${shown} ${unit}` : shown;
}

export function versus(figure: Figure): string {
  if (figure.baseline === 0) return `${amount(figure.baseline, figure.unit)}, ${figure.baseline_label}`;
  const change = Math.round(((figure.value - figure.baseline) / Math.abs(figure.baseline)) * 100);
  const sign = change > 0 ? "+" : change < 0 ? "−" : "±";
  return `${sign}${Math.abs(change)} % frente a ${amount(figure.baseline, figure.unit)}, ${figure.baseline_label}`;
}

export function changeOf(figure: Figure): string | null {
  if (figure.baseline === 0) return null;
  const change = Math.round(((figure.value - figure.baseline) / Math.abs(figure.baseline)) * 100);
  const sign = change > 0 ? "+" : change < 0 ? "−" : "±";
  return `${sign}${Math.abs(change)} %`;
}

export const against = (figure: Figure) => `frente a ${amount(figure.baseline, figure.unit)}, ${figure.baseline_label}`;

const day = new Intl.DateTimeFormat("es-ES", { weekday: "long", day: "numeric", month: "long" });

export function when(iso: string, now = new Date()): string {
  const date = new Date(iso);
  const days = Math.floor((startOf(now) - startOf(date)) / 86_400_000);
  if (days === 0) return "hoy";
  if (days === 1) return "ayer";
  return day.format(date);
}

const startOf = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();

export const paragraphs = (body: string) =>
  body
    .split(/\n\s*\n/)
    .map((one) => one.trim())
    .filter(Boolean);

const clock = new Intl.DateTimeFormat("es-ES", { hour: "2-digit", minute: "2-digit" });

export function at(iso: string, now = new Date()): string {
  return `${when(iso, now)} a las ${clock.format(new Date(iso))}`;
}

export function lastLook(runs: LastRun[], name: string, now = new Date()): string {
  const latest = [...runs].sort((a, b) => b.asked_at.localeCompare(a.asked_at))[0];
  if (!latest) return `${name} mira tus datos cada mañana desde las siete y el domingo te hace el resumen.`;
  const what = latest.kind === "weekly" ? "El resumen de la semana" : "La mirada de la mañana";
  const moment = at(latest.asked_at, now);
  switch (latest.state) {
    case "quiet":
      return `Miró ${moment}: nada nuevo que se saliera de lo tuyo, así que no hizo falta despertar a tu Claude.`;
    case "waiting":
      return `${what} está en marcha desde ${moment}: tu Claude mira tus datos.`;
    case "ok":
      return latest.ran_with
        ? `Miró ${moment} con tu cuenta «${latest.ran_with}», porque la de siempre no podía. Si nada pasaba el listón, se calló.`
        : `Miró ${moment} con tu Claude. Si nada pasaba el listón, se calló.`;
    case "refused":
      return latest.detail ?? `${what} no se pudo pedir ${moment}.`;
    case "rate_limited":
      return withFix(`${what} de ${moment} no salió: llegaste al límite de uso de tu Claude.`, latest.fix);
    default:
      return withFix(`${what} de ${moment} no salió${latest.detail ? `: ${latest.detail}` : "."}`, latest.fix);
  }
}

function withFix(said: string, fix?: string | null): string {
  return fix ? `${said} ${fix}` : said;
}
