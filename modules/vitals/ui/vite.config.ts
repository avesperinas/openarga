import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import { VERSIONED, assetVersion, iconUrl } from "./asset-version";

export default defineConfig({
  base: "/vitals/",
  plugins: [
    react(),
    {
      name: "vitals-versioned-assets",
      transformIndexHtml: (html) =>
        VERSIONED.reduce(
          (page, file) => page.replaceAll(`/vitals/${file}"`, `/vitals/${file}?v=${assetVersion(file)}"`),
          html,
        ),
    },
  ],
  define: { __VITALS_ICON__: JSON.stringify(iconUrl()) },
  server: {
    port: 5179,
    proxy: {
      "/api/vitals": {
        target: "http://localhost:8032",
        rewrite: (path) => path.replace(/^\/api\/vitals/, ""),
      },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
