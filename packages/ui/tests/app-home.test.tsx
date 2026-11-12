// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { AppHome } from "../src/index";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(() => {
  document.body.innerHTML = "";
  window.sessionStorage.clear();
});

function mount(className?: string, always?: boolean): void {
  const host = document.createElement("div");
  document.body.append(host);
  act(() => createRoot(host).render(<AppHome app="travel" className={className} always={always} />));
}

describe("la vuelta a arga sin cabecera", () => {
  it("habiendo venido de arga, lleva al escritorio con la clase de la pantalla", () => {
    window.sessionStorage.setItem("travel:desde-arga", "1");
    mount("travel-map-home glass");
    const link = document.querySelector("a");
    expect(link?.getAttribute("href")).toBe("/");
    expect(link?.getAttribute("aria-label")).toBe("Ir al escritorio de arga");
    expect(link?.className).toBe("app-home travel-map-home glass");
  });

  it("sin haber venido de arga sale igual: en todas las apps, siempre en el mismo sitio", () => {
    mount();
    expect(document.querySelector("a")?.getAttribute("href")).toBe("/");
  });

  it("con `always={false}` vuelve a lo de antes: sin haber venido de arga no sale", () => {
    mount(undefined, false);
    expect(document.querySelector("a")).toBeNull();
  });
});
