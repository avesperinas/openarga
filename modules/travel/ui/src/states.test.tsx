// @vitest-environment jsdom
import { reset } from "@openarga/app";
import { configureRegional } from "@openarga/ui";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { queue } from "./api";
import { App } from "./App";

const TRIP = "0a0a0a0a-0000-4000-8000-00000000e1c0";

const EMPTY_ATLAS = { trips: [], others: [], home: null, ideas: [] };
const EMPTY_STATS = {
  trips: 0,
  nights: 0,
  km: 0,
  countries: 0,
  regions: 0,
  europe_visited: [],
  europe_total: 44,
  by_year: [],
  km_by_mode: { plane: 0, train: 0, car: 0, bus: 0, boat: 0 },
  top_countries: [],
  cost_per_day: [],
  average_cost_per_day: null,
  spend_per_night_by_country: [],
  nights_calendar: {},
};
const NO_TRIP_TODAY = { day: "2026-11-03", trip: null, sleeping: null, entries: [], here: null, next_trip: null };

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

beforeEach(async () => {
  configureRegional({ locale: "en-GB" });
  void reset();
  await queue.bindPerson(`test-${Math.random()}`);
  replies = {
    "GET /api/travel/atlas": () => EMPTY_ATLAS,
    "GET /api/travel/stats": () => EMPTY_STATS,
    "GET /api/travel/today": () => NO_TRIP_TODAY,
    "GET /api/travel/me": () => ({ user_id: "00000000-0000-4000-8000-00000000a7e5" }),
    "GET /api/travel/version": () => ({ version: "1.0.0" }),
    "GET /api/kernel/spaces": () => [],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const reply = replies[`${method} ${url}`] ?? replies[`${method} ${url.split("?")[0]}`];
      if (!reply) return json({ detail: "does not exist" }, 404);
      const body = await reply();
      return body instanceof Response ? body : json(body);
    }),
  );
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  configureRegional({ locale: "es-ES" });
  act(() => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 8; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const button = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find(
    (one) => one.textContent?.includes(name) || one.getAttribute("aria-label") === name,
  );

async function open(path: string) {
  window.history.replaceState(null, "", path);
  act(() => root.render(<App />));
  await settle();
}

async function shows(text: string) {
  await vi.waitFor(async () => {
    await settle();
    expect(host.textContent).toContain(text);
  });
}

async function serious(): Promise<string[]> {
  const result = await axe.run(host, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((one) => one.impact === "serious" || one.impact === "critical")
    .map((one) => `${one.id}: ${one.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

describe("trips", () => {
  it("while they arrive, the skeleton", async () => {
    replies["GET /api/travel/atlas"] = () => new Promise(() => undefined);
    await open("/travel/trips");
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("without trips, the button adds the first", async () => {
    await open("/travel/trips");
    expect(host.textContent).toContain("No trips made yet");
    expect(button("Add a trip")).toBeDefined();
  });

  it("if it fails, it says so and retrying brings it", async () => {
    replies["GET /api/travel/atlas"] = () => json({ detail: "the database does not answer" }, 503);
    await open("/travel/trips");
    expect(host.textContent).toContain("Travel does not answer");
    expect(host.textContent).toContain("the database does not answer");

    replies["GET /api/travel/atlas"] = () => EMPTY_ATLAS;
    await act(async () => button("Try again")!.click());
    await settle();
    expect(host.textContent).toContain("No trips made yet");
  });

  it("offline, it says so on top", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open("/travel/trips");
    expect(host.textContent).toContain("Offline");
  });
});

describe("plans", () => {
  it("without any, the button plans one", async () => {
    await open("/travel/plans");
    expect(host.textContent).toContain("No plans");
    expect(button("Plan a trip")).toBeDefined();
  });
});

describe("today", () => {
  it("without a trip under way, the button plans one", async () => {
    await open("/travel/today");
    expect(host.textContent).toContain("No trip under way today");
    expect(button("Plan a trip")).toBeDefined();
  });

  it("if it fails, it is retried", async () => {
    replies["GET /api/travel/today"] = () => json({ detail: "the database does not answer" }, 503);
    await open("/travel/today");
    expect(host.textContent).toContain("the database does not answer");
    expect(button("Try again")).toBeDefined();
  });
});

describe("today's journal", () => {
  const ONGOING = {
    ...NO_TRIP_TODAY,
    trip: { id: TRIP, title: "Lisboa", number: 2, days: 4, day_title: null },
    journal: null,
  };

  it("it is written offline: it stays and waits to be sent", async () => {
    await queue.bindPerson("00000000-0000-4000-8000-00000000a7e5");
    replies["GET /api/travel/today"] = () => ONGOING;
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    replies[`PUT /api/travel/trips/${TRIP}/journal`] = () => {
      throw new TypeError("offline");
    };
    const fetcher = globalThis.fetch as ReturnType<typeof vi.fn>;
    const answer = fetcher.getMockImplementation()!;
    fetcher.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") throw new TypeError("offline");
      return answer(url, init);
    });
    await open("/travel/today");
    await shows("Today's journal");

    await act(async () => button("Write")!.click());
    const box = host.ownerDocument.querySelector<HTMLTextAreaElement>("textarea")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(box, "Tram 28.");
      box.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const save = Array.from(host.ownerDocument.querySelectorAll<HTMLButtonElement>("button")).find(
      (one) => one.textContent === "Save",
    )!;
    await act(async () => save.click());
    await settle();

    expect(host.textContent).toContain("Tram 28.");
    expect(host.textContent).toContain("1 change waiting to be sent");
  });
});

describe("figures", () => {
  it("without trips, the button adds the first", async () => {
    await open("/travel/stats");
    await shows("No figures yet");
    expect(button("Add a trip")).toBeDefined();
  });
});

describe("a trip's bookings", () => {
  it("if it does not exist it says so; another failure is retried", async () => {
    await open(`/travel/trips/${TRIP}/bookings`);
    await shows("It is no longer here");
    expect(button("Try again")).toBeUndefined();

    act(() => root.unmount());
    root = createRoot(host);
    void reset();
    for (const path of ["", "/days", "/bookings"]) {
      replies[`GET /api/travel/trips/${TRIP}${path}`] = () => json({ detail: "the database does not answer" }, 503);
    }
    await open(`/travel/trips/${TRIP}/bookings`);
    await shows("the database does not answer");
    expect(button("Try again")).toBeDefined();
  });
});

describe("axe-core without serious errors", () => {
  it.each([
    ["/travel/trips", "No trips made yet"],
    ["/travel/plans", "No plans"],
    ["/travel/today", "No trip under way today"],
    ["/travel/stats", "No figures yet"],
  ])("%s", async (path, text) => {
    await open(path);
    await shows(text);
    expect(await serious()).toEqual([]);
  });
});
