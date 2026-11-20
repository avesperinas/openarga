import { missingKeys } from "@openarga/ui";
import { afterEach, describe, expect, it } from "vitest";

import { CATALOGS, propertyLabel, setLocale } from "./lang";
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

describe("property labels", () => {
  it("names the keys apps write into a daily note and leaves other names alone", () => {
    setLocale("en");
    expect(propertyLabel("fat_g")).toBe("Fat (g)");
    expect(propertyLabel("my own property")).toBe("my own property");
    setLocale("es");
    expect(propertyLabel("fat_g")).toBe("Grasa (g)");
    expect(propertyLabel("steps")).toBe("Pasos");
    setLocale("en");
  });
});
