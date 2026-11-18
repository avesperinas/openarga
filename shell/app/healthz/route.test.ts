import { describe, expect, it } from "vitest";

import { GET } from "./route";

describe("the shell's health check", () => {
  it("answers 200 without a session and without asking the kernel", async () => {
    const response = GET();
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "ok" });
  });
});
