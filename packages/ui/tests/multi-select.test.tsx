// @vitest-environment jsdom
import * as React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { MultiSelectField } from "../src/index";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

afterEach(() => {
  document.body.innerHTML = "";
});

const OPTIONS = [
  { value: "cash", label: "Cash" },
  { value: "funds", label: "Fondos" },
  { value: "pension", label: "Pension" },
];

function Harness({ start = [] as string[], seen }: { start?: string[]; seen: string[][] }) {
  const [values, setValues] = React.useState(start);
  return (
    <MultiSelectField
      label="Tipo de producto"
      all="All kinds"
      options={OPTIONS}
      values={values}
      onChange={(next) => {
        seen.push(next);
        setValues(next);
      }}
    />
  );
}

function mount(start: string[] = []) {
  const seen: string[][] = [];
  const host = document.createElement("div");
  document.body.append(host);
  act(() => createRoot(host).render(<Harness start={start} seen={seen} />));
  const button = () => host.querySelector<HTMLButtonElement>(".multi-select-button")!;
  const option = (label: string) =>
    Array.from(host.querySelectorAll<HTMLButtonElement>('[role="option"]')).find((b) => b.textContent === label)!;
  return { host, seen, button, option };
}

describe("the multi-select dropdown", () => {
  it("with nothing checked it says “all”, and closed it does not show the list", () => {
    const { host, button } = mount();
    expect(button().textContent).toBe("All kinds");
    expect(button().getAttribute("aria-expanded")).toBe("false");
    expect(host.querySelector('[role="listbox"]')).toBeNull();
  });

  it("checks in the order of the options, says what is checked and unchecks", () => {
    const { seen, button, option } = mount();
    act(() => button().click());
    act(() => option("Pension").click());
    act(() => option("Cash").click());
    expect(seen.at(-1)).toEqual(["cash", "pension"]);
    expect(button().textContent).toBe("Cash, Pension");
    expect(option("Cash").getAttribute("aria-selected")).toBe("true");
    act(() => option("Fondos").click());
    expect(button().textContent).toBe("3 elegidas");
    act(() => option("Cash").click());
    expect(seen.at(-1)).toEqual(["funds", "pension"]);
  });

  it("“Clear selection” goes back to all, and tapping outside closes it", () => {
    const { host, seen, button } = mount(["funds"]);
    act(() => button().click());
    const clear = host.querySelector<HTMLButtonElement>(".multi-select-clear")!;
    act(() => clear.click());
    expect(seen.at(-1)).toEqual([]);
    act(() => {
      document.body.dispatchEvent(new Event("pointerdown", { bubbles: true }));
    });
    expect(host.querySelector('[role="listbox"]')).toBeNull();
  });
});
