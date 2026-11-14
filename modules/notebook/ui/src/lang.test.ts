import { missingKeys } from "@openarga/ui";
import { afterEach, describe, expect, it } from "vitest";

import { CATALOGS, setLocale } from "./lang";
import { ago, who } from "./when";

describe("the language", () => {
  afterEach(() => setLocale("en"));

  it("both catalogs have the same keys", () => {
    expect(missingKeys(CATALOGS)).toEqual([]);
  });

  it("follows the person's locale", () => {
    const now = new Date("2026-10-29T10:00:00Z");
    const before = new Date(now.getTime() - 5 * 60_000).toISOString();
    expect([who("app"), ago(before, now)]).toEqual(["You", "5 min ago"]);
    setLocale("es");
    expect([who("app"), ago(before, now)]).toEqual([CATALOGS.es!["who.you"], "hace 5 min"]);
  });
});
