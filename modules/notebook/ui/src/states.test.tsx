// @vitest-environment jsdom
import { reset } from "@openarga/app";
import { ToastHost } from "@openarga/ui";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const NOTE = "0a0a0a0a-0000-4000-8000-00000000a0a0";
const NOW = "2026-10-29T10:00:00Z";
const SUMMARY = { id: NOTE, folder: "Proyectos", title: "Huerto", path: "Proyectos/Huerto", updated_at: NOW, updated_by: "app" };
const FULL = {
  ...SUMMARY,
  content: "# Huerto\n\nTomates y albahaca.\n",
  properties: {},
  tags: [],
  outline: [{ level: 1, text: "Huerto", line: 0 }],
  version: 1,
  created_at: NOW,
  arga: null,
};

type Reply = () => unknown;

let root: Root;
let host: HTMLElement;
let replies: Record<string, Reply>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  window.scrollTo = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }) as never;
});

beforeEach(() => {
  void reset();
  replies = {
    "GET /api/notebook/tree": () => ({ folders: [], notes: [] }),
    "GET /api/notebook/tags": () => [],
    "GET /api/notebook/linkables": () => [],
    "GET /api/notebook/review": () => ({ chosen: false, notes: [] }),
    "GET /api/notebook/trash": () => [],
    "GET /api/notebook/graph": () => ({ nodes: [], edges: [] }),
    "GET /api/notebook/settings": () => ({ daily_folder: "Diario", review_property: null }),
    "GET /api/notebook/properties": () => [],
    "GET /api/notebook/export": () => ({ pushed_at: null, tried_at: null, outcome: "unconnected", detail: null, commit_url: null, pending: 0 }),
    "GET /api/notebook/search": () => [],
    "GET /api/notebook/version": () => ({ version: "1.0.0" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const reply = replies[`${method} ${url}`] ?? replies[`${method} ${url.split("?")[0]}`];
      if (!reply) return json({ detail: "no existe: eso" }, 404);
      const body = await reply();
      return body instanceof Response ? body : json(body);
    }),
  );
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const button = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((one) => one.textContent?.includes(name));

async function open(path = "/notebook/") {
  window.history.replaceState(null, "", path);
  act(() =>
    root.render(
      <ToastHost>
        <App />
      </ToastHost>,
    ),
  );
  await settle();
}

async function serious(): Promise<string[]> {
  const result = await axe.run(host, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((one) => one.impact === "serious" || one.impact === "critical")
    .map((one) => `${one.id}: ${one.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

describe("las notas", () => {
  it("mientras llega el árbol, el esqueleto, y nada de «Cargando…»", async () => {
    replies["GET /api/notebook/tree"] = () => new Promise(() => undefined);
    await open("/notebook/notas");
    expect(host.querySelector(".skeleton")).not.toBeNull();
    expect(host.textContent).not.toContain("Cargando");
  });

  it("sin notas, el botón crea la primera", async () => {
    await open("/notebook/notas");
    expect(host.textContent).toContain("Aún no hay notas");
    expect(button("Nota nueva")).toBeDefined();
  });

  it("si falla, lo dice y reintentar lo trae", async () => {
    replies["GET /api/notebook/tree"] = () => json({ detail: "la base no contesta" }, 503);
    await open("/notebook/notas");
    expect(host.textContent).toContain("Notebook no contesta");
    expect(host.textContent).toContain("la base no contesta");

    replies["GET /api/notebook/tree"] = () => ({ folders: ["Proyectos"], notes: [SUMMARY] });
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Proyectos");
  });

  it("sin red, lo dice arriba", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open("/notebook/notas");
    expect(host.textContent).toContain("Sin conexión");
  });
});

describe("una nota", () => {
  it("se lee sin esperar al editor", async () => {
    replies["GET /api/notebook/tree"] = () => ({ folders: ["Proyectos"], notes: [SUMMARY] });
    replies[`GET /api/notebook/notes/${NOTE}`] = () => FULL;
    replies[`GET /api/notebook/notes/${NOTE}/links`] = () => ({ links: [], backlinks: [] });
    await open(`/notebook/nota/${NOTE}`);
    expect(host.textContent).toContain("Tomates y albahaca.");
    expect(button("Editar")).toBeDefined();
  });

  it("si no existe lo dice; otro fallo se reintenta", async () => {
    await open(`/notebook/nota/${NOTE}`);
    expect(host.textContent).toContain("Esta nota ya no está");
    expect(button("Reintentar")).toBeUndefined();

    act(() => root.unmount());
    root = createRoot(host);
    void reset();
    replies[`GET /api/notebook/notes/${NOTE}`] = () => json({ detail: "la base no contesta" }, 503);
    await open(`/notebook/nota/${NOTE}`);
    expect(host.textContent).toContain("la base no contesta");
    expect(button("Reintentar")).toBeDefined();
  });
});

describe("las demás pantallas", () => {
  it("repasar, sin propiedad elegida, lleva a elegirla", async () => {
    await open("/notebook/repasar");
    expect(button("Elegirla")).toBeDefined();
  });

  it("la papelera vacía vuelve a las notas", async () => {
    await open("/notebook/papelera");
    expect(host.textContent).toContain("La papelera está vacía");
    expect(button("Volver a las notas")).toBeDefined();
  });

  it("al abrir Notebook sale el grafo, en su pestaña", async () => {
    await open("/notebook/");
    expect(host.textContent).toContain("Aún no hay nada que enlazar");
    expect(host.querySelector('[aria-current="page"]')?.textContent).toContain("Grafo");
  });

  it("el grafo sin enlaces ofrece una nota nueva", async () => {
    await open("/notebook/grafo");
    expect(host.textContent).toContain("Aún no hay nada que enlazar");
    expect(button("Nota nueva")).toBeDefined();
  });

  it("buscar sin nada que lo case ofrece borrar la búsqueda", async () => {
    await open("/notebook/buscar?q=nada");
    expect(host.textContent).toContain("Nada con eso");
    expect(button("Borrar la búsqueda")).toBeDefined();
  });

  it("los ajustes son los comunes, con los de Notebook arriba", async () => {
    await open("/notebook/ajustes");
    expect(host.textContent).toContain("Nota del día");
    expect(host.textContent).toContain("Copia en GitHub");
  });
});

describe("axe-core sin errores graves", () => {
  it.each(["/notebook/", "/notebook/notas", "/notebook/buscar?q=nada", "/notebook/repasar", "/notebook/papelera", "/notebook/grafo", "/notebook/ajustes"])(
    "%s",
    async (path) => {
      await open(path);
      expect(await serious()).toEqual([]);
    },
  );

  it("una nota", async () => {
    replies["GET /api/notebook/tree"] = () => ({ folders: ["Proyectos"], notes: [SUMMARY] });
    replies[`GET /api/notebook/notes/${NOTE}`] = () => FULL;
    replies[`GET /api/notebook/notes/${NOTE}/links`] = () => ({ links: [], backlinks: [] });
    await open(`/notebook/nota/${NOTE}`);
    expect(await serious()).toEqual([]);
  });
});
