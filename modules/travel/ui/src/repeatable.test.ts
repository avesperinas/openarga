import { describe, expect, it } from "vitest";

import { repeatable } from "./api";

describe("what is kept offline to send later", () => {
  it("keeps what changes nothing when repeated", () => {
    expect(repeatable("PUT", { title: "x" })).toBe(true);
    expect(repeatable("PATCH", { checked: true })).toBe(true);
    expect(repeatable("DELETE", undefined)).toBe(true);
    expect(repeatable("POST", { id: "a", title: "x" })).toBe(true);
    expect(repeatable("POST", [{ id: "a", text: "x" }, { id: "b", text: "y" }])).toBe(true);
  });

  it("does not keep what would be duplicated when repeated", () => {
    expect(repeatable("POST", { title: "x" })).toBe(false);
    expect(repeatable("POST", [{ id: "a" }, { text: "y" }])).toBe(false);
    expect(repeatable("POST", [])).toBe(false);
  });
});
