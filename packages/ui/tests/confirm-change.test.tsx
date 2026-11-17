// @vitest-environment jsdom
import * as React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ConfirmChange, ConfirmPanel } from "../src/index";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(() => {
  document.body.innerHTML = "";
});

function mount(node: React.ReactNode): void {
  const host = document.createElement("div");
  document.body.append(host);
  act(() => createRoot(host).render(node));
}

async function press(name: string): Promise<void> {
  const found = Array.from(document.querySelectorAll("button")).find((b) => b.textContent === name);
  if (!found) throw new Error(`no button "${name}"`);
  await act(async () => found.click());
}

describe("confirming a change", () => {
  it("says what changes and saves nothing until its button is pressed", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    mount(
      <ConfirmPanel
        title="Save?"
        changes={[{ label: "Category", from: "Leisure", to: "Health" }]}
        action="Save changes"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    );
    expect(document.body.textContent).toContain("Leisure");
    expect(document.body.textContent).toContain("Health");
    expect(onConfirm).not.toHaveBeenCalled();
    await press("Back");
    expect(onCancel).toHaveBeenCalledOnce();
    await press("Save changes");
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("if it fails, it says so and allows retrying", async () => {
    mount(
      <ConfirmChange title="Settle?" action="Mark as settled" onCancel={() => undefined} onConfirm={() => Promise.reject(new Error("Offline"))} />,
    );
    await press("Mark as settled");
    expect(document.querySelector('[role="alert"]')?.textContent).toBe("Offline");
    expect(Array.from(document.querySelectorAll("button")).some((b) => b.textContent === "Mark as settled")).toBe(true);
  });
});
