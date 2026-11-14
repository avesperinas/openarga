// @vitest-environment jsdom
import { reset } from "@openarga/app";
import { ToastHost } from "@openarga/ui";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const NOTE = "0a0a0a0a-0000-4000-8000-00000000a0a0";
const NOW = "2026-10-29T10:00:00Z";
const SUMMARY = { id: NOTE, folder: "Projects", title: "Orchard", path: "Projects/Orchard", updated_at: NOW, updated_by: "app" };
const FULL = {
  ...SUMMARY,
  content: "# Orchard\n\nTomatoes and basil.\n",
  properties: {},
  tags: [],
  outline: [{ level: 1, text: "Orchard", line: 0 }],
  version: 1,
  created_at: NOW,
  arga: null,
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
  replies = {
    "GET /api/notebook/tree": () => ({ folders: [], notes: [] }),
    "GET /api/notebook/tags": () => [],
    "GET /api/notebook/linkables": () => [],
    "GET /api/notebook/review": () => ({ chosen: false, notes: [] }),
    "GET /api/notebook/trash": () => [],
    "GET /api/notebook/graph": () => ({ nodes: [], edges: [] }),
    "GET /api/notebook/settings": () => ({ daily_folder: "Journal", review_property: null }),
    "GET /api/notebook/properties": () => [],
    "GET /api/notebook/export": () => ({ pushed_at: null, tried_at: null, outcome: "unconnected", detail: null, commit_url: null, pending: 0 }),
    "GET /api/notebook/search": () => [],
    "GET /api/notebook/version": () => ({ version: "1.0.0" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const reply = replies[`${method} ${url}`] ?? replies[`${method} ${url.split("?")[0]}`];
      if (!reply) return json({ detail: "not found: that" }, 404);
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

const retry = () => host.querySelector<HTMLButtonElement>(".empty-state[role=alert] button") ?? undefined;

async function open(path = "/notebook/") {
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
  const result = await axe.run(host, { rules: { "color-contrast": { enabled: false } } });
  return result.violations
    .filter((one) => one.impact === "serious" || one.impact === "critical")
    .map((one) => `${one.id}: ${one.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

describe("the notes", () => {
  it("while the tree arrives, the skeleton, and no loading text", async () => {
    replies["GET /api/notebook/tree"] = () => new Promise(() => undefined);
    await open("/notebook/notes");
    expect(host.querySelector(".skeleton")).not.toBeNull();
    expect(host.textContent).not.toMatch(/Loading|Cargando/);
  });

  it("without notes, the button creates the first one", async () => {
    await open("/notebook/notes");
    expect(host.textContent).toContain("No notes yet");
    expect(button("New note")).toBeDefined();
  });

  it("when it fails, it says so and retrying brings it", async () => {
    replies["GET /api/notebook/tree"] = () => json({ detail: "the database does not answer" }, 503);
    await open("/notebook/notes");
    expect(host.textContent).toContain("Notes does not answer");
    expect(host.textContent).toContain("the database does not answer");

    replies["GET /api/notebook/tree"] = () => ({ folders: ["Projects"], notes: [SUMMARY] });
    act(() => retry()!.click());
    await settle();
    expect(host.textContent).toContain("Projects");
  });

  it("offline, it says so on top", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open("/notebook/notes");
    expect(host.querySelector('.notice[data-tone="warning"]')).not.toBeNull();
  });
});

describe("a note", () => {
  it("is read without waiting for the editor", async () => {
    replies["GET /api/notebook/tree"] = () => ({ folders: ["Projects"], notes: [SUMMARY] });
    replies[`GET /api/notebook/notes/${NOTE}`] = () => FULL;
    replies[`GET /api/notebook/notes/${NOTE}/links`] = () => ({ links: [], backlinks: [] });
    await open(`/notebook/note/${NOTE}`);
    expect(host.textContent).toContain("Tomatoes and basil.");
    expect(button("Edit")).toBeDefined();
  });

  it("a missing note says so; another failure can be retried", async () => {
    await open(`/notebook/note/${NOTE}`);
    expect(host.textContent).toContain("This note is no longer here");
    expect(retry()).toBeUndefined();

    act(() => root.unmount());
    root = createRoot(host);
    void reset();
    replies[`GET /api/notebook/notes/${NOTE}`] = () => json({ detail: "the database does not answer" }, 503);
    await open(`/notebook/note/${NOTE}`);
    expect(host.textContent).toContain("the database does not answer");
    expect(retry()).toBeDefined();
  });
});

describe("the other screens", () => {
  it("review, without a chosen property, leads to choosing it", async () => {
    await open("/notebook/review");
    expect(button("Choose it")).toBeDefined();
  });

  it("the empty trash goes back to the notes", async () => {
    await open("/notebook/trash");
    expect(host.textContent).toContain("The trash is empty");
    expect(button("Back to the notes")).toBeDefined();
  });

  it("opening Notes shows the graph, in its tab", async () => {
    await open("/notebook/");
    expect(host.textContent).toContain("Nothing to link yet");
    expect(host.querySelector('[aria-current="page"]')?.textContent).toContain("Graph");
  });

  it("the graph without links offers a new note", async () => {
    await open("/notebook/graph");
    expect(host.textContent).toContain("Nothing to link yet");
    expect(button("New note")).toBeDefined();
  });

  it("a search that matches nothing offers to clear it", async () => {
    await open("/notebook/search?q=nothing");
    expect(host.textContent).toContain("Nothing with that");
    expect(button("Clear the search")).toBeDefined();
  });

  it("the settings are the common ones, with those of Notes on top", async () => {
    await open("/notebook/settings");
    expect(host.textContent).toContain("Daily note");
    expect(host.textContent).toContain("Copy on GitHub");
  });
});

describe("axe-core without serious errors", () => {
  it.each(["/notebook/", "/notebook/notes", "/notebook/search?q=nothing", "/notebook/review", "/notebook/trash", "/notebook/graph", "/notebook/settings"])(
    "%s",
    async (path) => {
      await open(path);
      expect(await serious()).toEqual([]);
    },
  );

  it("a note", async () => {
    replies["GET /api/notebook/tree"] = () => ({ folders: ["Projects"], notes: [SUMMARY] });
    replies[`GET /api/notebook/notes/${NOTE}`] = () => FULL;
    replies[`GET /api/notebook/notes/${NOTE}/links`] = () => ({ links: [], backlinks: [] });
    await open(`/notebook/note/${NOTE}`);
    expect(await serious()).toEqual([]);
  });
});
