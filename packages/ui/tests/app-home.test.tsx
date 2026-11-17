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

describe("the way back to arga without a header", () => {
  it("having come from arga, it leads to the desktop with the screen's class", () => {
    window.sessionStorage.setItem("travel:desde-arga", "1");
    mount("travel-map-home glass");
    const link = document.querySelector("a");
    expect(link?.getAttribute("href")).toBe("/");
    expect(link?.getAttribute("aria-label")).toBe("Go to the OpenArga desktop");
    expect(link?.className).toBe("app-home travel-map-home glass");
  });

  it("even without coming from arga it shows: in every app, always in the same place", () => {
    mount();
    expect(document.querySelector("a")?.getAttribute("href")).toBe("/");
  });

  it("with `always={false}` it goes back to before: without coming from arga it does not show", () => {
    mount(undefined, false);
    expect(document.querySelector("a")).toBeNull();
  });
});
