import type { Locale, Translate } from "@openarga/ui";

import type { Device, EcgTrace, Irn, Night } from "./api";
import { decimal } from "./words";

export function ecgSeries(
  trace: EcgTrace,
  t: Translate,
  locale: Locale,
): { labels: string[]; series: { key: string; name: string; values: number[] }[] } {
  const step = trace.step_seconds ?? 0;
  return {
    labels: trace.millivolts.map((_, index) => `${decimal(index * step, locale, 1)} s`),
    series: [{ key: "mv", name: t("ecg.lead"), values: trace.millivolts }],
  };
}

export function irnFoot(alert: Irn, t: Translate): string {
  if (alert.windows === 0) return "";
  return t("irn.windows", { positive: alert.positive_windows, windows: alert.windows });
}

export function ago(moment: string, t: Translate, now: Date = new Date()): string {
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(moment).getTime()) / 60000));
  if (minutes < 60) return t("ago.minutes", { count: minutes });
  const hours = Math.round(minutes / 60);
  if (hours < 48) return t("ago.hours", { count: hours });
  return t("ago.days", { count: Math.round(hours / 24) });
}

export function bandFigure(
  device: Device,
  t: Translate,
  now: Date = new Date(),
): { value: string; foot: string; tone?: "warning" } {
  const value = device.battery_pct != null ? `${device.battery_pct} %` : device.battery ? t(`battery.${device.battery}`) : "—";
  const foot = device.last_sync ? t("band.synced", { ago: ago(device.last_sync, t, now) }) : t("band.not_synced");
  const stale = device.last_sync ? now.getTime() - new Date(device.last_sync).getTime() > 24 * 3600 * 1000 : true;
  const low = device.battery === "low" || device.battery === "empty" || (device.battery_pct ?? 100) <= 20;
  return low || stale ? { value, foot, tone: "warning" } : { value, foot };
}

export function wakeTiles(night: Night, t: Translate): { label: string; value: string }[] {
  const tiles: { label: string; value: string }[] = [];
  if (night.awakenings != null) tiles.push({ label: t("wake.awakenings"), value: String(night.awakenings) });
  if (night.minutes_out_of_bed != null) tiles.push({ label: t("wake.out_of_bed"), value: `${night.minutes_out_of_bed} min` });
  if (night.minutes_after_wake_up != null) {
    tiles.push({ label: t("wake.in_bed_awake"), value: `${night.minutes_after_wake_up} min` });
  }
  return tiles;
}
