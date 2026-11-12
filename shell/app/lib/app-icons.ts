import { type IconStyle, styledIcon } from "@openarga/ui";

import type { ModuleSummary } from "./kernel";

export const appIconOf = (module: Pick<ModuleSummary, "view" | "updated_at">): string | undefined =>
  module.view ? `${module.view}/icon.svg?v=${Date.parse(module.updated_at)}` : undefined;

export const appIcons = (modules: ModuleSummary[], style?: IconStyle): Record<string, string> =>
  Object.fromEntries(
    modules.flatMap((module) => {
      const icon = appIconOf(module);
      return icon ? [[module.id, styledIcon(icon, style)]] : [];
    }),
  );
