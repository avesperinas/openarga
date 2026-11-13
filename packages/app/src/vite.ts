import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { type Plugin, type Rollup, type UserConfig, mergeConfig } from "vite";

type OutputBundle = Rollup.OutputBundle;

export const VERSIONED = ["icon.svg", "apple-touch-icon.png", "manifest.webmanifest"];

export interface AppOptions {
  id: string;
  dir: string;
  port: number;
  apiPort: number;
  api?: string;
}

export function assetVersion(dir: string, file: string): string {
  const body = readFileSync(join(dir, "public", file));
  return createHash("sha256").update(body).digest("hex").slice(0, 10);
}

export function iconDefine(id: string, dir: string): Record<string, string> {
  return { [`__${id.toUpperCase()}_ICON__`]: JSON.stringify(`/${id}/icon.svg?v=${assetVersion(dir, "icon.svg")}`) };
}

export function precacheOf(id: string, bundle: OutputBundle, loose: string[]): string[] {
  const initial = new Set<string>();
  const visit = (name: string) => {
    const chunk = bundle[name];
    if (!chunk || chunk.type !== "chunk" || initial.has(name)) return;
    initial.add(name);
    const css = (chunk as { viteMetadata?: { importedCss?: Set<string> } }).viteMetadata?.importedCss;
    for (const sheet of css ?? []) initial.add(sheet);
    for (const imported of chunk.imports) visit(imported);
  };
  for (const [name, chunk] of Object.entries(bundle)) if (chunk.type === "chunk" && chunk.isEntry) visit(name);
  return [`/${id}/`, ...[...initial].sort().map((name) => `/${id}/${name}`), ...loose.map((name) => `/${id}/${name}`)];
}

function serviceWorker({ id, dir }: AppOptions): Plugin {
  const template = readFileSync(new URL("../sw.template.js", import.meta.url), "utf8");
  return {
    name: "arga-app-sw",
    apply: "build",
    generateBundle: {
      order: "post",
      handler(_, bundle) {
        const loose = VERSIONED.filter((file) => existsSync(join(dir, "public", file)));
        const list = precacheOf(id, bundle, loose);
        const hash = createHash("sha256");
        for (const url of list) {
          const name = url.slice(id.length + 2) || "index.html";
          const out = bundle[name];
          if (out) hash.update(out.type === "chunk" ? out.code : out.source);
          else if (existsSync(join(dir, "public", name))) hash.update(readFileSync(join(dir, "public", name)));
        }
        const app = { id, root: `/${id}/`, version: hash.digest("hex").slice(0, 12), precache: list };
        this.emitFile({ type: "asset", fileName: "sw.js", source: template.replace("const APP = __APP__;", `const APP = ${JSON.stringify(app)};`) });
      },
    },
  };
}

function versionedAssets({ id, dir }: AppOptions): Plugin {
  return {
    name: "arga-app-versioned-assets",
    transformIndexHtml: (html) =>
      VERSIONED.filter((file) => existsSync(join(dir, "public", file))).reduce(
        (page, file) => page.replaceAll(`/${id}/${file}"`, `/${id}/${file}?v=${assetVersion(dir, file)}"`),
        html,
      ),
  };
}

export function appConfig(options: AppOptions, extra: UserConfig = {}): UserConfig {
  const { id, dir, port, apiPort, api = id } = options;
  return mergeConfig(
    {
      base: `/${id}/`,
      plugins: [react(), versionedAssets(options), serviceWorker(options)],
      define: iconDefine(id, dir),
      server: {
        port,
        proxy: {
          [`/api/${api}`]: {
            target: `http://localhost:${apiPort}`,
            rewrite: (path: string) => path.replace(new RegExp(`^/api/${api}`), ""),
          },
        },
      },
      build: { outDir: "dist", emptyOutDir: true },
    } satisfies UserConfig,
    extra,
  );
}

export function appTestConfig({ id, dir }: Pick<AppOptions, "id" | "dir">) {
  return {
    esbuild: { jsx: "automatic" as const },
    define: iconDefine(id, dir),
    test: {
      environment: "node" as const,
      globals: true,
      setupFiles: [fileURLToPath(new URL("./test-setup.ts", import.meta.url))],
    },
  };
}
