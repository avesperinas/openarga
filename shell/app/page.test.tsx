import { beforeEach, describe, expect, it, vi } from "vitest";

const { redirect, signedOut } = vi.hoisted(() => ({
  redirect: vi.fn((target: string) => {
    throw new Error(`NEXT_REDIRECT ${target}`);
  }),
  signedOut: { on: true },
}));

vi.mock("next/navigation", () => ({ redirect }));
vi.mock("next/headers", () => ({ headers: async () => new Headers() }));
vi.mock("./lib/kernel", async () => {
  const actual = await vi.importActual<typeof import("./lib/kernel")>("./lib/kernel");
  const refuse = async () => {
    if (signedOut.on) throw new actual.SignInRequired("401");
    throw new Error("boom");
  };
  return {
    ...actual,
    readFirstRun: async () => ({ pending: false }),
    readDesktops: refuse,
    readCatalogue: refuse,
    readPreferences: refuse,
    readModules: refuse,
    readWallpapers: refuse,
  };
});

import Today from "./page";

describe("the home page without a session", () => {
  beforeEach(() => {
    redirect.mockClear();
    signedOut.on = true;
  });

  it("sends the person to the login page instead of failing", async () => {
    await expect(Today()).rejects.toThrow("NEXT_REDIRECT /login?next=%2F");
    expect(redirect).toHaveBeenCalledWith("/login?next=%2F");
  });

  it("still fails on any other error", async () => {
    signedOut.on = false;
    await expect(Today()).rejects.toThrow("boom");
    expect(redirect).not.toHaveBeenCalled();
  });
});
