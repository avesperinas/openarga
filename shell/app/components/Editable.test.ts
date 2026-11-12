import { afterEach, describe, expect, it, vi } from "vitest";

import { currentDevice } from "./Editable";

function screenOf(width: number, height: number, touch: boolean, windowWidth = width) {
  vi.stubGlobal("window", {
    screen: { width, height },
    matchMedia: (query: string) => ({
      matches:
        query === "(pointer: coarse)"
          ? touch
          : query === "(max-width: 559px)"
            ? windowWidth <= 559
            : false,
    }),
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("el escritorio del dispositivo", () => {
  it("un móvil en vertical ve el del móvil", () => {
    screenOf(390, 844, true);
    expect(currentDevice()).toBe("mobile");
  });

  it("y girado también: el lado corto de la pantalla no cambia", () => {
    screenOf(844, 390, true);
    expect(currentDevice()).toBe("mobile");
  });

  it("una tablet ve el del ordenador, en vertical y apaisada", () => {
    screenOf(744, 1133, true);
    expect(currentDevice()).toBe("desktop");
    screenOf(1180, 820, true);
    expect(currentDevice()).toBe("desktop");
  });

  it("estrechar la ventana del ordenador no cambia nada hasta que ya no cabe", () => {
    screenOf(1920, 1080, false, 700);
    expect(currentDevice()).toBe("desktop");
    screenOf(1920, 1080, false, 500);
    expect(currentDevice()).toBe("mobile");
  });
});
