import type { IconName } from "@openarga/ui";

import type { Figure, Insight, LastRun, Rating } from "./api";
import { intl, t } from "./lang";

export const RATINGS: { value: Rating; label: string }[] = [
  { value: "useful", get label() { return t("rating.useful"); } },
  { value: "known", get label() { return t("rating.known"); } },
  { value: "not_applicable", get label() { return t("rating.not_applicable"); } },
];

export const DOMAINS: Record<Insight["domain"], string> = {
  get money() { return t("domain.money"); },
  get body() { return t("domain.body"); },
  get time() { return t("domain.time"); },
  get leisure() { return t("domain.leisure"); },
  get cross() { return t("domain.cross"); },
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

export function amount(value: number, unit: string | null): string {
  const shown = new Intl.NumberFormat(intl(), { maximumFractionDigits: 1 }).format(value);
  return unit ? `${shown} ${unit}` : shown;
}

export function versus(figure: Figure): string {
  if (figure.baseline === 0) return `${amount(figure.baseline, figure.unit)}, ${figure.baseline_label}`;
  const change = Math.round(((figure.value - figure.baseline) / Math.abs(figure.baseline)) * 100);
  const sign = change > 0 ? "+" : change < 0 ? "−" : "±";
  return t("figure.versus", { change: `${sign}${Math.abs(change)} %`, baseline: amount(figure.baseline, figure.unit), label: figure.baseline_label });
}

export function changeOf(figure: Figure): string | null {
  if (figure.baseline === 0) return null;
  const change = Math.round(((figure.value - figure.baseline) / Math.abs(figure.baseline)) * 100);
  const sign = change > 0 ? "+" : change < 0 ? "−" : "±";
  return `${sign}${Math.abs(change)} %`;
}

export const against = (figure: Figure) => t("figure.against", { baseline: amount(figure.baseline, figure.unit), label: figure.baseline_label });


export function when(iso: string, now = new Date()): string {
  const date = new Date(iso);
  const days = Math.floor((startOf(now) - startOf(date)) / 86_400_000);
  if (days === 0) return t("when.today");
  if (days === 1) return t("when.yesterday");
  return new Intl.DateTimeFormat(intl(), { weekday: "long", day: "numeric", month: "long" }).format(date);
}

const startOf = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();

export const paragraphs = (body: string) =>
  body
    .split(/\n\s*\n/)
    .map((one) => one.trim())
    .filter(Boolean);


export function at(iso: string, now = new Date()): string {
  return t("when.at", { day: when(iso, now), time: new Intl.DateTimeFormat(intl(), { hour: "2-digit", minute: "2-digit" }).format(new Date(iso)) });
}

export function lastLook(runs: LastRun[], name: string, now = new Date()): string {
  const latest = [...runs].sort((a, b) => b.asked_at.localeCompare(a.asked_at))[0];
  if (!latest) return t("look.never", { name });
  const what = latest.kind === "weekly" ? t("look.weekly") : t("look.morning");
  const moment = at(latest.asked_at, now);
  switch (latest.state) {
    case "quiet":
      return t("look.quiet", { moment });
    case "waiting":
      return t("look.waiting", { what, moment });
    case "ok":
      return latest.ran_with ? t("look.ok_with", { moment, with: latest.ran_with }) : t("look.ok", { moment });
    case "refused":
      return latest.detail ?? t("look.refused", { what, moment });
    case "rate_limited":
      return withFix(t("look.rate_limited", { what, moment }), latest.fix);
    default:
      return withFix(latest.detail ? t("look.failed_because", { what, moment, detail: latest.detail }) : t("look.failed", { what, moment }), latest.fix);
  }
}

function withFix(said: string, fix?: string | null): string {
  return fix ? `${said} ${fix}` : said;
}
