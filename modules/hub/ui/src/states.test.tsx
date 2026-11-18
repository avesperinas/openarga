// @vitest-environment jsdom
import { reset } from "@openarga/app";
import { configureRegional } from "@openarga/ui";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const CONNECTION = "0b7c2f1e-1b1a-4c55-9d1e-8a6f4a3c2b10";

type Reply = () => unknown;

let root: Root;
let host: HTMLElement;
let replies: Record<string, Reply>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

beforeAll(() => {
  configureRegional({ locale: "en-GB" });
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
    "GET /api/hub/catalogue": () => [
      {
        id: "calendar",
        name: "Calendarios",
        providers: [
          { id: "ical", name: "Calendario iCal", description: "", capabilities: ["sync"], available: true, single: false, lives_in: null, secrets: [] },
        ],
      },
    ],
    "GET /api/hub/connections": () => [],
    "GET /api/hub/apps": () => ({
      apps: [{ module: "planner", name: "Planner", view: "/planner", inlets: [{ key: "calendar", title: "Calendarios", providers: ["ical"] }], services: [] }],
      others: [],
    }),
    "GET /api/hub/version": () => ({ version: "1.0.0" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const reply = replies[`${method} ${url}`] ?? replies[`${method} ${url.split("?")[0]}`];
      if (!reply) return json({ detail: "that connection does not exist" }, 404);
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

async function open(path = "/hub/") {
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

describe("the front page", () => {
  it("while it arrives, the skeleton", async () => {
    replies["GET /api/hub/connections"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("with nothing connected, the button leads to connecting a source", async () => {
    await open();
    expect(host.textContent).toContain("Nothing connected here yet");
    act(() => button("Connect a source")!.click());
    await settle();
    expect(window.location.pathname).toBe("/hub/setup");
    expect(host.textContent).toContain("Planner");
  });

  it("when it fails it says so, and trying again brings it", async () => {
    replies["GET /api/hub/connections"] = () => json({ detail: "the database is not answering" }, 503);
    await open();
    expect(host.textContent).toContain("Hub is not answering");
    expect(host.textContent).toContain("the database is not answering");

    replies["GET /api/hub/connections"] = () => [];
    act(() => button("Try again")!.click());
    await settle();
    expect(host.textContent).toContain("Nothing connected here yet");
  });

  it("offline, it says so at the top", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.textContent).toContain("Offline");
  });
});

describe("a connection", () => {
  it("when it does not exist it says so; another failure can be retried", async () => {
    await open(`/hub/${CONNECTION}`);
    expect(host.textContent).toContain("It is no longer here");
    expect(button("Try again")).toBeUndefined();

    act(() => root.unmount());
    root = createRoot(host);
    void reset();
    replies[`GET /api/hub/connections/${CONNECTION}`] = () => json({ detail: "the database is not answering" }, 503);
    await open(`/hub/${CONNECTION}`);
    expect(host.textContent).toContain("the database is not answering");
    expect(button("Try again")).toBeDefined();
  });
});

describe("axe-core without serious errors", () => {
  it.each(["/hub/", "/hub/setup", "/hub/settings"])("%s", async (path) => {
    await open(path);
    expect(await serious()).toEqual([]);
  });
});
