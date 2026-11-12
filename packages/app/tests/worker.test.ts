import { readFileSync } from "node:fs";

import { describe, expect, it, vi } from "vitest";

import { precacheOf } from "../src/vite";

const APP = { id: "library", root: "/library/", version: "abc", precache: [] };
const source = readFileSync(new URL("../sw.template.js", import.meta.url), "utf8").replace(
  "const APP = __APP__;",
  `const APP = ${JSON.stringify(APP)};`,
);
const self = { addEventListener: () => undefined };
type Worker = {
  pick: (url: URL, mode: string, origin: string) => string;
  page: (request: string) => Promise<unknown>;
  stale: (names: string[]) => { old: string[]; servedOld: boolean };
};
const load = (fetch: (request: string) => Promise<unknown>, kept: unknown = "guardada") =>
  new Function("self", "caches", "fetch", `${source}\nreturn { pick, page, stale };`)(
    self,
    {
      open: async () => ({
        match: async (url: string) => (url === APP.root ? kept : undefined),
      }),
    },
    fetch,
  ) as Worker;
const { pick, stale } = load(async () => undefined);

const ORIGIN = "https://arga.example";
const at = (path: string, mode = "cors") => pick(new URL(path, ORIGIN), mode, ORIGIN);

describe("el service worker de una app", () => {
  it("trata como página cualquier pantalla de la app", () => {
    expect(at("/library/", "navigate")).toBe("page");
    expect(at("/library/libro/1", "navigate")).toBe("page");
    expect(at("/library", "navigate")).toBe("page");
  });

  it("guarda los trozos y los ficheros de la app", () => {
    expect(at("/library/assets/index-a1.js")).toBe("asset");
    expect(at("/library/icon.svg?v=1")).toBe("file");
  });

  it("no toca la API, otras apps, el worker de los avisos ni otros orígenes", () => {
    expect(at("/api/library/books")).toBe("pass");
    expect(at("/shopping/", "navigate")).toBe("pass");
    expect(at("/sw.js")).toBe("pass");
    expect(at("/library/sw.js")).toBe("pass");
    expect(pick(new URL("https://otro.example/library/"), "navigate", ORIGIN)).toBe("pass");
  });
});

describe("la página", () => {
  const fresh = { status: 200, body: "de la red" };

  it("sale de la red, aunque haya una guardada: la guardada es la versión de la última visita", async () => {
    expect(await load(async () => fresh).page("/library/")).toBe(fresh);
  });

  it("sin red, o con el servidor caído, sale la guardada", async () => {
    expect(await load(async () => Promise.reject(new TypeError("offline"))).page("/library/")).toBe("guardada");
    expect(await load(async () => ({ status: 502 })).page("/library/")).toBe("guardada");
  });

  it("una redirección al login no se cambia por la guardada", async () => {
    const login = { status: 0, type: "opaqueredirect" };
    expect(await load(async () => login).page("/library/")).toBe(login);
  });

  it("si la red no contesta a tiempo, sale la guardada", async () => {
    vi.useFakeTimers();
    try {
      const opened = load(() => new Promise(() => undefined)).page("/library/");
      await vi.advanceTimersByTimeAsync(4000);
      expect(await opened).toBe("guardada");
    } finally {
      vi.useRealTimers();
    }
  });

  it("sin red y sin nada guardado, el error de la red", async () => {
    await expect(load(async () => Promise.reject(new TypeError("offline")), null).page("/library/")).rejects.toThrow(
      "offline",
    );
  });
});

describe("al activarse una versión nueva", () => {
  it("borra las cachés de las otras versiones de la app y no las de otras apps", () => {
    expect(stale(["library-app-2-old", "library-app-2-abc", "shopping-app-2-x"]).old).toEqual(["library-app-2-old"]);
  });

  it("recarga lo abierto solo si venía de un worker que abría la página guardada", () => {
    expect(stale(["library-app-2-old"]).servedOld).toBe(false);
    expect(stale(["library-app-1f2e3d4c5b6a"]).servedOld).toBe(true);
  });
});

describe("lo que se guarda al instalar", () => {
  it("la página, los trozos de arranque con sus estilos y los ficheros sueltos; no los perezosos", () => {
    const chunk = (fileName: string, imports: string[], css: string[] = [], isEntry = false) => ({
      type: "chunk" as const,
      fileName,
      isEntry,
      imports,
      code: "",
      viteMetadata: { importedCss: new Set(css) },
    });
    const bundle = {
      "assets/index.js": chunk("assets/index.js", ["assets/react.js"], ["assets/index.css"], true),
      "assets/react.js": chunk("assets/react.js", []),
      "assets/scanner.js": chunk("assets/scanner.js", []),
      "assets/index.css": {
        type: "asset" as const,
        fileName: "assets/index.css",
        source: "",
      },
      "assets/zxing.wasm": {
        type: "asset" as const,
        fileName: "assets/zxing.wasm",
        source: "",
      },
    };
    expect(precacheOf("library", bundle as never, ["icon.svg"])).toEqual([
      "/library/",
      "/library/assets/index.css",
      "/library/assets/index.js",
      "/library/assets/react.js",
      "/library/icon.svg",
    ]);
  });
});
