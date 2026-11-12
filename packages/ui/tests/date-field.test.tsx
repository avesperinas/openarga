// @vitest-environment jsdom
import * as React from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { DateField, parseSpanishDate, spanishDate } from "../src/index";

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

function typeInto(input: HTMLInputElement, text: string): void {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  act(() => {
    setter.call(input, text);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

describe("leer y escribir un día", () => {
  it("enseña el día con el día delante", () => {
    expect(spanishDate("2026-10-02")).toBe("02/10/2026");
    expect(spanishDate("")).toBe("");
  });

  it("entiende el día escrito a la española, y el ISO pegado", () => {
    expect(parseSpanishDate("2/10/2026")).toBe("2026-10-02");
    expect(parseSpanishDate("02-10-26")).toBe("2026-10-02");
    expect(parseSpanishDate("2026-10-02")).toBe("2026-10-02");
  });

  it("no da por buenos días que no existen ni lo que está a medio escribir", () => {
    expect(parseSpanishDate("31/02/2026")).toBeNull();
    expect(parseSpanishDate("13/13/2026")).toBeNull();
    expect(parseSpanishDate("02/10")).toBeNull();
  });
});

describe("el campo", () => {
  it("escribe en ISO lo tecleado a la española", () => {
    const onChange = vi.fn();
    mount(<DateField label="Desde" value="" onChange={onChange} />);
    const input = document.querySelector("input")!;
    expect(input.placeholder).toBe("dd/mm/aaaa");
    typeInto(input, "05/10/2026");
    expect(onChange).toHaveBeenLastCalledWith("2026-10-05");
  });

  it("abre el mes con el lunes primero y elige el día pulsado", async () => {
    const onChange = vi.fn();
    mount(<DateField label="Desde" value="2026-10-02" onChange={onChange} />);
    expect(document.querySelector("input")!.value).toBe("02/10/2026");
    const open = document.querySelector<HTMLButtonElement>('button[aria-label="Elegir en el calendario"]')!;
    await act(async () => open.click());

    const heads = Array.from(document.querySelectorAll(".month-weekday")).map((cell) => cell.textContent);
    expect(heads).toEqual(["L", "M", "X", "J", "V", "S", "D"]);
    const firstRow = document.querySelectorAll(".month-grid .month-row")[1]!;
    expect(firstRow.querySelectorAll("[data-empty]")).toHaveLength(3);

    const fifth = document.querySelector<HTMLButtonElement>('button[aria-label^="lunes, 5 de octubre"]')!;
    await act(async () => fifth.click());
    expect(onChange).toHaveBeenLastCalledWith("2026-10-05");
  });

  it("no deja elegir días pasado el máximo", async () => {
    mount(<DateField label="Hecho el" value="2026-10-02" max="2026-10-02" onChange={() => {}} />);
    const open = document.querySelector<HTMLButtonElement>('button[aria-label="Elegir en el calendario"]')!;
    await act(async () => open.click());
    const third = document.querySelector<HTMLButtonElement>('button[aria-label^="sábado, 3 de octubre"]')!;
    expect(third.disabled).toBe(true);
  });
});
