// @vitest-environment jsdom
import { invalidate, prime, reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { Insight, Profile } from "./api";
import { App } from "./App";

const ID = "0a0a0a0a-0000-4000-8000-00000000a0a0";

const figure = { label: "dinners out this week", value: 4, unit: null, baseline: 2, baseline_label: "your average" };

const WEEK: Insight = {
  id: ID,
  kind: "weekly",
  domain: "cross",
  topic: "week:2026-w42",
  title: "A week of eating out a lot",
  body: "Cenaste fuera cuatro veces.",
  figures: [figure],
  affects: "the December cushion",
  action: "Three dinners at home from Monday to Thursday.",
  created_at: "2026-10-18T17:00:00Z",
  read_at: null,
  rating: null,
  rated_at: null,
  proposals: [
    { what: "Three dinners at home from Monday to Thursday", figure, how: "Shopping: add three dinners to the list" },
    { what: "Two strength sessions on Tuesday and Thursday", figure, how: "Planner: a 45 min block at 19:00" },
    { what: "Go to bed before 23:30 on weekdays", figure, how: "Planner: a reminder at 23:00" },
  ],
};

const PROFILE: Profile = { name: "Txuri", about: "", named: true };

type Reply = () => unknown;

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
  asked = [];
  replies = {
    "GET /api/insights/profile": () => PROFILE,
    "GET /api/insights/insights": () => [WEEK],
    "GET /api/insights/signals": () => [],
    "GET /api/insights/runs": () => [],
    "GET /api/insights/threads": () => [],
    "GET /api/insights/version": () => ({ version: "1.0.0" }),
    [`POST /api/insights/insights/${ID}/read`]: () => ({ ...WEEK, read_at: "2026-10-18T18:00:00Z" }),
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
  vi.restoreAllMocks();
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const retry = () => host.querySelector<HTMLButtonElement>(".empty-state[role=alert] button") ?? undefined;

const button = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((one) => one.textContent?.includes(name));

async function open(path = "/insights/inbox") {
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

describe("the inbox", () => {
  it("while the advice arrives, the skeleton", async () => {
    replies["GET /api/insights/insights"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("without advice, it says what to do and the button leads to telling it what matters", async () => {
    replies["GET /api/insights/insights"] = () => [];
    await open();
    expect(host.textContent).toContain("Txuri has not told you anything yet");

    act(() => button("Tell it what matters to you")!.click());
    await settle();
    expect(window.location.pathname).toBe("/insights/you");
  });

  it("when the advice fails, it says so and retrying brings it", async () => {
    replies["GET /api/insights/insights"] = () => json({ detail: "the database does not answer" }, 503);
    await open();
    expect(host.textContent).toContain("The advice could not be read");
    expect(host.textContent).toContain("the database does not answer");

    replies["GET /api/insights/insights"] = () => [WEEK];
    act(() => retry()!.click());
    await settle();
    expect(host.textContent).toContain("A week of eating out a lot");
  });

  it("offline, it says so on top", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.querySelector('.notice[data-tone="warning"]')).not.toBeNull();
  });

  it("axe-core without serious errors", async () => {
    await open();
    expect(await serious()).toEqual([]);
  });
});

describe("the Sunday summary", () => {
  it("brings its numbered proposals, with their figure and how to ask for them", async () => {
    await open(`/insights/insight/${ID}`);

    expect(asked).toContain(`POST /api/insights/insights/${ID}/read`);
    expect(host.textContent).toContain("Next week");
    expect(host.textContent).toContain("1. Three dinners at home from Monday to Thursday");
    expect(host.textContent).toContain("3. Go to bed before 23:30 on weekdays");
    expect(host.textContent).toContain("Planner: a 45 min block at 19:00");
    expect(host.textContent).toContain("ask your assistant");
    expect(await serious()).toEqual([]);
  });

  it("a single alert still says what it would do", async () => {
    const alert = { ...WEEK, kind: "alert" as const, proposals: [] };
    replies[`POST /api/insights/insights/${ID}/read`] = () => alert;
    replies["GET /api/insights/insights"] = () => [alert];
    await open(`/insights/insight/${ID}`);

    expect(host.textContent).toContain("What it would do");
    expect(host.textContent).not.toContain("Next week");
  });

  it("if it cannot be opened, retry", async () => {
    replies["GET /api/insights/insights"] = () => [];
    replies[`POST /api/insights/insights/${ID}/read`] = () => json({ detail: "no" }, 500);
    await open(`/insights/insight/${ID}`);
    expect(host.textContent).toContain("The advice could not be opened");

    replies[`POST /api/insights/insights/${ID}/read`] = () => WEEK;
    act(() => retry()!.click());
    await settle();
    expect(host.textContent).toContain("Next week");
  });
});

describe("hablar", () => {
  it("without conversations, the button starts one", async () => {
    await open("/insights/chat");
    expect(host.textContent).toContain("Ask Txuri anything");

    act(() => button("Start talking")!.click());
    await settle();
    expect(window.location.pathname).toBe("/insights/chat/new");
  });

  it("when the conversations fail, retry", async () => {
    replies["GET /api/insights/threads"] = () => json({ detail: "no" }, 500);
    await open("/insights/chat");
    expect(host.textContent).toContain("The conversations could not be read");

    replies["GET /api/insights/threads"] = () => [];
    act(() => retry()!.click());
    await settle();
    expect(host.textContent).toContain("Ask Txuri anything");
  });

  it("axe-core without serious errors, also in the settings", async () => {
    await open("/insights/chat");
    expect(await serious()).toEqual([]);
    act(() => root.unmount());
    root = createRoot(host);
    await open("/insights/settings");
    expect(await serious()).toEqual([]);
  });
});

describe("the settings", () => {
  it("the fields fill with what the server has, not what the device kept", async () => {
    prime<Profile>("profile", { name: "Other", about: "someone else's", named: true });
    invalidate("profile");
    const waiting: ((profile: Profile) => void)[] = [];
    replies["GET /api/insights/profile"] = () => new Promise<Profile>((resolve) => waiting.push(resolve));
    await open("/insights/settings");
    expect(host.querySelector("textarea")).toBeNull();

    await act(async () => waiting.forEach((answer) => answer({ ...PROFILE, about: "mine" })));
    await settle();
    expect((host.querySelector("textarea") as HTMLTextAreaElement).value).toBe("mine");
  });
});
