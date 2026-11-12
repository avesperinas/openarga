// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const EVENT = "0a0a0a0a-0000-4000-8000-00000000e0e0";
const WISH = "0a0a0a0a-0000-4000-8000-00000000a0a0";

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
    "GET /api/outings/mine": () => ({ from: "2026-11-01", to: "2026-11-30", events: [] }),
    "GET /api/outings/foryou": () => [],
    "GET /api/outings/explore": () => ({ first: "2026-11-01", last: "2027-01-31", total: 0, events: [] }),
    "GET /api/outings/wishes": () => [],
    "GET /api/outings/planned": () => [],
    "GET /api/outings/interests": () => [],
    "GET /api/outings/agenda/sources": () => ({ plugged: [], offered: [], failed: null }),
    "GET /api/outings/version": () => ({ version: "1.0.0" }),
    "GET /api/kernel/spaces": () => [],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const reply = replies[`${method} ${url}`] ?? replies[`${method} ${url.split("?")[0]}`];
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
  vi.restoreAllMocks();
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const retry = () => host.querySelector<HTMLButtonElement>('.empty-state[role="alert"] button') ?? undefined;

const button = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((one) => one.textContent?.includes(name));

async function open(path = "/outings/") {
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

describe("the agenda", () => {
  it("while it arrives, the skeleton", async () => {
    replies["GET /api/outings/mine"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("empty, the button goes to Explore", async () => {
    await open();
    expect(host.textContent).toContain("Your agenda is empty");
    act(() => button("Explore")!.click());
    await settle();
    expect(window.location.pathname).toBe("/outings/explore");
  });

  it("if it fails, it says so and retrying brings it", async () => {
    replies["GET /api/outings/mine"] = () => json({ detail: "the database is not answering" }, 503);
    await open();
    expect(host.textContent).toContain("Outings is not answering");
    expect(host.textContent).toContain("the database is not answering");

    replies["GET /api/outings/mine"] = () => ({ from: "2026-11-01", to: "2026-11-30", events: [] });
    act(() => retry()!.click());
    await settle();
    expect(host.textContent).toContain("Your agenda is empty");
  });

  it("offline, it says so at the top", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.querySelector('.notice[data-tone="warning"]')).not.toBeNull();
  });
});

describe("explore", () => {
  it("with nothing in the agenda, the button asks your AI to fill it", async () => {
    await open("/outings/explore");
    expect(host.textContent).toContain("The agenda is empty");
    expect(button("Update")).toBeDefined();
  });

  it("if it fails, it retries", async () => {
    replies["GET /api/outings/explore"] = () => json({ detail: "the database is not answering" }, 503);
    await open("/outings/explore");
    expect(host.textContent).toContain("the database is not answering");
    expect(retry()).toBeDefined();
  });
});

describe("the wishes", () => {
  it("with none, the button notes the first", async () => {
    await open("/outings/wishes");
    expect(host.textContent).toContain("Nothing noted yet");
    expect(button("Note")).toBeDefined();
  });

  it("one that is gone says so; another failure retries", async () => {
    await open(`/outings/wishes/${WISH}`);
    expect(host.textContent).toContain("Not here any more");
    expect(retry()).toBeUndefined();

    act(() => root.unmount());
    root = createRoot(host);
    void reset();
    replies[`GET /api/outings/wishes/${WISH}`] = () => json({ detail: "the database is not answering" }, 503);
    await open(`/outings/wishes/${WISH}`);
    expect(host.textContent).toContain("the database is not answering");
    expect(retry()).toBeDefined();
  });
});

describe("an event", () => {
  it("if it does not exist, it says so", async () => {
    await open(`/outings/events/${EVENT}`);
    expect(host.textContent).toContain("Not here any more");
  });
});

describe("the settings", () => {
  it("if they cannot be read, it retries", async () => {
    replies["GET /api/outings/interests"] = () => json({ detail: "the database is not answering" }, 503);
    await open("/outings/settings");
    expect(host.textContent).toContain("the database is not answering");
    expect(retry()).toBeDefined();
  });
});

describe("axe-core without serious errors", () => {
  it.each(["/outings/", "/outings/explore", "/outings/wishes", "/outings/settings"])("%s", async (path) => {
    await open(path);
    expect(await serious()).toEqual([]);
  });
});
