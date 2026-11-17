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

describe("where a sheet opened from inside a card ends up", () => {
  it("hangs from the body and not from the card", () => {
    const card = openFromACard();
    const dialog = document.querySelector('[role="dialog"]');

    expect(dialog).not.toBeNull();
    expect(card.contains(dialog)).toBe(false);
    expect(document.body.contains(dialog)).toBe(true);
  });

  it("the scrim is a direct child of the body, so nothing in between can trap it", () => {
    openFromACard();
    const backdrop = document.querySelector(".bottom-sheet-backdrop");

    expect(backdrop?.parentElement).toBe(document.body);
  });
});
