import type { Locale, Translate } from "@openarga/ui";

import type { CheckupChange } from "./api";
import { decimal } from "./words";

export function changeLine(change: CheckupChange, t: Translate, locale: Locale): string {
  const shown = (value: number) => decimal(value, locale, 2);
  const unit = change.unit ? ` ${change.unit}` : "";
  const range =
    change.out && !change.was_out
      ? `, ${t("range.now_out")}`
      : !change.out && change.was_out
        ? `, ${t("range.back_in")}`
        : change.out
          ? `, ${t("range.still_out")}`
          : "";
  return `${shown(change.previous)} → ${shown(change.value)}${unit}${range}`;
}
