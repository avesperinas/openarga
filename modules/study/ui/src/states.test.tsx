// @vitest-environment jsdom
import { reset } from "@openarga/app";
import axe from "axe-core";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
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

describe("la portada", () => {
  it("mientras llega, el esqueleto", async () => {
    replies["GET /api/study/home"] = () => new Promise(() => undefined);
    await open();
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });

  it("sin estudios, el botón crea el primero", async () => {
    await open();
    expect(host.textContent).toContain("Lo que estudias, en un sitio");
    expect(button("Crear un estudio")).toBeDefined();
  });

  it("si falla, lo dice y reintentar la trae", async () => {
    replies["GET /api/study/home"] = () => json({ detail: "la base no contesta" }, 503);
    await open();
    expect(host.textContent).toContain("Study no contesta");
    expect(host.textContent).toContain("la base no contesta");

    replies["GET /api/study/home"] = () => EMPTY_HOME;
    act(() => button("Reintentar")!.click());
    await settle();
    expect(host.textContent).toContain("Lo que estudias, en un sitio");
  });

  it("sin red, lo dice arriba", async () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    await open();
    expect(host.textContent).toContain("Sin conexión");
  });
});

describe("un estudio", () => {
  it("si no existe lo dice; otro fallo se reintenta", async () => {
    await open(`/study/estudio/${COURSE}`);
    expect(host.textContent).toContain("Ya no está");
    expect(button("Reintentar")).toBeUndefined();

    act(() => root.unmount());
    root = createRoot(host);
    void reset();
    for (const part of ["schedules", "sessions", "materials"]) replies[`GET /api/study/courses/${COURSE}/${part}`] = () => [];
    replies[`GET /api/study/courses/${COURSE}`] = () => json({ detail: "la base no contesta" }, 503);
    await open(`/study/estudio/${COURSE}`);
    expect(host.textContent).toContain("la base no contesta");
    expect(button("Reintentar")).toBeDefined();
  });
});

describe("los apuntes", () => {
  it("sin apuntes ni estudios, dice cómo empezar", async () => {
    replies["GET /api/study/notes"] = () => [];
    await open("/study/apuntes");
    expect(host.textContent).toContain("Sin apuntes todavía");
  });

  it("unos apuntes no se enseñan con lo guardado: esperan a leerlos", async () => {
    replies[`GET /api/study/notes/${NOTE}`] = () => new Promise(() => undefined);
    await open(`/study/apuntes/${NOTE}`);
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });
});

describe("axe-core sin errores graves", () => {
  it.each(["/study/", "/study/semana", "/study/apuntes", "/study/archivo", "/study/ajustes"])("%s", async (path) => {
    await open(path);
    expect(await serious()).toEqual([]);
  });
});

function Probe({ load, fresh = false }: { load: () => Promise<string>; fresh?: boolean }) {
  const { data, found } = useLoad("probe:1", load, { fresh });
  return <div>{data ?? <Pending found={found} />}</div>;
}

describe("lo leído", () => {
  it("lo que se borró no se enseña aunque quede su copia", async () => {
    let answer: () => Promise<string> = async () => "el estudio";
    act(() => root.render(<Probe load={() => answer()} />));
    await settle();
    expect(host.textContent).toContain("el estudio");

    answer = async () => {
      throw new Error("no existe: el estudio");
    };
    act(() => changed());
    await settle();
    expect(host.textContent).not.toContain("el estudio");
    expect(host.textContent).toContain("Ya no está");
  });

  it("con editor, no arranca de lo que había: espera a leerlo", async () => {
    act(() => root.render(<Probe load={async () => "lo de antes"} />));
    await settle();
    act(() => root.unmount());
    root = createRoot(host);

    act(() => root.render(<Probe fresh load={() => new Promise(() => undefined)} />));
    await settle();
    expect(host.textContent).not.toContain("lo de antes");
    expect(host.querySelector(".skeleton")).not.toBeNull();
  });
});
