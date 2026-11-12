// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { type Category, type ShoppingList, queue } from "./api";
import { App } from "./App";

const DAIRY: Category = { id: "dairy", name: "Lácteos", emoji: "🥛", position: 3 };
const BAKERY: Category = { id: "bakery", name: "Panadería", emoji: "🥖", position: 2 };

const LIST: ShoppingList = {
  groups: [
    {
      category_id: "dairy",
      name: "Lácteos",
      emoji: "🥛",
      items: [
        {
          id: "00000000-0000-4000-8000-0000000000a1",
          product_id: "00000000-0000-4000-8000-0000000000b1",
          name: "Leche",
          category_id: "dairy",
          quantity: "2",
          note: null,
          in_cart: false,
          source: "app",
        },
      ],
    },
  ],
  cart: [],
  due: [],
  usual: [],
  pending: 1,
  in_cart: 0,
  space_id: null,
};

const EMPTY: ShoppingList = { ...LIST, groups: [], pending: 0 };

type Reply = () => unknown;

let root: Root;
let host: HTMLElement;
let replies: Record<string, Reply>;
let asked: string[];
let offline: boolean;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  window.scrollTo = () => undefined;
  window.matchMedia = (query: string) =>
    ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }) as never;
});

beforeEach(async () => {
  reset();
  offline = false;
  window.history.replaceState(null, "", "/shopping/");
  asked = [];
  replies = {
    "GET /api/shopping/list": () => LIST,
    "GET /api/shopping/products": () => [],
    "GET /api/shopping/categories": () => [BAKERY, DAIRY],
    "GET /api/shopping/trips": () => [],
    "GET /api/shopping/version": () => ({ version: "1.0.0" }),
    "GET /api/kernel/spaces": () => [],
    "GET /api/shopping/me": () => ({ user_id: "persona-prueba" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      if (offline) throw new TypeError("sin red");
      asked.push(key);
      const reply = replies[key];
      if (!reply) return json({ detail: "no existe" }, 404);
      const body = await reply();
      return body instanceof Response ? body : json(body);
    }),
  );
  await queue.bindPerson("persona-prueba");
  await queue.flush(true);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const button = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((one) => one.textContent?.includes(name));

async function open(path: string) {
  window.history.replaceState(null, "", path);
  act(() => root.render(<App />));
  await settle();
}

async function serious(): Promise<string[]> {
  const result = await axe.run(host, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((one) => one.impact === "serious" || one.impact === "critical")
    .map((one) => `${one.id}: ${one.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

describe("la lista", () => {
  it("mientras llega, el esqueleto", async () => {
    replies["GET /api/shopping/list"] = () => new Promise(() => undefined);
    await open("/shopping/");
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("vacía, dice qué hacer y el botón lleva a apuntar", async () => {
    replies["GET /api/shopping/list"] = () => EMPTY;
    await open("/shopping/");
    expect(host.textContent).toContain("No hay nada apuntado");

    act(() => button("Apuntar algo")!.click());
    expect(document.activeElement).toBe(host.querySelector(".text-field input"));
  });

  it("si falla, lo dice y reintentar la trae", async () => {
    replies["GET /api/shopping/list"] = () => json({ detail: "la base no contesta" }, 503);
    await open("/shopping/");
    expect(host.textContent).toContain("No se ha podido leer la lista");

    replies["GET /api/shopping/list"] = () => LIST;
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Leche");
  });

  it("axe-core sin errores graves", async () => {
    await open("/shopping/");
    expect(await serious()).toEqual([]);
  });
});

describe("el historial", () => {
  it("vacío lleva a la lista", async () => {
    await open("/shopping/historial");
    expect(host.textContent).toContain("Todavía no hay compras");

    act(() => button("Ir a la lista")!.click());
    await settle();
    expect(window.location.pathname).toBe("/shopping/");
  });

  it("si falla, reintentar", async () => {
    replies["GET /api/shopping/trips"] = () => json({ detail: "no" }, 500);
    await open("/shopping/historial");
    expect(host.textContent).toContain("No se ha podido leer el historial");

    replies["GET /api/shopping/trips"] = () => [];
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Todavía no hay compras");
  });

  it("axe-core sin errores graves", async () => {
    await open("/shopping/historial");
    expect(await serious()).toEqual([]);
  });
});

describe("en el súper, sin cobertura", () => {
  it("tachar y apuntar se ven, se cuentan por enviar y se mandan en orden al volver", async () => {
    await open("/shopping/");
    offline = true;
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

    act(() => host.querySelector<HTMLElement>('[role="checkbox"], .check-row button, input[type="checkbox"]')!.click());
    await settle();
    expect(host.textContent).toContain("En el carro");

    const field = host.querySelector<HTMLInputElement>(".text-field input")!;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, "Pan");
      field.dispatchEvent(new Event("input", { bubbles: true }));
    });
    act(() => field.form?.requestSubmit() ?? field.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    await settle();

    expect(host.textContent).toContain("Pan");
    expect(host.textContent).toContain("2 cambios por enviar");

    offline = false;
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    replies["PUT /api/shopping/list/items/00000000-0000-4000-8000-0000000000a1/cart"] = () => LIST;
    replies["POST /api/shopping/list/items"] = () => ({ added: [], list: LIST });
    await act(async () => {
      window.dispatchEvent(new Event("online"));
    });
    await settle();

    const writes = asked.filter((one) => !one.startsWith("GET"));
    expect(writes).toEqual([
      "PUT /api/shopping/list/items/00000000-0000-4000-8000-0000000000a1/cart",
      "POST /api/shopping/list/items",
    ]);
    expect(host.textContent).not.toContain("por enviar");
  });
});
