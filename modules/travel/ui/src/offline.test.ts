import { describe, expect, it } from "vitest";

import { adopt } from "./offline";

describe("la cola de antes de la 1.0", () => {
  it("pasa a la común con su URL entera y de quien mira", () => {
    const old = { key: 3, method: "POST", path: "/trips/t/expenses", body: { id: "e" }, what: "un gasto", at: "2026-10-01" };
    expect(adopt(old, "persona")).toEqual({
      key: 3,
      method: "POST",
      url: "/api/travel/trips/t/expenses",
      person: "persona",
      body: { id: "e" },
      what: "un gasto",
      at: "2026-10-01",
    });
  });

  it("lo que ya es de la común no se toca", () => {
    const fresh = { key: 1, method: "PUT", url: "/api/travel/x", person: "otra", body: null, what: "x", at: "" };
    expect(adopt(fresh, "persona")).toBe(fresh);
  });
});
