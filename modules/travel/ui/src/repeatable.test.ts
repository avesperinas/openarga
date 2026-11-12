import { describe, expect, it } from "vitest";

import { repeatable } from "./api";

describe("lo que se guarda sin red para mandarlo luego", () => {
  it("guarda lo que repetido no cambia nada", () => {
    expect(repeatable("PUT", { title: "x" })).toBe(true);
    expect(repeatable("PATCH", { checked: true })).toBe(true);
    expect(repeatable("DELETE", undefined)).toBe(true);
    expect(repeatable("POST", { id: "a", title: "x" })).toBe(true);
    expect(repeatable("POST", [{ id: "a", text: "x" }, { id: "b", text: "y" }])).toBe(true);
  });

  it("no guarda lo que repetido se duplicaría", () => {
    expect(repeatable("POST", { title: "x" })).toBe(false);
    expect(repeatable("POST", [{ id: "a" }, { text: "y" }])).toBe(false);
    expect(repeatable("POST", [])).toBe(false);
  });
});
