// @vitest-environment jsdom
import * as React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { AppBackdrop, CrashBoundary } from "../src/index";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

let broken = true;
function Screen() {
  if (broken) throw new TypeError("x.toFixed is not a function");
  return <p>Stats</p>;
}

function mount(node: React.ReactNode): void {
  const host = document.createElement("div");
  document.body.append(host);
  act(() => createRoot(host).render(node));
}

describe("una pantalla que falla", () => {
  it("dice qué falló en vez de quedarse en blanco, y se puede volver a intentar", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    broken = true;
    mount(
      <CrashBoundary home="/training/">
        <Screen />
      </CrashBoundary>,
    );

    expect(document.body.textContent).toContain("Algo ha fallado en esta pantalla");
    expect(document.body.textContent).toContain("TypeError: x.toFixed is not a function");

    broken = false;
    await act(async () => {
      Array.from(document.querySelectorAll("button"))
        .find((button) => button.textContent === "Volver a intentarlo")!
        .click();
    });
    expect(document.body.textContent).toBe("Stats");
  });

  it("lo tiene cualquier app, porque va dentro de su fondo", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    vi.stubGlobal("fetch", async () => new Response("{}", { status: 404 }));
    broken = true;
    mount(
      <AppBackdrop app="training">
        <Screen />
      </AppBackdrop>,
    );

    expect(document.querySelector(".app-desktop .crash")).not.toBeNull();
    vi.unstubAllGlobals();
  });
});
