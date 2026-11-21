import { describe, expect, it } from "vitest";

import { sayFor } from "./words";

describe("server-side words", () => {
  it("follow the person, not the last locale configured in the process", () => {
    expect(sayFor("es", "tabs.today")).toBe("Hoy");
    expect(sayFor("en", "tabs.today")).toBe("Today");
  });
});
