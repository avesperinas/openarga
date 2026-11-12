// @vitest-environment jsdom
import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { useTick } from "../src/index";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

let root: Root;
let host: HTMLElement;
let visibility: DocumentVisibilityState = "visible";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
  vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
  visibility = "visible";
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function Reads({ read }: { read: () => void }) {
  const tick = useTick();
  useEffect(read, [read, tick]);
  return null;
}

describe("useTick", () => {
  it("repite la lectura cada cinco minutos mientras se ve", () => {
    const read = vi.fn();
    act(() => root.render(<Reads read={read} />));
    expect(read).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(4 * 60_000));
    expect(read).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(60_000 + 15_000));
    expect(read).toHaveBeenCalledTimes(2);
  });

  it("escondida no lee; al volver, si ha pasado el rato, sí", () => {
    const read = vi.fn();
    act(() => root.render(<Reads read={read} />));
    visibility = "hidden";
    act(() => vi.advanceTimersByTime(20 * 60_000));
    expect(read).toHaveBeenCalledTimes(1);

    visibility = "visible";
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(read).toHaveBeenCalledTimes(2);
  });
});
