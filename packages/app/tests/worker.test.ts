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

describe("an app's service worker", () => {
  it("treats any screen of the app as a page", () => {
    expect(at("/library/", "navigate")).toBe("page");
    expect(at("/library/libro/1", "navigate")).toBe("page");
    expect(at("/library", "navigate")).toBe("page");
  });

  it("caches the app's chunks and files", () => {
    expect(at("/library/assets/index-a1.js")).toBe("asset");
    expect(at("/library/icon.svg?v=1")).toBe("file");
  });

  it("does not touch the API, other apps, the notifications worker or other origins", () => {
    expect(at("/api/library/books")).toBe("pass");
    expect(at("/shopping/", "navigate")).toBe("pass");
    expect(at("/sw.js")).toBe("pass");
    expect(at("/library/sw.js")).toBe("pass");
    expect(pick(new URL("https://otro.example/library/"), "navigate", ORIGIN)).toBe("pass");
  });
});

describe("the page", () => {
  const fresh = { status: 200, body: "de la red" };

  it("comes from the network even if one is cached: the cached one is the last visit's version", async () => {
    expect(await load(async () => fresh).page("/library/")).toBe(fresh);
  });

  it("offline, or with the server down, the cached one is served", async () => {
    expect(await load(async () => Promise.reject(new TypeError("offline"))).page("/library/")).toBe("guardada");
    expect(await load(async () => ({ status: 502 })).page("/library/")).toBe("guardada");
  });

  it("a redirect to the login is not swapped for the cached one", async () => {
    const login = { status: 0, type: "opaqueredirect" };
    expect(await load(async () => login).page("/library/")).toBe(login);
  });

  it("if the network does not answer in time, the cached one is served", async () => {
    vi.useFakeTimers();
    try {
      const opened = load(() => new Promise(() => undefined)).page("/library/");
      await vi.advanceTimersByTimeAsync(4000);
      expect(await opened).toBe("guardada");
    } finally {
      vi.useRealTimers();
    }
  });

  it("offline and with nothing cached, the network error", async () => {
    await expect(load(async () => Promise.reject(new TypeError("offline")), null).page("/library/")).rejects.toThrow(
      "offline",
    );
  });
});

describe("when a new version activates", () => {
  it("deletes the caches of the app's other versions and not those of other apps", () => {
    expect(stale(["library-app-2-old", "library-app-2-abc", "shopping-app-2-x"]).old).toEqual(["library-app-2-old"]);
  });

  it("reloads open tabs only if they came from a worker that served the cached page", () => {
    expect(stale(["library-app-2-old"]).servedOld).toBe(false);
    expect(stale(["library-app-1f2e3d4c5b6a"]).servedOld).toBe(true);
  });
});

describe("what is cached on install", () => {
  it("the page, the startup chunks with their styles and the loose files; not the lazy ones", () => {
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
