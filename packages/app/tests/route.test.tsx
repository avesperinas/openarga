// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { useRoute } from "../src/index";

let root: Root;
let host: HTMLElement;
let go: (to: string) => void;

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  window.scrollTo = () => undefined;
});
beforeEach(() => {
  window.history.replaceState(null, "", "/demo/");
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  delete (document as { startViewTransition?: unknown }).startViewTransition;
});

const parse = (path: string) => path.replace("/demo/", "") || "home";
const format = (to: string) => (to === "home" ? "/demo/" : `/demo/${to}`);

function Page() {
  const [route, navigate] = useRoute(parse, format);
  go = navigate;
  return <p>{route}</p>;
}

const reduced = (matches: boolean) => {
  window.matchMedia = (() => ({ matches })) as never;
};

describe("useRoute", () => {
  it("cambia de pantalla dentro de una transición de vista, ya pintada al acabar el callback", () => {
    reduced(false);
    const seen: string[] = [];
    (document as { startViewTransition?: unknown }).startViewTransition = vi.fn((update: () => void) => {
      update();
      seen.push(host.textContent ?? "");
    });
    act(() => root.render(<Page />));
    act(() => go("libro"));
    expect(seen).toEqual(["libro"]);
    expect(window.location.pathname).toBe("/demo/libro");
  });

  it("con movimiento reducido o sin la API, cambia sin transición", () => {
    reduced(true);
    const start = vi.fn();
    (document as { startViewTransition?: unknown }).startViewTransition = start;
    act(() => root.render(<Page />));
    act(() => go("libro"));
    expect(start).not.toHaveBeenCalled();
    expect(host.textContent).toBe("libro");

    delete (document as { startViewTransition?: unknown }).startViewTransition;
    reduced(false);
    act(() => go("home"));
    expect(host.textContent).toBe("home");
  });
});
