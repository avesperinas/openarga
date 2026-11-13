import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

import { iconUrl } from "./asset-version";

export default defineConfig({
  esbuild: { jsx: "automatic" },
  define: { __MONEY_ICON__: JSON.stringify(iconUrl()) },
  test: {
    environment: "node",
    globals: true,
    setupFiles: [fileURLToPath(new URL("../../../packages/app/src/test-setup.ts", import.meta.url))],
  },
});
