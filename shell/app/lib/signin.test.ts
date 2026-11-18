import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({ headers: async () => new Headers() }));

import { readDesktops, SignInRequired } from "./kernel";

describe("a kernel answer of 401", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("is told apart from any other failure", async () => {
    vi.stubGlobal("fetch", async () => new Response("{}", { status: 401 }));
    await expect(readDesktops()).rejects.toBeInstanceOf(SignInRequired);
    vi.stubGlobal("fetch", async () => new Response("{}", { status: 500 }));
    await expect(readDesktops()).rejects.not.toBeInstanceOf(SignInRequired);
  });
});
