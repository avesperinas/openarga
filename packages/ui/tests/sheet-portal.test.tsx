// @vitest-environment jsdom
import * as React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { Sheet } from "../src/index";

const noop = () => {};

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(() => {
  document.body.innerHTML = "";
});

function openFromACard(): HTMLElement {
  const card = document.createElement("div");
  card.className = "surface widget";
  card.style.isolation = "isolate";
  document.body.append(card);
  act(() =>
    createRoot(card).render(
      <Sheet title="¿Empezar Pull?" onClose={noop}>
        <p>contenido</p>
      </Sheet>,
    ),
  );
  return card;
}

describe("dónde acaba una hoja abierta desde dentro de una tarjeta", () => {
  it("cuelga del body y no de la tarjeta", () => {
    const card = openFromACard();
    const dialog = document.querySelector('[role="dialog"]');

    expect(dialog).not.toBeNull();
    expect(card.contains(dialog)).toBe(false);
    expect(document.body.contains(dialog)).toBe(true);
  });

  it("el velo es hijo directo del body, así que nadie de en medio puede atraparlo", () => {
    openFromACard();
    const backdrop = document.querySelector(".bottom-sheet-backdrop");

    expect(backdrop?.parentElement).toBe(document.body);
  });
});
