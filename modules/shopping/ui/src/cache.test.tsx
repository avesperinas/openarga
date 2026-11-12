// @vitest-environment jsdom
import { reset } from "@openarga/app";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { ShoppingList } from "./api";
import { App } from "./App";

const LIST: ShoppingList = {
  groups: [
    {
      category_id: "dairy",
      name: "Lácteos",
      emoji: "🥛",
      items: [
        {
          id: "leche",
          product_id: "p-leche",
          name: "Leche",
          category_id: "dairy",
          quantity: null,
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

type Reply = () => Promise<unknown> | unknown;

let root: Root;
let host: HTMLElement;
let replies: Record<string, Reply>;
let asked: string[];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  window.scrollTo = () => undefined;
  window.matchMedia = (query: string) =>
    ({ matches: false, media: query, addEventListener: () => undefined, removeEventListener: () => undefined }) as never;
});

beforeEach(() => {
  reset();
  window.history.replaceState(null, "", "/shopping/");
  asked = [];
  replies = {
    "GET /api/shopping/list": () => LIST,
    "GET /api/shopping/products": () => [],
    "GET /api/shopping/categories": () => [],
    "GET /api/shopping/trips": () => [],
    "GET /api/shopping/version": () => ({ version: "1.0.0" }),
    "GET /api/kernel/spaces": () => [],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      asked.push(key);
      const reply = replies[key];
      if (!reply) return json({ detail: "no existe" }, 404);
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
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const tab = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>(".tab-bar button")).find((one) => one.textContent?.includes(name))!;
const times = (key: string) => asked.filter((one) => one === key).length;

describe("Shopping con el kit de app", () => {
  it("de la lista al historial y vuelta: la lista, lo que compras y las secciones se piden una vez", async () => {
    act(() => root.render(<App />));
    await settle();
    expect(host.textContent).toContain("Leche");

    act(() => tab("Historial").click());
    await settle();
    act(() => tab("Lista").click());
    expect(host.textContent).toContain("Leche");
    await settle();

    expect(times("GET /api/shopping/list")).toBe(1);
    expect(times("GET /api/shopping/products")).toBe(1);
    expect(times("GET /api/shopping/categories")).toBe(1);
  });

  it("tachar algo lo baja al carro al tocar, y lo devuelve si el servidor no lo acepta", async () => {
    let answer!: (response: Response) => void;
    replies["PUT /api/shopping/list/items/leche/cart"] = () => new Promise<Response>((resolve) => (answer = resolve));
    act(() => root.render(<App />));
    await settle();

    act(() => host.querySelector<HTMLElement>("[role=checkbox]")!.click());
    await settle();
    expect(host.textContent).toContain("1 en el carro");
    expect(host.querySelector("[role=checkbox][aria-checked=true]")).not.toBeNull();

    answer(json({ detail: "esa lista ya no es la tuya" }, 409));
    await settle();
    expect(host.textContent).not.toContain("En el carro");
    expect(host.textContent).toContain("esa lista ya no es la tuya");
  });

  it("quitar desde la fila es al momento, y Deshacer lo vuelve a apuntar", async () => {
    let dropped = false;
    replies["POST /api/shopping/list/items/leche/drop"] = () => {
      dropped = true;
      return { ...LIST, groups: [], pending: 0 };
    };
    replies["POST /api/shopping/list/items"] = () => ({ added: [], list: LIST });
    act(() => root.render(<App />));
    await settle();

    const quitar = Array.from(host.querySelectorAll<HTMLButtonElement>(".swipe-row-action")).find((one) =>
      one.textContent?.includes("Quitar"),
    )!;
    act(() => quitar.click());
    expect(host.querySelector("[role=checkbox]")).toBeNull();
    await settle();
    expect(dropped).toBe(true);

    const undo = Array.from(document.querySelectorAll<HTMLButtonElement>(".toast-action")).find((one) =>
      one.textContent?.includes("Deshacer"),
    )!;
    act(() => undo.click());
    await settle();
    expect(times("POST /api/shopping/list/items")).toBe(1);
    expect(host.textContent).toContain("Leche");
  });
});

