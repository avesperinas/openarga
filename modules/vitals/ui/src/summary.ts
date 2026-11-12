import type { CheckupChange } from "./api";

export function changeLine(change: CheckupChange): string {
  const shown = (value: number) => value.toLocaleString("es-ES", { maximumFractionDigits: 2 });
  const unit = change.unit ? ` ${change.unit}` : "";
  const range =
    change.out && !change.was_out
      ? ", ahora fuera de rango"
      : !change.out && change.was_out
        ? ", vuelve al rango"
        : change.out
          ? ", sigue fuera de rango"
          : "";
  return `${shown(change.previous)} → ${shown(change.value)}${unit}${range}`;
}
