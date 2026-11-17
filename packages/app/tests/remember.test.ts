import { describe, expect, it, vi } from "vitest";

vi.mock("../src/persist", async (original) => ({
  ...(await original<typeof import("../src/persist")>()),
  keep: vi.fn(),
}));

import { keep } from "../src/persist";
import { peek, remember } from "../src/index";

describe("remember", () => {
  it("keeps it at hand and stores it on the device", () => {
    remember("today", { next: "Push" });

    expect(peek("today")).toEqual({ next: "Push" });
    expect(keep).toHaveBeenCalledWith("today", { next: "Push" });
  });
});
