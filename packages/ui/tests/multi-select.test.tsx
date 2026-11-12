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
  { value: "cash", label: "Efectivo" },
  { value: "funds", label: "Fondos" },
  { value: "pension", label: "Pensión" },
];

function Harness({ start = [] as string[], seen }: { start?: string[]; seen: string[][] }) {
  const [values, setValues] = React.useState(start);
  return (
    <MultiSelectField
      label="Tipo de producto"
      all="Todos los tipos"
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

describe("el desplegable de varias", () => {
  it("sin nada marcado dice «todos», y cerrado no enseña la lista", () => {
    const { host, button } = mount();
    expect(button().textContent).toBe("Todos los tipos");
    expect(button().getAttribute("aria-expanded")).toBe("false");
    expect(host.querySelector('[role="listbox"]')).toBeNull();
  });

  it("marca en el orden de las opciones, dice lo marcado y desmarca", () => {
    const { seen, button, option } = mount();
    act(() => button().click());
    act(() => option("Pensión").click());
    act(() => option("Efectivo").click());
    expect(seen.at(-1)).toEqual(["cash", "pension"]);
    expect(button().textContent).toBe("Efectivo, Pensión");
    expect(option("Efectivo").getAttribute("aria-selected")).toBe("true");
    act(() => option("Fondos").click());
    expect(button().textContent).toBe("3 elegidas");
    act(() => option("Efectivo").click());
    expect(seen.at(-1)).toEqual(["funds", "pension"]);
  });

  it("«Quitar la selección» vuelve a todos, y tocar fuera la cierra", () => {
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
