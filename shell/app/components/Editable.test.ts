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

describe("the device's desktop", () => {
  it("a phone in portrait sees the phone's", () => {
    screenOf(390, 844, true);
    expect(currentDevice()).toBe("mobile");
  });

  it("and rotated too: the short side of the screen does not change", () => {
    screenOf(844, 390, true);
    expect(currentDevice()).toBe("mobile");
  });

  it("a tablet sees the computer's, in portrait and landscape", () => {
    screenOf(744, 1133, true);
    expect(currentDevice()).toBe("desktop");
    screenOf(1180, 820, true);
    expect(currentDevice()).toBe("desktop");
  });

  it("narrowing the computer window changes nothing until it no longer fits", () => {
    screenOf(1920, 1080, false, 700);
    expect(currentDevice()).toBe("desktop");
    screenOf(1920, 1080, false, 500);
    expect(currentDevice()).toBe("mobile");
  });
});
