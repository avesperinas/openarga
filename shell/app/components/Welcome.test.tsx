// @vitest-environment jsdom
import * as React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import type { PersonPreferences } from "../lib/regional";
import { Welcome } from "./Welcome";

const SAM: PersonPreferences = {
  locale: "en",
  timezone: "Europe/Madrid",
  currency: "EUR",
  country: "ES",
  region: "ES-NA",
  area: "pamplona",
};
const APPS = [
  { id: "planner", name: "Calendar", hue: 6 },
  { id: "study", name: "Study", hue: 6 },
];

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

async function press(label: string): Promise<void> {
  const found = Array.from(document.querySelectorAll("button")).find(
    (button) => button.textContent === label || button.getAttribute("aria-label") === label,
  );
  if (!found) throw new Error(`no button "${label}"`);
  await act(async () => found.click());
}

describe("the first run", () => {
  it("asks for the region, then the apps, and saves both only at the end", async () => {
    const finish = vi.fn(async () => undefined);
    const done = vi.fn();
    mount(<Welcome initial={SAM} apps={APPS} finish={finish} done={done} />);
    expect(document.body.textContent).toContain("Welcome to OpenArga");
    expect(document.body.textContent).toContain("Language and region");

    await press("Next");
    expect(document.body.textContent).toContain("Your apps");
    expect(finish).not.toHaveBeenCalled();

    await press("Hide Study");
    await press("Start");
    expect(finish).toHaveBeenCalledWith(SAM, ["study"]);
    expect(done).toHaveBeenCalledOnce();
  });

  it("if saving fails it stays, says so and lets the person try again", async () => {
    const done = vi.fn();
    mount(<Welcome initial={SAM} apps={APPS} finish={() => Promise.reject(new Error("offline"))} done={done} />);
    await press("Next");
    await press("Start");
    expect(document.body.textContent).toContain("It could not be saved");
    expect(done).not.toHaveBeenCalled();
    expect(Array.from(document.querySelectorAll("button")).some((button) => button.textContent === "Start")).toBe(true);
  });
});
