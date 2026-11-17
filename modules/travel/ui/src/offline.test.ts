import { describe, expect, it } from "vitest";

import { adopt } from "./offline";

describe("the queue from before 1.0", () => {
  it("moves to the shared one with its whole URL and for whoever looks", () => {
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

  it("what already belongs to the shared one is not touched", () => {
    const fresh = { key: 1, method: "PUT", url: "/api/travel/x", person: "otra", body: null, what: "x", at: "" };
    expect(adopt(fresh, "persona")).toBe(fresh);
  });
});
