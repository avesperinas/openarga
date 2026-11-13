// @vitest-environment jsdom
import { reset } from "@openarga/app";
import { ToastHost } from "@openarga/ui";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { Layer, Occurrence } from "./api";
import { App } from "./App";

const PERSONAL: Layer = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Personal",
  tone: 5,
  origin: "own",
  visible: true,
  position: 0,
  display: "events",
  connection_id: null,
  days_off_from: [],
};

const DINNER: Occurrence = {
  id: "e1",
  event_id: "00000000-0000-4000-8000-000000000001",
  calendar_id: PERSONAL.id,
  title: "Synthetic dinner",
  all_day: false,
  start: new Date(Date.now() + 2 * 3600_000).toISOString(),
  end: new Date(Date.now() + 3 * 3600_000).toISOString(),
  tz: "Europe/Madrid",
  location: "Casa",
  notes: null,
  url: null,
  status: "confirmed",
  original_start: null,
  rrule: null,
  repeat: null,
  moved: false,
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
  Element.prototype.scrollTo = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
    }) as never;
  class Watcher {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver = Watcher;
  (globalThis as { IntersectionObserver?: unknown }).IntersectionObserver = Watcher;
});

beforeEach(() => {
  void reset();
  replies = {
    "GET /api/planner/calendars": () => [PERSONAL],
    "GET /api/planner/occurrences": () => [DINNER],
    "GET /api/planner/version": () => ({ version: "1.0.0" }),
    "GET /api/planner/subscriptions/catalogue": () => ({ groups: [], sources: [], others: [] }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const reply = replies[`${method} ${url}`] ?? replies[`${method} ${url.split("?")[0]}`];
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
  document.body.innerHTML = "";
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const retry = () => document.querySelector<HTMLButtonElement>('.empty-state[role="alert"] button') ?? undefined;

const button = (name: string) =>
  Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((one) => one.textContent?.includes(name));

async function open(path = "/planner/semana") {
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
  const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((one) => one.impact === "serious" || one.impact === "critical")
    .map((one) => `${one.id}: ${one.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

describe("the week", () => {
  it("while it arrives, the skeleton", async () => {
    replies["GET /api/planner/occurrences"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("with its items, its events", async () => {
    await open();
    expect(host.textContent).toContain("Synthetic dinner");
  });

  it("if it fails, it says so and retrying brings it", async () => {
    replies["GET /api/planner/occurrences"] = () => json({ detail: "the database is not answering" }, 503);
    await open();
    expect(host.textContent).toContain("Planner is not answering");
    expect(host.textContent).toContain("the database is not answering");

    replies["GET /api/planner/occurrences"] = () => [DINNER];
    await act(async () => retry()!.click());
    await settle();
    expect(host.textContent).toContain("Synthetic dinner");
  });

  it("offline, it says so at the top", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.querySelector('.notice[data-tone="warning"]')).not.toBeNull();
  });
});

describe("the agenda", () => {
  it("with nothing, the button creates the first", async () => {
    replies["GET /api/planner/occurrences"] = () => [];
    await open("/planner/agenda");
    expect(host.textContent).toContain("Nothing in the next 60 days");
    act(() => button("New event")!.click());
    await settle();
    expect(document.body.textContent).toContain("Create");
  });
});

describe("an event", () => {
  it("opens alongside, from the address", async () => {
    await open(`/planner/semana?event=${DINNER.event_id}`);
    const detail = host.querySelector('[role="region"][aria-label="Evento"]');
    expect(detail?.textContent).toContain("Synthetic dinner");
    expect(detail?.textContent).toContain("Casa");
  });
});

describe("the subscriptions", () => {
  it("if Hub is not answering, it retries; without sources, it leads to Hub", async () => {
    replies["GET /api/planner/subscriptions/catalogue"] = () => json({ detail: "sin hub" }, 503);
    await open();
    await act(async () => button("Subscriptions")?.click() ?? document.querySelector<HTMLButtonElement>('[aria-label="Subscriptions: add or remove"]')!.click());
    await settle();
    expect(document.body.textContent).toContain("Hub is not answering");

    replies["GET /api/planner/subscriptions/catalogue"] = () => ({ groups: [], sources: [], others: [] });
    await act(async () => retry()!.click());
    await settle();
    expect(document.body.textContent).toContain("Nothing to subscribe to yet");
    expect(button("Go to Hub")).toBeDefined();
  });
});

describe("axe-core without serious errors", () => {
  it.each(["/planner/semana", "/planner/mes", "/planner/agenda", "/planner/dia", `/planner/semana?event=${DINNER.event_id}`])(
    "%s",
    async (path) => {
      await open(path);
      expect(await serious()).toEqual([]);
    },
  );
});
