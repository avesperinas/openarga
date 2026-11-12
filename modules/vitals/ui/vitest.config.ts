import { defineConfig } from "vitest/config";

import { iconUrl } from "./asset-version";

export default defineConfig({
  esbuild: { jsx: "automatic" },
  define: { __VITALS_ICON__: JSON.stringify(iconUrl()) },
  test: { environment: "node", globals: true },
});
