import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import { VERSIONED, assetVersion, iconUrl } from "./asset-version";

export default defineConfig({
  base: "/money/",
  plugins: [
    react(),
    {
      name: "money-versioned-assets",
      transformIndexHtml: (html) =>
        VERSIONED.reduce(
          (page, file) => page.replaceAll(`/money/${file}"`, `/money/${file}?v=${assetVersion(file)}"`),
          html,
        ),
    },
  ],
  define: { __MONEY_ICON__: JSON.stringify(iconUrl()) },
  server: {
    port: 5176,
    proxy: {
      "/api/money": {
        target: "http://localhost:8040",
        rewrite: (path) => path.replace(/^\/api\/money/, ""),
      },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
