import { readFileSync } from "node:fs";

import { appConfig } from "@openarga/app/vite";
import { defineConfig } from "vite";

import { mapVersion } from "./map-version";

const MAP = mapVersion(import.meta.dirname);

export default defineConfig(
  appConfig(
    { id: "outings", dir: import.meta.dirname, port: 5193, apiPort: 8052 },
    {
      plugins: [
        {
          name: "outings-geo-and-map",
          configureServer(server) {
            server.middlewares.use((request, response, next) => {
              if ((request.url ?? "").split("?")[0] === "/outings/geo/countries.json") {
                response.setHeader("content-type", "application/json");
                response.end(readFileSync(new URL("../../../packages/ui/geo/countries.json", import.meta.url)));
                return;
              }
              request.url = request.url?.replace(/^\/outings\/map\/v-(?:[0-9a-f]+)\//, "/outings/map/");
              next();
            });
          },
        },
        {
          name: "outings-map-version",
          apply: "build",
          generateBundle() {
            this.emitFile({ type: "asset", fileName: "map/VERSION", source: `${MAP}\n` });
          },
        },
      ],
      define: { __OUTINGS_MAP__: JSON.stringify(MAP) },
      worker: { format: "es" },
    },
  ),
);
