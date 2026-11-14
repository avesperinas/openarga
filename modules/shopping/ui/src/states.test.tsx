// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { type Category, type ShoppingList, queue } from "./api";
import { App } from "./App";
import { english, inLocale } from "./i18n/testing";

const DAIRY: Category = { id: "dairy", name: "Dairy and eggs", emoji: "🥛", position: 3 };
const BAKERY: Category = { id: "bakery", name: "Bakery", emoji: "🥖", position: 2 };

const LIST: ShoppingList = {
  groups: [
    {
      category_id: "dairy",
      name: "Dairy and eggs",
      emoji: "🥛",
      items: [
        {
          id: "00000000-0000-4000-8000-0000000000a1",
          product_id: "00000000-0000-4000-8000-0000000000b1",
          name: "Milk",
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
    "GET /api/shopping/me": () => ({ user_id: "test-person" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      if (offline) throw new TypeError("no network");
      asked.push(key);
      const reply = replies[key];
      if (!reply) return json({ detail: "not found" }, 404);
      const body = await reply();
      return body instanceof Response ? body : json(body);
    }),
  );
  await queue.bindPerson("test-person");
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

const retry = () => host.querySelector<HTMLButtonElement>("[role=alert] button");

const button = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((one) => one.textContent?.includes(name));

async function open(path: string) {
  window.history.replaceState(null, "", path);
  act(() => root.render(inLocale(<App />)));
  await settle();
}

async function serious(): Promise<string[]> {
  const result = await axe.run(host, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((one) => one.impact === "serious" || one.impact === "critical")
    .map((one) => `${one.id}: ${one.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

describe("the list", () => {
  it("while it comes, the skeleton", async () => {
    replies["GET /api/shopping/list"] = () => new Promise(() => undefined);
    await open("/shopping/");
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("empty, it says what to do and the button leads to adding", async () => {
    replies["GET /api/shopping/list"] = () => EMPTY;
    await open("/shopping/");
    expect(host.textContent).toContain(english("empty.title"));

    act(() => button(english("empty.action"))!.click());
    expect(document.activeElement).toBe(host.querySelector(".text-field input"));
  });

  it("if it fails, it says so and retrying brings it", async () => {
    replies["GET /api/shopping/list"] = () => json({ detail: "the database does not answer" }, 503);
    await open("/shopping/");
    expect(host.textContent).toContain(english("list.read_failed"));

    replies["GET /api/shopping/list"] = () => LIST;
    act(() => retry()!.click());
    await settle();
    expect(host.textContent).toContain("Milk");
  });

  it("axe-core without serious errors", async () => {
    await open("/shopping/");
    expect(await serious()).toEqual([]);
  });
});

describe("the history", () => {
  it("empty, it leads to the list", async () => {
    await open("/shopping/history");
    expect(host.textContent).toContain(english("history.empty"));

    act(() => button(english("history.go_list"))!.click());
    await settle();
    expect(window.location.pathname).toBe("/shopping/");
  });

  it("if it fails, retry", async () => {
    replies["GET /api/shopping/trips"] = () => json({ detail: "no" }, 500);
    await open("/shopping/history");
    expect(host.textContent).toContain(english("history.read_failed"));

    replies["GET /api/shopping/trips"] = () => [];
    act(() => retry()!.click());
    await settle();
    expect(host.textContent).toContain(english("history.empty"));
  });

  it("axe-core without serious errors", async () => {
    await open("/shopping/history");
    expect(await serious()).toEqual([]);
  });
});

describe("in the supermarket, without coverage", () => {
  it("ticking and adding show, count as waiting and are sent in order when back", async () => {
    await open("/shopping/");
    offline = true;
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

    act(() => host.querySelector<HTMLElement>('[role="checkbox"], .check-row button, input[type="checkbox"]')!.click());
    await settle();
    expect(host.textContent).toContain(english("cart.title"));

    const field = host.querySelector<HTMLInputElement>(".text-field input")!;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, "Bread");
      field.dispatchEvent(new Event("input", { bubbles: true }));
    });
    act(() => field.form?.requestSubmit() ?? field.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    await settle();

    expect(host.textContent).toContain("Bread");
    expect(host.querySelector('.notice[data-tone="warning"]')?.textContent).toContain("2");

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
    expect(host.querySelector('.notice[data-tone="warning"]')).toBeNull();
  });
});
