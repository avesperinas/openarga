import type { Layer } from "./api";
import { t } from "./lang";

export function statusLine(layer: Pick<Layer, "subscription">, now: number): string {
  const state = layer.subscription;
  if (!state) return t("sub.waiting");
  if (state.paused) return t("sub.paused");
  if (state.failing) return state.detail ? t("sub.failing_detail", { detail: state.detail }) : t("sub.failing");
  if (!state.updated_at) return t("sub.waiting");
  const minutes = Math.max(0, Math.round((now - new Date(state.updated_at).getTime()) / 60_000));
  if (minutes < 1) return t("sub.now");
  if (minutes < 60) return t("sub.minutes", { minutes });
  const hours = Math.round(minutes / 60);
  if (hours < 48) return t("sub.hours", { hours });
  return t("sub.days", { days: Math.round(hours / 24) });
}
