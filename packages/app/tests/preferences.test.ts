import { afterEach, describe, expect, it } from "vitest";

import { FALLBACK, forgetPreferences, loadPreferences } from "../src/preferences";

afterEach(() => forgetPreferences());

describe("preferences", () => {
  it("come from the kernel", async () => {
    const mine = { ...FALLBACK, locale: "es" as const, timezone: "Europe/Madrid" };
    const fetcher = async () => new Response(JSON.stringify(mine), { status: 200 });
    expect(await loadPreferences(fetcher as typeof fetch)).toEqual(mine);
  });

  it("fall back to the defaults when the kernel does not answer", async () => {
    const fetcher = async () => Promise.reject(new TypeError("offline"));
    expect(await loadPreferences(fetcher as typeof fetch)).toEqual(FALLBACK);
  });
});
