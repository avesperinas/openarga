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

describe("reading and writing a day", () => {
  it("shows the day with the weekday first", () => {
    expect(spanishDate("2026-10-02")).toBe("02/10/2026");
    expect(spanishDate("")).toBe("");
  });

  it("understands a day typed in the locale's order, and pasted ISO", () => {
    expect(parseSpanishDate("2/10/2026")).toBe("2026-10-02");
    expect(parseSpanishDate("02-10-26")).toBe("2026-10-02");
    expect(parseSpanishDate("2026-10-02")).toBe("2026-10-02");
  });

  it("does not accept days that do not exist or half-typed input", () => {
    expect(parseSpanishDate("31/02/2026")).toBeNull();
    expect(parseSpanishDate("13/13/2026")).toBeNull();
    expect(parseSpanishDate("02/10")).toBeNull();
  });
});

describe("the field", () => {
  it("writes what was typed in the locale's order as ISO", () => {
    const onChange = vi.fn();
    mount(<DateField label="From" value="" onChange={onChange} />);
    const input = document.querySelector("input")!;
    expect(input.placeholder).toBe("dd/mm/aaaa");
    typeInto(input, "05/10/2026");
    expect(onChange).toHaveBeenLastCalledWith("2026-10-05");
  });

  it("opens the month with Monday first and picks the tapped day", async () => {
    const onChange = vi.fn();
    mount(<DateField label="From" value="2026-10-02" onChange={onChange} />);
    expect(document.querySelector("input")!.value).toBe("02/10/2026");
    const open = document.querySelector<HTMLButtonElement>('button[aria-label="Pick on the calendar"]')!;
    await act(async () => open.click());

    const heads = Array.from(document.querySelectorAll(".month-weekday")).map((cell) => cell.textContent);
    expect(heads).toEqual(["M", "T", "W", "T", "F", "S", "S"]);
    const firstRow = document.querySelectorAll(".month-grid .month-row")[1]!;
    expect(firstRow.querySelectorAll("[data-empty]")).toHaveLength(3);

    const fifth = document.querySelector<HTMLButtonElement>('button[aria-label^="Monday 5 October"]')!;
    await act(async () => fifth.click());
    expect(onChange).toHaveBeenLastCalledWith("2026-10-05");
  });

  it("does not allow picking days past the maximum", async () => {
    mount(<DateField label="Hecho el" value="2026-10-02" max="2026-10-02" onChange={() => {}} />);
    const open = document.querySelector<HTMLButtonElement>('button[aria-label="Pick on the calendar"]')!;
    await act(async () => open.click());
    const third = document.querySelector<HTMLButtonElement>('button[aria-label^="Saturday 3 October"]')!;
    expect(third.disabled).toBe(true);
  });
});
