import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { appConfig } from "@openarga/app/vite";
import { type Plugin, type PluginOption, defineConfig } from "vite";

const dir = import.meta.dirname;

const precache: Plugin = {
  name: "travel-precache",
  apply: "build",
  generateBundle(_, bundle) {
    const files = (folder: string): string[] =>
      readdirSync(folder).flatMap((name) => {
        const path = join(folder, name);
        return statSync(path).isDirectory() ? files(path) : [path];
      });
    const fonts = files(join(dir, "public/map/fonts")).map(
      (path) => `/travel/${relative(join(dir, "public"), path).split("\\").join("/")}`,
    );
    const loose = readdirSync(join(dir, "public"))
      .filter((name) => statSync(join(dir, "public", name)).isFile())
      .map((name) => `/travel/${name}`);
    const built = [...Object.keys(bundle).map((name) => `/travel/${name}`), ...loose];
    const list = JSON.stringify(["/travel/", ...built, ...fonts]);
    this.emitFile({ type: "asset", fileName: "precache.json", source: list });
    const version = createHash("sha256").update(list).digest("hex").slice(0, 12);
    this.emitFile({
      type: "asset",
      fileName: "sw.js",
      source: readFileSync(join(dir, "sw.js"), "utf8").replace("__VERSION__", version),
    });
  },
};

const config = appConfig({ id: "travel", dir, port: 5181, apiPort: 8033 }, { worker: { format: "es" } });

const common = (plugin: PluginOption): boolean =>
  !(plugin && typeof plugin === "object" && "name" in plugin && plugin.name === "arga-app-sw");
config.plugins = [...(config.plugins ?? []).flat().filter(common), precache];

export default defineConfig(config);
