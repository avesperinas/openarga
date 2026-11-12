import type { Layer } from "./api";

export function statusLine(layer: Pick<Layer, "subscription">, now: number): string {
  const state = layer.subscription;
  if (!state) return "Esperando la primera pasada";
  if (state.paused) return "En pausa en Hub";
  if (state.failing) return state.detail ? `Falla: ${state.detail}` : "Falla";
  if (!state.updated_at) return "Esperando la primera pasada";
  const minutes = Math.max(0, Math.round((now - new Date(state.updated_at).getTime()) / 60_000));
  if (minutes < 1) return "Actualizada ahora";
  if (minutes < 60) return `Actualizada hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `Actualizada hace ${hours} h`;
  return `Actualizada hace ${Math.round(hours / 24)} días`;
}
