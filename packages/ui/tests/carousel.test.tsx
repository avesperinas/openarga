// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";

import { Carousel } from "../src/index";

it("las flechas y el teclado mueven el carril una tarjeta, y en el borde su flecha se esconde", () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const scrollBy = vi.fn();
  Object.defineProperty(HTMLElement.prototype, "scrollBy", { value: scrollBy, configurable: true });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { get: () => 288, configurable: true });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { get: () => 300, configurable: true });
  Object.defineProperty(HTMLElement.prototype, "scrollWidth", { get: () => 900, configurable: true });

  act(() =>
    root.render(
      <Carousel label="Datos de hoy">
        <p>Uno</p>
        <p>Dos</p>
        <p>Tres</p>
      </Carousel>,
    ),
  );
  const start = host.querySelector<HTMLButtonElement>('[aria-label="Anterior"]')!;
  const end = host.querySelector<HTMLButtonElement>('[aria-label="Siguiente"]')!;
  expect(start.hidden).toBe(true);
  expect(end.hidden).toBe(false);

  act(() => end.click());
  expect(scrollBy).toHaveBeenLastCalledWith(expect.objectContaining({ left: 288 }));

  const track = host.querySelector<HTMLElement>(".carousel")!;
  act(() => track.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true })));
  expect(scrollBy).toHaveBeenLastCalledWith(expect.objectContaining({ left: -288 }));

  act(() => root.unmount());
  host.remove();
});
