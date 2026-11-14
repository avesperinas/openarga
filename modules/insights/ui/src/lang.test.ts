import { missingKeys } from "@openarga/ui";
import { afterEach, describe, expect, it } from "vitest";

import { CATALOGS, dateFormat, setLocale, t } from "./lang";

describe("the language", () => {
  afterEach(() => setLocale("en"));

  it("both catalogs have the same keys", () => {
    expect(missingKeys(CATALOGS)).toEqual([]);
  });

  it("follows the person's locale", () => {
    const day = new Date("2026-11-10T10:00:00Z");
    const month = dateFormat({ month: "long", timeZone: "UTC" });
    expect([t("action.save"), month.format(day)]).toEqual(["Save", "November"]);
    setLocale("es");
    expect([t("action.save"), month.format(day)]).toEqual([CATALOGS.es!["action.save"], "noviembre"]);
  });
});
