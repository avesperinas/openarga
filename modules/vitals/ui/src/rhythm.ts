import type { Device, EcgTrace, Irn, Night } from "./api";

export function ecgSeries(trace: EcgTrace): { labels: string[]; series: { key: string; name: string; values: number[] }[] } {
  const step = trace.step_seconds ?? 0;
  return {
    labels: trace.millivolts.map((_, index) => `${(index * step).toLocaleString("es-ES", { maximumFractionDigits: 1 })} s`),
    series: [{ key: "mv", name: "Derivación I", values: trace.millivolts }],
  };
}

export function irnFoot(alert: Irn): string {
  if (alert.windows === 0) return "";
  return `${alert.positive_windows} de ${alert.windows} ventanas con ritmo irregular`;
}

const BATTERY: Record<NonNullable<Device["battery"]>, string> = {
  high: "batería alta",
  medium: "batería media",
  low: "batería baja",
  empty: "sin batería",
};

export function ago(moment: string, now: Date = new Date()): string {
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(moment).getTime()) / 60000));
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `hace ${hours} h`;
  return `hace ${Math.round(hours / 24)} días`;
}

export function bandFigure(device: Device, now: Date = new Date()): { value: string; foot: string; tone?: "warning" } {
  const value = device.battery_pct != null ? `${device.battery_pct} %` : device.battery ? BATTERY[device.battery] : "—";
  const foot = device.last_sync ? `sincronizó ${ago(device.last_sync, now)}` : "sin sincronizar";
  const stale = device.last_sync ? now.getTime() - new Date(device.last_sync).getTime() > 24 * 3600 * 1000 : true;
  const low = device.battery === "low" || device.battery === "empty" || (device.battery_pct ?? 100) <= 20;
  return low || stale ? { value, foot, tone: "warning" } : { value, foot };
}

export function wakeTiles(night: Night): { label: string; value: string }[] {
  const tiles: { label: string; value: string }[] = [];
  if (night.awakenings != null) tiles.push({ label: "Despertares", value: String(night.awakenings) });
  if (night.minutes_out_of_bed != null) tiles.push({ label: "Levantado", value: `${night.minutes_out_of_bed} min` });
  if (night.minutes_after_wake_up != null) {
    tiles.push({ label: "En la cama ya despierto", value: `${night.minutes_after_wake_up} min` });
  }
  return tiles;
}
