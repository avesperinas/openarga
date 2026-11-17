// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { configureRegional, platformSay, regional } from "@openarga/ui";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { english, inLocale } from "./i18n/testing";

const GOAL = "0a0a0a0a-0000-4000-8000-00000000a0a0";

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

const instance = regional();
const retry = () => platformSay("error_state.retry");

beforeEach(() => {
  configureRegional({ locale: "en-US" });
  void reset();
  replies = {
    "GET /api/goals/categories": () => [],
    "GET /api/goals/goals": () => [],
    "GET /api/goals/goals?state=closed": () => [],
    "GET /api/goals/tasks": () => [],
    "GET /api/goals/tasks?state=done": () => [],
    "GET /api/goals/version": () => ({ version: "1.0.0" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const reply = replies[`${init?.method ?? "GET"} ${url}`];
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
  configureRegional(instance);
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const button = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((one) => one.textContent?.includes(name));

async function open(path = "/goals/goals") {
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

describe("the goals", () => {
  it("while they arrive, the skeleton", async () => {
    replies["GET /api/goals/goals"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("without goals, the button sets the first one", async () => {
    await open();
    expect(host.textContent).toContain(english("goals.empty"));
    expect(button(english("goals.set_one"))).toBeDefined();
  });

  it("if they fail, it says so and retrying brings them", async () => {
    replies["GET /api/goals/goals"] = () => json({ detail: "the database is not answering" }, 503);
    await open();
    expect(host.textContent).toContain(english("app.not_answering"));
    expect(host.textContent).toContain("the database is not answering");

    replies["GET /api/goals/goals"] = () => [];
    act(() => button(retry())!.click());
    await settle();
    expect(host.textContent).toContain(english("goals.empty"));
  });

  it("offline, it says so at the top", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.textContent).toContain(platformSay("offline.title"));
  });

  it("a goal that does not exist says so and goes back; any other failure is retried", async () => {
    replies[`GET /api/goals/goals/${GOAL}`] = () => json({ detail: `not found: goal '${GOAL}'` }, 404);
    await open(`/goals/goal/${GOAL}`);
    expect(host.textContent).toContain(english("goal.missing"));

    act(() => root.unmount());
    root = createRoot(host);
    void reset();
    replies[`GET /api/goals/goals/${GOAL}`] = () => json({ detail: "the database is not answering" }, 503);
    await open(`/goals/goal/${GOAL}`);
    expect(host.textContent).toContain("the database is not answering");
    expect(button(retry())).toBeDefined();
  });
});

describe("the tasks", () => {
  it("are the front page and the first tab; the goals, the second", async () => {
    await open("/goals/");
    expect(host.textContent).toContain(english("home.empty"));
    const tabs = Array.from(host.querySelectorAll("nav button, [role=tab]")).map((one) => one.textContent?.trim());
    expect(tabs.indexOf(english("tab.tasks"))).toBeLessThan(tabs.indexOf(english("tab.goals")));
    expect(tabs.indexOf(english("tab.tasks"))).toBeGreaterThanOrEqual(0);
  });

  it("without tasks, the button adds one", async () => {
    await open("/goals/");
    expect(host.textContent).toContain(english("home.empty"));
    expect(button(english("home.add_task"))).toBeDefined();
  });

  it("if they fail, retry", async () => {
    replies["GET /api/goals/tasks"] = () => json({ detail: "boom" }, 500);
    await open("/goals/");
    expect(host.querySelector("[role=alert]")).not.toBeNull();

    replies["GET /api/goals/tasks"] = () => [];
    act(() => button(retry())!.click());
    await settle();
    expect(host.textContent).toContain(english("home.empty"));
  });
});

describe("axe-core without serious errors", () => {
  it.each(["/goals/", "/goals/goals", "/goals/done", "/goals/settings"])("%s", async (path) => {
    await open(path);
    expect(await serious()).toEqual([]);
  });
});
