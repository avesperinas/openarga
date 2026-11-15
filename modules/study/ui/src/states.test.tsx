// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { setLocale } from "./lang";
import { Pending, useLoad, changed } from "./Bits";

const COURSE = "0a0a0a0a-0000-4000-8000-00000000a0a0";
const NOTE = "0b0b0b0b-0000-4000-8000-00000000b0b0";

type Reply = () => unknown;

let root: Root;
let host: HTMLElement;
let replies: Record<string, Reply>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const EMPTY_HOME = { week_start: "2026-10-26", days: [], upcoming: [], courses: [], archived: 0 };

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
  setLocale("en");
  replies = {
    "GET /api/study/home": () => EMPTY_HOME,
    "GET /api/study/courses": () => [],
    "GET /api/study/notes": () => [],
    "GET /api/study/sessions": () => [],
    "GET /api/study/assessments": () => [],
    "GET /api/study/version": () => ({ version: "1.0.0" }),
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
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const settle = () =>
  act(async () => {
    for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  });

const RETRY = "Reintentar";

const button = (name: string) =>
  Array.from(host.querySelectorAll<HTMLButtonElement>("button")).find((one) => one.textContent?.includes(name));

async function open(path = "/study/") {
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

describe("the home screen", () => {
  it("the skeleton while it loads", async () => {
    replies["GET /api/study/home"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("with no courses, the button creates the first", async () => {
    await open();
    expect(host.textContent).toContain("What you study, in one place");
    expect(button("Create a course")).toBeDefined();
  });

  it("on failure it says so and retry brings it back", async () => {
    replies["GET /api/study/home"] = () => json({ detail: "the server is down" }, 503);
    await open();
    expect(host.textContent).toContain("Study does not answer");
    expect(host.textContent).toContain("the server is down");

    replies["GET /api/study/home"] = () => EMPTY_HOME;
    act(() => button(RETRY)!.click());
    await settle();
    expect(host.textContent).toContain("What you study, in one place");
  });

  it("offline, it says so at the top", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.querySelector('.notice[data-tone="warning"]')).not.toBeNull();
  });
});

describe("a course", () => {
  it("if it does not exist it says so; another failure retries", async () => {
    await open(`/study/estudio/${COURSE}`);
    expect(host.textContent).toContain("It is no longer there");
    expect(button(RETRY)).toBeUndefined();

    act(() => root.unmount());
    root = createRoot(host);
    void reset();
    for (const part of ["schedules", "sessions", "materials"]) replies[`GET /api/study/courses/${COURSE}/${part}`] = () => [];
    replies[`GET /api/study/courses/${COURSE}`] = () => json({ detail: "the server is down" }, 503);
    await open(`/study/estudio/${COURSE}`);
    expect(host.textContent).toContain("the server is down");
    expect(button(RETRY)).toBeDefined();
  });
});

describe("the notes", () => {
  it("with no notes or courses, it says how to start", async () => {
    replies["GET /api/study/notes"] = () => [];
    await open("/study/apuntes");
    expect(host.textContent).toContain("No notes yet");
  });

  it("a note is not shown from the cache: it waits to be read", async () => {
    replies[`GET /api/study/notes/${NOTE}`] = () => new Promise(() => undefined);
    await open(`/study/apuntes/${NOTE}`);
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });
});

describe("axe-core with no serious errors", () => {
  it.each(["/study/", "/study/semana", "/study/apuntes", "/study/archivo", "/study/ajustes"])("%s", async (path) => {
    await open(path);
    expect(await serious()).toEqual([]);
  });
});

function Probe({ load, fresh = false }: { load: () => Promise<string>; fresh?: boolean }) {
  const { data, found } = useLoad("probe:1", load, { fresh });
  return <div>{data ?? <Pending found={found} />}</div>;
}

describe("what is read", () => {
  it("what was deleted is not shown even if its copy remains", async () => {
    let answer: () => Promise<string> = async () => "the course";
    act(() => root.render(<Probe load={() => answer()} />));
    await settle();
    expect(host.textContent).toContain("the course");

    answer = async () => {
      throw new Error("does not exist: the course");
    };
    act(() => changed());
    await settle();
    expect(host.textContent).not.toContain("the course");
    expect(host.textContent).toContain("It is no longer there");
  });

  it("in fresh mode it does not start from the cache: it waits to be read", async () => {
    act(() => root.render(<Probe load={async () => "the earlier text"} />));
    await settle();
    act(() => root.unmount());
    root = createRoot(host);

    act(() => root.render(<Probe fresh load={() => new Promise(() => undefined)} />));
    await settle();
    expect(host.textContent).not.toContain("the earlier text");
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });
});
