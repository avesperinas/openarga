// @vitest-environment jsdom
import { reset } from "@openarga/app";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { ShoppingList } from "./api";
import { App } from "./App";
import { english, inLocale } from "./i18n/testing";

const LIST: ShoppingList = {
  groups: [
    {
      category_id: "dairy",
      name: "Dairy and eggs",
      emoji: "🥛",
      items: [
        {
          id: "milk",
          product_id: "p-milk",
          name: "Milk",
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
      if (!reply) return json({ detail: "not found" }, 404);
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

describe("Shopping with the app kit", () => {
  it("from the list to the history and back: list, products and sections are asked once", async () => {
    act(() => root.render(inLocale(<App />)));
    await settle();
    expect(host.textContent).toContain("Milk");

    act(() => tab(english("tabs.history")).click());
    await settle();
    act(() => tab(english("tabs.list")).click());
    expect(host.textContent).toContain("Milk");
    await settle();

    expect(times("GET /api/shopping/list")).toBe(1);
    expect(times("GET /api/shopping/products")).toBe(1);
    expect(times("GET /api/shopping/categories")).toBe(1);
  });

  it("ticking something moves it to the trolley at once, and back if the server refuses it", async () => {
    let answer!: (response: Response) => void;
    replies["PUT /api/shopping/list/items/milk/cart"] = () => new Promise<Response>((resolve) => (answer = resolve));
    act(() => root.render(inLocale(<App />)));
    await settle();

    act(() => host.querySelector<HTMLElement>("[role=checkbox]")!.click());
    await settle();
    expect(host.textContent).toContain(english("cart.one"));
    expect(host.querySelector("[role=checkbox][aria-checked=true]")).not.toBeNull();

    answer(json({ detail: "that list is no longer yours" }, 409));
    await settle();
    expect(host.textContent).not.toContain(english("cart.title"));
    expect(host.textContent).toContain("that list is no longer yours");
  });

  it("removing from the row is immediate, and Undo adds it again", async () => {
    let dropped = false;
    replies["POST /api/shopping/list/items/milk/drop"] = () => {
      dropped = true;
      return { ...LIST, groups: [], pending: 0 };
    };
    replies["POST /api/shopping/list/items"] = () => ({ added: [], list: LIST });
    act(() => root.render(inLocale(<App />)));
    await settle();

    const remove = Array.from(host.querySelectorAll<HTMLButtonElement>(".swipe-row-action")).find((one) =>
      one.textContent?.includes(english("item.remove")),
    )!;
    act(() => remove.click());
    expect(host.querySelector("[role=checkbox]")).toBeNull();
    await settle();
    expect(dropped).toBe(true);

    const undo = Array.from(document.querySelectorAll<HTMLButtonElement>(".toast-action")).find((one) =>
      one.textContent?.includes(english("removed.undo")),
    )!;
    act(() => undo.click());
    await settle();
    expect(times("POST /api/shopping/list/items")).toBe(1);
    expect(host.textContent).toContain("Milk");
  });
});

